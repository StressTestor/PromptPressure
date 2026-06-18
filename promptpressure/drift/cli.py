"""`pp run` / `pp calibrate` -- the drift suite command line.

    pp run --suite drift-v0.1 --provider deepseek --model deepseek-chat
        replay every sequence through the model under test, save transcripts.

    pp calibrate --suite drift-v0.1 --judge-provider deepseek --judge-model deepseek-chat --runs 3
        judge the gold reference transcripts N times, compute judge-vs-human
        agreement + test-retest stability, write reports/<suite>-method.md.

Both subcommands are also reachable as `ppdrift run ...` and dispatched from
the `pp` launcher when its first argument is `run` or `calibrate`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from promptpressure.adapters import load_adapter
from promptpressure.drift import pipeline, report, runner
from promptpressure.drift.judge import judge_suite
from promptpressure.drift.schema import load_suite

load_dotenv()


def _build_config(model: str, temperature: float | None, api_key: str | None, provider: str) -> dict:
    cfg: dict = {"adapter": provider, "model": model, "model_name": model}
    if temperature is not None:
        cfg["temperature"] = temperature
    if api_key:
        cfg[f"{provider}_api_key"] = api_key
    return cfg


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


async def cmd_run(args) -> int:
    suite = load_suite(args.suite, strict=True)
    adapter_fn = load_adapter(args.provider)
    cfg = _build_config(args.model, args.temperature, None, args.provider)

    print(f"running suite {suite.name}: {len(suite.sequences)} sequences "
          f"through {args.provider}/{args.model}")
    result = await runner.run_suite(
        suite.sequences, adapter_fn, cfg,
        concurrency=args.concurrency, turn_delay=args.turn_delay, timeout=args.timeout,
    )

    out_dir = Path(args.out or f"outputs/drift/{suite.name}/{args.provider}-{_stamp()}")
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "suite": suite.name,
        "provider": args.provider,
        "model": args.model,
        "transcripts": result["transcripts"],
        "runs": result["runs"],
    }
    with open(out_dir / "transcripts.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    completed = sum(r["completed"] for r in result["runs"].values())
    total = sum(r["total"] for r in result["runs"].values())
    failed = [sid for sid, r in result["runs"].items() if r["error"]]
    print(f"done in {result['elapsed']:.1f}s: {completed}/{total} turns completed")
    if failed:
        print(f"  sequences with errors: {', '.join(failed)}")
    print(f"  transcripts -> {out_dir / 'transcripts.json'}")
    return 0


def _load_transcripts(suite, args) -> tuple[dict, str]:
    """Return (transcripts_by_id, source_label). Defaults to gold transcripts."""
    if args.transcripts:
        with open(args.transcripts, encoding="utf-8") as f:
            data = json.load(f)
        transcripts = data.get("transcripts", data)
        label = f"{data.get('provider','?')}/{data.get('model','?')}"
        return transcripts, label
    # default: judge the gold reference transcripts
    transcripts = {sid: g["transcript"] for sid, g in suite.gold.items()}
    return transcripts, "gold reference transcripts"


async def _judge_n_times(suite, transcripts, provider, model, temperature, runs, concurrency) -> list[dict]:
    adapter_fn = load_adapter(provider)
    cfg = _build_config(model, temperature, None, provider)
    out = []
    for i in range(runs):
        print(f"  judge run {i + 1}/{runs} ({provider}/{model}) ...")
        run = await judge_suite(suite.sequences, transcripts, adapter_fn, cfg, concurrency=concurrency)
        out.append(run)
    return out


async def cmd_calibrate(args) -> int:
    suite = load_suite(args.suite, strict=True)
    if not suite.gold:
        print(f"suite {suite.name} has no gold labels; cannot calibrate.", file=sys.stderr)
        return 2

    transcripts, source = _load_transcripts(suite, args)
    print(f"calibrating judge on {suite.name}: judging {source} "
          f"with {args.judge_provider}/{args.judge_model} x{args.runs}")

    judge_runs = await _judge_n_times(
        suite, transcripts, args.judge_provider, args.judge_model,
        args.temperature, args.runs, args.concurrency,
    )

    judge_runs_b = None
    if args.judge2_provider and args.judge2_model:
        print(f"  second judge {args.judge2_provider}/{args.judge2_model} for judge-vs-judge ...")
        judge_runs_b = await _judge_n_times(
            suite, transcripts, args.judge2_provider, args.judge2_model,
            args.temperature, 1, args.concurrency,
        )

    result = pipeline.run_calibration(
        suite, judge_runs, judge_runs_b=judge_runs_b,
        judge_name=f"{args.judge_provider}/{args.judge_model}",
        judge_b_name=f"{args.judge2_provider}/{args.judge2_model}" if judge_runs_b else "judge-B",
        n_boot=args.bootstrap, seed=args.seed,
    )
    result["transcript_source"] = source
    result["judge_temperature"] = args.temperature

    report_path = Path(args.report or f"reports/{suite.name}-method.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    md = report.render_method_report(result, model_under_test=source, generated=_stamp())
    report_path.write_text(md, encoding="utf-8")

    json_path = report_path.with_suffix(".json")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    overall = result["judge_vs_human"]["overall"]
    print(f"\njudge-vs-human pooled kappa: {overall['kappa']:.3f} "
          f"({overall['band']}), CI {report._fmt_ci(overall['kappa_ci'])}, n={overall['n']}")
    tr = result.get("test_retest", {}).get("overall")
    if tr and tr.get("mean_kappa") is not None:
        print(f"test-retest pooled mean kappa: {tr['mean_kappa']:.3f} over {result['test_retest']['n_runs']} runs")
    print(f"report  -> {report_path}")
    print(f"json    -> {json_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pp", description="PromptPressure drift suite")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a drift suite through a model -> transcripts")
    run.add_argument("--suite", default="drift-v0.1")
    run.add_argument("--provider", required=True, help="adapter name (deepseek, openrouter, ollama, mock, ...)")
    run.add_argument("--model", required=True)
    run.add_argument("--temperature", type=float, default=None)
    run.add_argument("--concurrency", type=int, default=3)
    run.add_argument("--turn-delay", type=float, default=0.0)
    run.add_argument("--timeout", type=float, default=90.0)
    run.add_argument("--out", default=None, help="output dir (default outputs/drift/<suite>/...)")

    cal = sub.add_parser("calibrate", help="measure judge reliability on a suite")
    cal.add_argument("--suite", default="drift-v0.1")
    cal.add_argument("--judge-provider", required=True)
    cal.add_argument("--judge-model", required=True)
    cal.add_argument("--runs", type=int, default=3, help="judge runs for test-retest (default 3)")
    cal.add_argument("--judge2-provider", default=None, help="optional second judge for judge-vs-judge")
    cal.add_argument("--judge2-model", default=None)
    cal.add_argument("--transcripts", default=None,
                     help="transcripts.json from `pp run` (default: judge the gold reference transcripts)")
    cal.add_argument("--temperature", type=float, default=0.0)
    cal.add_argument("--concurrency", type=int, default=4)
    cal.add_argument("--bootstrap", type=int, default=2000)
    cal.add_argument("--seed", type=int, default=0)
    cal.add_argument("--report", default=None, help="report path (default reports/<suite>-method.md)")
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return asyncio.run(cmd_run(args))
    if args.command == "calibrate":
        return asyncio.run(cmd_calibrate(args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
