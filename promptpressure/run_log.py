"""Structured run log for PromptPressure eval runs.

Writes JSONL (one JSON object per line) to a log file alongside the
results output. Each line captures one request with: model, provider,
latency, tokens, cost, retry count, error type, and entry ID.

Usage:
    log = RunLog(output_dir)
    log.record(entry_id="tc_001", model="grok-4.20", provider="xai",
               latency=2.3, tokens={"prompt": 100, "completion": 50},
               cost=0.0003, retries=0, error=None, error_type=None,
               multi_turn=False, turns=1)
    log.close()
"""

import json
import os
from datetime import datetime


class RunLog:
    """Structured JSONL logger for eval run requests."""

    def __init__(self, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        self._path = os.path.join(output_dir, "run.jsonl")
        self._file = open(self._path, "w", encoding="utf-8")
        self._count = 0

        # write header line
        self._file.write(json.dumps({
            "type": "header",
            "ts": datetime.utcnow().isoformat() + "Z",
            "version": "1",
        }) + "\n")

    def record(self, entry_id, model, provider=None, latency=0.0,
               tokens=None, cost=None, retries=0,
               error=None, error_type=None,
               multi_turn=False, turns=1, batch=False):
        """Log a single request."""
        self._count += 1
        line = {
            "type": "request",
            "seq": self._count,
            "ts": datetime.utcnow().isoformat() + "Z",
            "entry_id": entry_id,
            "model": model,
            "provider": provider,
            "latency_s": round(latency, 3),
            "tokens": tokens or {},
            "cost_usd": round(cost, 6) if cost else None,
            "retries": retries,
            "error": error,
            "error_type": error_type,
            "multi_turn": multi_turn,
            "turns": turns,
            "batch": batch,
        }
        self._file.write(json.dumps(line) + "\n")

    def close(self):
        """Write summary line and close the file."""
        self._file.write(json.dumps({
            "type": "summary",
            "ts": datetime.utcnow().isoformat() + "Z",
            "total_requests": self._count,
        }) + "\n")
        self._file.close()

    @property
    def path(self):
        return self._path
