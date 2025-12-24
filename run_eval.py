# v1.7 AsyncIO Refactor + Database Integration

import os
import argparse
import json
import csv
import traceback
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from adapters import load_adapter
from metrics import MetricsCollector, get_metrics_analyzer
from monitoring import start_metrics_server, stop_metrics_server, record_api_request, record_evaluation_start, record_evaluation_end, record_prompt_processing, record_response, update_custom_metrics
from reporting import ReportGenerator
from database import init_db, get_db_session, Evaluation, Result, Metric, DATABASE_URL

def log_error(output_dir, error_msg):
    log_path = os.path.join(output_dir, "error.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {error_msg}\n")

async def run_evaluation_suite(config, adapter_name):
    """
    Runs the evaluation suite asynchronously.
    """
    # Load prompts
    dataset_file = config.get("dataset", "evals_dataset.json")
    with open(dataset_file, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    # Prepare output directory
    base_output_dir = config.get("output_dir", "outputs")
    use_ts = config.get("use_timestamp_output_dir", True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") if use_ts else None
    output_dir = os.path.join(base_output_dir, ts) if ts else base_output_dir
    os.makedirs(output_dir, exist_ok=True)

    results = []
    adapter_fn = load_adapter(adapter_name)
    model_name = config.get("model_name") or adapter_name
    
    metrics_collector = MetricsCollector()
    collect_metrics = config.get("collect_metrics", True)
    concurrency = config.get("max_workers", 10) # Default to higher concurrency for async

    print(f"Evaluating model '{model_name}' using adapter '{adapter_name}' with {len(prompts)} prompts (Concurrency: {concurrency})...")
    
    # DB Initialization
    engine = await init_db()
    
    # Check for Dynamic Adapter Config
    async for session in get_db_session(engine):
        from database import AdapterConfig
        db_adapter = await session.get(AdapterConfig, adapter_name)
        if db_adapter:
            print(f"Loaded dynamic adapter configuration for '{adapter_name}' (Base: {db_adapter.base_type})")
            # Override adapter_name to the base type (e.g., 'openai')
            real_adapter_name = db_adapter.base_type
            
            # Inject config overrides
            config["model_name"] = db_adapter.model_name
            if db_adapter.api_key:
                config[f"{real_adapter_name.upper()}_API_KEY"] = db_adapter.api_key
            if db_adapter.api_base:
                config[f"{real_adapter_name.upper()}_API_BASE"] = db_adapter.api_base
            
            # Merge extra parameters
            if db_adapter.parameters:
                config.update(db_adapter.parameters)
            
            # Use the base adapter loader
            adapter_fn = load_adapter(real_adapter_name)
        else:
            # Standard static adapter
            real_adapter_name = adapter_name
            adapter_fn = load_adapter(adapter_name)

    # Create DB Evaluation record
    async for session in get_db_session(engine):
        db_eval = Evaluation(
            id=str(int(time.time())), # Simple ID generation
            timestamp=datetime.utcnow(),
            config_snapshot=json.loads(json.dumps(config, default=str)),
            status="running"
        )
        session.add(db_eval)
        await session.commit()
        await session.refresh(db_eval)
        eval_id = db_eval.id
    
    record_evaluation_start()
    eval_start_time = time.time()

    # Initialize Plugin Manager
    from plugins import PluginManager
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()

    # Semaphore for concurrency control
    sem = asyncio.Semaphore(concurrency)

    # Callback support for event streaming
    log_callback = config.get("_callback")
    
    async def emit_event(event_type, data):
        if log_callback:
            await log_callback(event_type, data)

    async def process_entry(entry):
        async with sem:
            prompt_text = entry.get("prompt") or entry.get("input")
            if not prompt_text:
                return None

            # Emit start event
            await emit_event("start_prompt", {"id": entry.get("id"), "prompt": prompt_text[:50]})

            record_prompt_processing()
            start_time = time.time()
            success = False
            response = ""
            error_msg = None
            plugin_scores = {}

            try:
                # Call Async Adapter
                response = await adapter_fn(prompt_text, config)
                success = True
                
                if collect_metrics:
                    response_time = time.time() - start_time
                    metrics_collector.record_success(response_time)
                
                duration = time.time() - start_time
                record_response(success=True, response_time=duration)
                record_api_request(model=model_name, adapter=adapter_name, duration=duration, success=True)

                # Run Plugins
                metadata = {
                    "latency": duration,
                    "model": model_name,
                    "adapter": adapter_name,
                    "config": config
                }
                plugin_scores = await plugin_manager.run_scorers(prompt_text, response, metadata)

            except Exception as e:
                error_msg = str(e)
                if collect_metrics:
                    metrics_collector.record_error(e, prompt_text)
                
                duration = time.time() - start_time
                record_response(success=False)
                record_api_request(model=model_name, adapter=adapter_name, duration=duration, success=False, error_type=type(e).__name__)
                
                log_error(output_dir, f"Error on prompt '{prompt_text[:30]}...': {e}")
            
            result_data = {
                "id": entry.get("id"),
                "prompt": prompt_text,
                "response": response if success else "",
                "model": model_name,
                "is_simulation": config.get("is_simulation", False),
                "eval_criteria": entry.get("eval_criteria"),
                "success": success,
                "error": error_msg,
                "plugin_scores": plugin_scores
            }
            
            # Emit end event
            await emit_event("end_prompt", {
                "id": entry.get("id"), 
                "success": success, 
                "latency": duration,
                "error": str(error_msg) if error_msg else None
            })

            # Save to Database
            async for session in get_db_session(engine):
                # Note: plugin_scores are not yet stored in DB in this version
                db_result = Result(
                    evaluation_id=eval_id,
                    prompt_id=str(entry.get("id")),
                    prompt_text=prompt_text,
                    response_text=response if success else "",
                    model=model_name,
                    adapter=adapter_name,
                    latency_ms=duration * 1000,
                    success=success,
                    error_message=error_msg
                )
                session.add(db_result)
                await session.commit()
            
            return result_data

    # Run tasks
    tasks = [process_entry(p) for p in prompts]
    processed_results = await asyncio.gather(*tasks)
    
    # Filter valid results
    results = [r for r in processed_results if r]

    # Write CSV/JSON output for backward compatibility
    csv_filename = config.get("output", "results.csv")
    csv_path = os.path.join(output_dir, csv_filename)
    json_path = os.path.splitext(csv_path)[0] + ".json"

    with open(csv_path, "w", newline="", encoding="utf-8") as out_csv:
        writer = csv.writer(out_csv)
        writer.writerow(["id", "prompt", "response", "model", "is_simulation"])
        for r in results:
            if r["success"]:
                writer.writerow([r["id"], r["prompt"], r["response"], r["model"], r["is_simulation"]])

    with open(json_path, "w", encoding="utf-8") as out_json:
        json.dump(results, out_json, indent=2)

    # Save metrics
    if collect_metrics:
        metrics_data = metrics_collector.get_metrics()
        metrics_path = os.path.join(output_dir, "metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as mb:
            json.dump(metrics_data, mb, indent=2)
        
        # Save metrics to DB
        async for session in get_db_session(engine):
            # Flatten metrics into key-value pairs
            # Assuming simple structure for now
            for k, v in metrics_data.get("errors_by_type", {}).items():
                 session.add(Metric(evaluation_id=eval_id, name=f"error_count_{k}", value=float(v)))
            session.add(Metric(evaluation_id=eval_id, name="total_requests", value=float(metrics_data.get("total_requests", 0))))
            session.add(Metric(evaluation_id=eval_id, name="successful_requests", value=float(metrics_data.get("successful_requests", 0))))
            await session.commit()

    # Update DB status
    async for session in get_db_session(engine):
        eval_record = await session.get(Evaluation, eval_id)
        if eval_record:
            eval_record.status = "completed"
            await session.commit()

    record_evaluation_end(time.time() - eval_start_time)
    await engine.dispose()
    
    return results, output_dir, metrics_collector

async def post_analyze_groq(results, config, suffix="all_models"):
    analysis_dir = os.path.join(config.get("output_dir", "outputs"), "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    analysis_csv = os.path.join(analysis_dir, f"groq_scores_{suffix}{ts}.csv")
    analysis_json = os.path.join(analysis_dir, f"groq_scores{suffix}_{ts}.json")

    adapter_fn = load_adapter("groq")
    rubric_fields = sorted({k for item in results for k in (item.get("eval_criteria") or {}).keys()})
    scored = []
    
    sem = asyncio.Semaphore(5) # Limit concurrency for scoring

    async def grade_item(item):
        async with sem:
            rubric_list = ", ".join(rubric_fields) if rubric_fields else ""
            grading_prompt = (
                f"You are a strict grader. Given the prompt and model response, return a JSON object with boolean fields: [{rubric_list}]. "
                f"Do not include any text before or after the JSON.\n"
                f"Prompt: {item['prompt']}\n"
                f"Response: {item['response']}"
            )
            try:
                raw = await adapter_fn(grading_prompt, config)
                start = raw.find("{"); end = raw.rfind("}")
                parsed = json.loads(raw[start:end+1]) if start >= 0 and end >= 0 else {}
            except Exception:
                parsed = {k: None for k in rubric_fields}
            return {**item, "scores": parsed}

    tasks = [grade_item(item) for item in results if item.get("success")]
    scored = await asyncio.gather(*tasks)

    # Write outputs
    try:
        with open(analysis_csv, "w", newline="", encoding="utf-8") as a_csv:
            writer = csv.writer(a_csv)
            writer.writerow(["id", "prompt", "response", "model"] + rubric_fields)
            for item in scored:
                scores = item.get("scores", {})
                writer.writerow([item.get("id"), item["prompt"], item["response"], item["model"]] + [scores.get(k) for k in rubric_fields])
        
        with open(analysis_json, "w", encoding="utf-8") as a_json:
            json.dump(scored, a_json, indent=2)
            
        print(f"Groq post-analysis written to {analysis_csv}")
    except Exception as e:
        print(f"Error writing analysis: {e}")

async def post_analyze_openrouter(results, config, suffix="all_models"):
    analysis_dir = os.path.join(config.get("output_dir", "outputs"), "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    analysis_csv = os.path.join(analysis_dir, f"openrouter_scores_{suffix}_{ts}.csv")
    analysis_json = os.path.join(analysis_dir, f"openrouter_scores_{suffix}_{ts}.json")

    adapter_fn = load_adapter("openrouter")
    rubric_fields = sorted({k for item in results for k in (item.get("eval_criteria") or {}).keys()})
    scored = []

    sem = asyncio.Semaphore(5)

    async def grade_item(item):
        async with sem:
            rubric_list = ", ".join(rubric_fields) if rubric_fields else ""
            grading_prompt = (
                f"You are a strict grader. Given the prompt and model response, return a JSON object with boolean fields: [{rubric_list}]. "
                f"Do not include any text before or after the JSON.\n"
                f"Prompt: {item['prompt']}\n"
                f"Response: {item['response']}"
            )
            config_override = dict(config or {})
            config_override["model_name"] = config_override.get("scoring_model_name", "openai/gpt-oss-20b:free")
            
            try:
                raw = await adapter_fn(grading_prompt, config_override)
                start = raw.find("{"); end = raw.rfind("}")
                parsed = json.loads(raw[start:end+1]) if start >= 0 and end >= 0 else {}
            except Exception:
                parsed = {k: None for k in rubric_fields}
            return {**item, "scores": parsed}

    tasks = [grade_item(item) for item in results if item.get("success")]
    scored = await asyncio.gather(*tasks)

    try:
        with open(analysis_csv, "w", newline="", encoding="utf-8") as a_csv:
            writer = csv.writer(a_csv)
            writer.writerow(["id", "prompt", "response", "model"] + rubric_fields)
            for item in scored:
                scores = item.get("scores", {})
                writer.writerow([item.get("id"), item["prompt"], item["response"], item["model"]] + [scores.get(k) for k in rubric_fields])
        
        with open(analysis_json, "w", encoding="utf-8") as a_json:
            json.dump(scored, a_json, indent=2)
            
        print(f"OpenRouter post-analysis written to {analysis_csv}")
    except Exception as e:
        print(f"Error writing analysis: {e}")

async def main_async():
    start_metrics_server()
    
    parser = argparse.ArgumentParser(description="Run PromptPressure Eval Suite (Async v1.7)")
    parser.add_argument("--multi-config", help="YAML config file(s)")
    parser.add_argument("--post-analyze", choices=["groq", "openrouter"], help="Optional post-analysis adapter")
    parser.add_argument("--schema", action="store_true", help="Dump JSON Schema for configuration and exit")
    
    # Plugin CLI commands
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")
    
    # 'plugins' command
    plugins_parser = subparsers.add_parser("plugins", help="Manage plugins")
    plugins_subparsers = plugins_parser.add_subparsers(dest="plugin_command")
    
    # 'plugins list'
    plugins_subparsers.add_parser("list", help="List available plugins")
    
    # 'plugins install <name>'
    install_parser = plugins_subparsers.add_parser("install", help="Install a plugin")
    install_parser.add_argument("name", help="Name of the plugin to install")

    args = parser.parse_args()

    if args.schema:
        from config import Settings
        print(json.dumps(Settings.model_json_schema(), indent=2))
        return

    # Handle Plugin CLI
    if args.command == "plugins":
        from plugins.core import PluginManager
        manager = PluginManager()
        
        if args.plugin_command == "list":
            print(f"{'Name':<20} {'Description':<50} {'Author':<15}")
            print("-" * 85)
            for p in manager.list_available_plugins():
                print(f"{p['name']:<20} {p['description']:<50} {p['author']:<15}")
            return
            
        elif args.plugin_command == "install":
            print(f"Installing plugin '{args.name}'...")
            success = manager.install_plugin(args.name)
            if success:
                print(f"Successfully installed '{args.name}'!")
            else:
                print(f"Failed to install '{args.name}'. Check logs for details.")
            return

    if not args.multi_config:
        parser.error("--multi-config is required unless --schema or a subcommand is used")


    all_results = []
    output_dirs = []
    all_metrics = []
    last_config = None

    for cfg_file in args.multi_config:
        from config import get_config
        config = get_config(cfg_file)
        config_dict = config.model_dump()
        last_config = config_dict

        results, out_dir, metrics_collector = await run_evaluation_suite(config_dict, config_dict.get("adapter"))
        all_results.extend(results)
        output_dirs.append(out_dir)
        if metrics_collector:
            all_metrics.append(metrics_collector.get_metrics())

    # Post Analysis
    if args.post_analyze:
        if args.post_analyze == "groq":
            await post_analyze_groq(all_results, last_config)
        elif args.post_analyze == "openrouter":
            await post_analyze_openrouter(all_results, last_config)
    elif len(args.multi_config) > 1:
        await post_analyze_openrouter(all_results, last_config)

    # Aggregated metrics (Legacy file support)
    if all_metrics:
        aggregated_metrics_path = os.path.join(last_config.get("output_dir", "outputs"), "aggregated_metrics.json")
        os.makedirs(os.path.dirname(aggregated_metrics_path), exist_ok=True)
        with open(aggregated_metrics_path, "w", encoding="utf-8") as f:
            json.dump(all_metrics, f, indent=2)

    # Custom Metrics
    if all_results and last_config and last_config.get("collect_metrics", True):
        # MetricsAnalyzer doesn't need to be async usually as it works on completed results
        analyzer = get_metrics_analyzer()
        custom_metrics = analyzer.calculate_metrics(all_results)
        report_path = analyzer.generate_report(custom_metrics, last_config.get("output_dir", "outputs"))
        print(f"Custom metrics report saved to {report_path}")

    # Report Gen
    if all_results and last_config:
        try:
            report_gen = ReportGenerator(last_config.get("output_dir", "outputs"), last_config)
            generated_reports = report_gen.generate(all_results, metrics=all_metrics[0] if all_metrics else None)
            for r in generated_reports:
                print(f"Report generated: {r}")
        except Exception as e:
            print(f"Failed to generate reports: {e}")

    stop_metrics_server()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
