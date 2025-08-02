# added multi-model run, aggregated post-analysis, error logging

import os
import yaml
import argparse
import json
import csv
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from adapters import load_adapter


def log_error(output_dir, error_msg):
    """
    Appends error messages to an error log in the given directory.
    """
    log_path = os.path.join(output_dir, "error.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {error_msg}\n")


def run_evaluation_suite(config, adapter_name):
    """
    Runs the evaluation suite for a given config and adapter.
    Returns a list of result dicts containing prompt, response, model, is_simulation.
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

    print(f"Evaluating model '{model_name}' using adapter '{adapter_name}' with {len(prompts)} prompts...")

    # Prepare output paths
    csv_filename = config.get("output")
    csv_path = os.path.join(output_dir, csv_filename)
    json_path = os.path.splitext(csv_path)[0] + ".json"

    with open(csv_path, "w", newline="", encoding="utf-8") as out_csv:
        writer = csv.writer(out_csv)
        writer.writerow(["prompt", "response", "model", "is_simulation"])

        for entry in prompts:
            prompt_text = entry.get("prompt") or entry.get("input")
            if not prompt_text:
                warning = f"Skipping malformed entry: {entry}"
                print(warning)
                log_error(output_dir, warning)
                continue
            try:
                response = adapter_fn(prompt_text, config)
                row = [prompt_text, response, model_name, config.get("is_simulation", False)]
                writer.writerow(row)
                results.append({
                    "prompt": prompt_text,
                    "response": response,
                    "model": model_name,
                    "is_simulation": config.get("is_simulation", False)
                })
            except Exception as e:
                err = f"Error on prompt '{prompt_text[:30]}...': {e}\n{traceback.format_exc()}"
                print(err)
                log_error(output_dir, err)

    # Write JSON output
    with open(json_path, "w", encoding="utf-8") as out_json:
        json.dump(results, out_json, indent=2)

    return results, output_dir


def post_analyze_groq(results, config, suffix="all_models"):
    """Sends each <prompt, response> pair to the Groq adapter for rubric-based scoring.
    
    Args:
        results: List of evaluation results
        config: Configuration dictionary (converted from Settings object)
        suffix: Output file suffix
    
    Outputs a CSV and JSON in an analysis subfolder, aggregated across all models.
    """
    analysis_dir = os.path.join(config.get("output_dir", "outputs"), "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    analysis_csv = os.path.join(analysis_dir, f"groq_scores_{suffix}{ts}.csv")
    analysis_json = os.path.join(analysis_dir, f"groq_scores{suffix}_{ts}.json")

    adapter_fn = load_adapter("groq")
    # Collect rubric fields dynamically
    rubric_fields = sorted({k for item in results for k in (item.get("eval_criteria") or {}).keys()})
    scored = []

    def grade_item(item):
        rubric_list = ", ".join(rubric_fields) if rubric_fields else ""
        grading_prompt = (
            f"You are a strict grader. Given the prompt and model response, return a JSON object with boolean fields: [{rubric_list}]. "
            f"Do not include any text before or after the JSON.\n"
            f"Prompt: {item['prompt']}\n"
            f"Response: {item['response']}"
        )
        raw = adapter_fn(grading_prompt, config)
        try:
            # Be tolerant: find first/last braces if model adds extra text
            start = raw.find("{"); end = raw.rfind("}")
            parsed = json.loads(raw[start:end+1]) if start >= 0 and end >= 0 else {}
        except Exception:
            parsed = {k: None for k in rubric_fields}
        return parsed

    try:
        with open(analysis_csv, "w", newline="", encoding="utf-8") as a_csv:
            writer = csv.writer(a_csv)
            writer.writerow(["id", "prompt", "response", "model"] + rubric_fields)
            for item in results:
                scores = grade_item(item)
                writer.writerow([item.get("id"), item["prompt"], item["response"], item["model"]] + [scores.get(k) for k in rubric_fields])
                scored.append({**item, "scores": scores})

        with open(analysis_json, "w", encoding="utf-8") as a_json:
            json.dump(scored, a_json, indent=2)

        print(f"Groq post-analysis written to {analysis_csv} and {analysis_json}")
    except Exception as e:
        err = f"Error during post-analysis: {e}\n{traceback.format_exc()}"
        print(err)
        log_error(analysis_dir, err)
        scored = []

def post_analyze_openai(results, config, suffix="all_models"):
    """Sends each <prompt, response> pair to the OpenAI adapter for rubric-based scoring.
    
    Args:
        results: List of evaluation results
        config: Configuration dictionary (converted from Settings object)
        suffix: Output file suffix
    
    Outputs a CSV and JSON in an analysis subfolder, aggregated across all models.
    """
    analysis_dir = os.path.join(config.get("output_dir", "outputs"), "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    analysis_csv = os.path.join(analysis_dir, f"openai_scores_{suffix}{ts}.csv")
    analysis_json = os.path.join(analysis_dir, f"openai_scores{suffix}_{ts}.json")

    # Create a copy of config with OpenAI-specific settings
    openai_config = config.copy()
    openai_config["model_name"] = "gpt-4o-mini"  # Use GPT-4o-mini for analysis
    
    adapter_fn = load_adapter("openai")
    # Collect rubric fields dynamically
    rubric_fields = sorted({k for item in results for k in (item.get("eval_criteria") or {}).keys()})
    scored = []

    def grade_item(item):
        rubric_list = ", ".join(rubric_fields) if rubric_fields else ""
        grading_prompt = (
            f"You are a strict grader. Given the prompt and model response, return a JSON object with boolean fields: [{rubric_list}]. "
            f"Do not include any text before or after the JSON.\n"
            f"Prompt: {item['prompt']}\n"
            f"Response: {item['response']}"
        )
        raw = adapter_fn(grading_prompt, openai_config)
        try:
            # Be tolerant: find first/last braces if model adds extra text
            start = raw.find("{"); end = raw.rfind("}")
            parsed = json.loads(raw[start:end+1]) if start >= 0 and end >= 0 else {}
        except Exception:
            parsed = {k: None for k in rubric_fields}
        return parsed

    try:
        with open(analysis_csv, "w", newline="", encoding="utf-8") as a_csv:
            writer = csv.writer(a_csv)
            writer.writerow(["id", "prompt", "response", "model"] + rubric_fields)
            for item in results:
                scores = grade_item(item)
                writer.writerow([item.get("id"), item["prompt"], item["response"], item["model"]] + [scores.get(k) for k in rubric_fields])
                scored.append({**item, "scores": scores})

        with open(analysis_json, "w", encoding="utf-8") as a_json:
            json.dump(scored, a_json, indent=2)

        print(f"OpenAI post-analysis written to {analysis_csv} and {analysis_json}")
    except Exception as e:
        err = f"Error during post-analysis: {e}\n{traceback.format_exc()}"
        print(err)
        log_error(analysis_dir, err)
        scored = []
    return scored


def main():
    parser = argparse.ArgumentParser(description="Run PromptPressure Eval Suite with aggregated post-analysis and error logging.")
    parser.add_argument("--multi-config", required=True, nargs='+', help="YAML config file(s) to use")
    parser.add_argument("--post-analyze", choices=["groq", "openai"], help="Optional post-analysis adapter")
    args = parser.parse_args()

    all_results = []
    output_dirs = []
    last_config = None

    for cfg_file in args.multi_config:
        # Use Settings object instead of raw YAML config
        from config import get_config
        config = get_config(cfg_file)
        # Convert to dict for backward compatibility
        config_dict = config.model_dump()
        last_config = config_dict

        results, out_dir = run_evaluation_suite(config_dict, config_dict.get("adapter"))
        all_results.extend(results)
        output_dirs.append(out_dir)

    # After all runs, perform post-analysis if conditions met
    if args.post_analyze == "groq" or args.post_analyze == "openai" or len(args.multi_config) > 1:
        if args.post_analyze == "openai" or (args.post_analyze is None and len(args.multi_config) > 1):
            post_analyze_openai(all_results, last_config)
        else:
            post_analyze_groq(all_results, last_config)

if __name__ == "__main__":
    main()
