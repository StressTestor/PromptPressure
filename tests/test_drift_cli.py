"""Integration tests for `pp run` / `pp calibrate` (no network)."""

import json
from pathlib import Path

import pytest

from promptpressure.drift import cli
from promptpressure.drift.schema import load_suite


def _flexible_fake_adapter():
    """Works as both a run adapter (text, config, messages=) and judge (prompt, config)."""
    async def fake(a, b=None, messages=None):
        return "reply"
    return fake


def test_run_writes_transcripts(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "load_adapter", lambda name: _flexible_fake_adapter())
    out = tmp_path / "run"
    rc = cli.main(["run", "--suite", "drift-v0.1", "--provider", "mock",
                   "--model", "m", "--out", str(out), "--concurrency", "4"])
    assert rc == 0
    payload = json.loads((out / "transcripts.json").read_text())
    assert payload["suite"] == "drift-v0.1"
    assert len(payload["transcripts"]) == 9  # all sequences ran
    # every sequence ran to completion with the fake
    assert all(r["error"] is None for r in payload["runs"].values())


def test_calibrate_writes_report(monkeypatch, tmp_path):
    # Patch the judge to deterministically echo the gold labels back, so the
    # CLI orchestration is exercised end-to-end and kappa is a known 1.0.
    suite = load_suite("drift-v0.1", strict=True)

    async def fake_judge_suite(sequences, transcripts, adapter_fn, cfg, concurrency=4):
        out = {}
        for seq in sequences:
            sid = seq["id"]
            if sid not in suite.gold:
                continue
            out[sid] = {"labels": [dict(r) for r in suite.gold[sid]["labels"]],
                        "parse_failures": 0}
        return out

    monkeypatch.setattr(cli, "judge_suite", fake_judge_suite)
    monkeypatch.setattr(cli, "load_adapter", lambda name: _flexible_fake_adapter())

    report_path = tmp_path / "method.md"
    rc = cli.main(["calibrate", "--suite", "drift-v0.1",
                   "--judge-provider", "mock", "--judge-model", "m",
                   "--runs", "2", "--bootstrap", "100",
                   "--report", str(report_path)])
    assert rc == 0
    assert report_path.exists()
    md = report_path.read_text()
    assert "judge-vs-human agreement" in md
    assert "the honest claim" in md
    data = json.loads(report_path.with_suffix(".json").read_text())
    # gold judged against gold -> perfect agreement
    assert data["judge_vs_human"]["overall"]["kappa"] == 1.0
    assert data["coverage"]["labeled_assistant_turns"] == 108


def test_calibrate_with_second_judge(monkeypatch, tmp_path):
    suite = load_suite("drift-v0.1", strict=True)

    async def fake_judge_suite(sequences, transcripts, adapter_fn, cfg, concurrency=4):
        return {s["id"]: {"labels": [dict(r) for r in suite.gold[s["id"]]["labels"]],
                          "parse_failures": 0}
                for s in sequences if s["id"] in suite.gold}

    monkeypatch.setattr(cli, "judge_suite", fake_judge_suite)
    monkeypatch.setattr(cli, "load_adapter", lambda name: _flexible_fake_adapter())

    report_path = tmp_path / "m.md"
    rc = cli.main(["calibrate", "--judge-provider", "a", "--judge-model", "x",
                   "--judge2-provider", "b", "--judge2-model", "y",
                   "--runs", "1", "--bootstrap", "50", "--report", str(report_path)])
    assert rc == 0
    data = json.loads(report_path.with_suffix(".json").read_text())
    assert "judge_vs_judge" in data
    assert "judge-vs-judge agreement" in report_path.read_text()


def test_launcher_dispatches_run(monkeypatch):
    import promptpressure.launcher as launcher
    captured = {}

    def fake_drift_main(argv):
        captured["argv"] = argv
        return 0

    import promptpressure.drift.cli as drift_cli
    monkeypatch.setattr(drift_cli, "main", fake_drift_main)
    monkeypatch.setattr("sys.argv", ["pp", "run", "--suite", "drift-v0.1",
                                     "--provider", "mock", "--model", "m"])
    rc = launcher.main()
    assert rc == 0
    assert captured["argv"][0] == "run"


def test_launcher_no_args_does_not_dispatch(monkeypatch):
    # `pp` with no args should NOT be treated as a drift subcommand.
    import promptpressure.launcher as launcher
    monkeypatch.setattr("sys.argv", ["pp"])
    # probe_existing_launcher would do real network; stub it + find_free_port path
    monkeypatch.setattr(launcher, "probe_existing_launcher", lambda r: 8000)
    monkeypatch.setattr("webbrowser.open", lambda url: True)
    rc = launcher.main()
    assert rc == 0  # took the launcher path, not the drift path
