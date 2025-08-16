"""
Unit tests for scripts/aggregate_openrouter_scores.py (stdlib-only).

Uses a temporary CSV to validate pass-rate computation and output writing.
Run:
    python -m unittest -v test_aggregate_openrouter_scores.py
"""

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
import importlib.util

# Dynamically load the aggregator module from scripts/ without requiring it to be a package
ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
AGG_PATH = SCRIPTS_DIR / "aggregate_openrouter_scores.py"

spec = importlib.util.spec_from_file_location("aggregate_openrouter_scores", str(AGG_PATH))
agg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agg)  # type: ignore


class TestAggregateOpenRouterScores(unittest.TestCase):
    def setUp(self) -> None:
        # Temporary workspace
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.csv_path = self.tmp_path / "openrouter_scores_all_models_2025-01-01_00-00-00.csv"

        # Create a synthetic combined CSV with two boolean metric columns
        header = [
            "id",
            "prompt",
            "response",
            "model",
            "safe",
            "grounded",
        ]
        rows = [
            ["1", "p1", "r1", "modelA", "true", "true"],
            ["2", "p2", "r2", "modelA", "false", "true"],
            ["3", "p3", "r3", "modelB", "true", "false"],
            ["4", "p4", "r4", "modelB", "", "true"],  # blank should be ignored
            ["5", "p5", "r5", "modelB", "notabool", "false"],  # non-bool ignored for 'safe'
        ]
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_compute_pass_rates(self):
        result = agg.compute_pass_rates(str(self.csv_path))
        self.assertIn("metrics", result)
        metrics = result["metrics"]
        per_model = metrics["per_model"]
        overall = metrics["overall"]

        # Model A: safe: 1/2 true; grounded: 2/2 true
        self.assertEqual(per_model["modelA"]["safe"]["passed"], 1)
        self.assertEqual(per_model["modelA"]["safe"]["total"], 2)
        self.assertAlmostEqual(per_model["modelA"]["safe"]["pass_rate"], 0.5)

        self.assertEqual(per_model["modelA"]["grounded"]["passed"], 2)
        self.assertEqual(per_model["modelA"]["grounded"]["total"], 2)
        self.assertAlmostEqual(per_model["modelA"]["grounded"]["pass_rate"], 1.0)

        # Model B: safe: only one boolean 'true' counted (others ignored), so 1/1
        self.assertEqual(per_model["modelB"]["safe"]["passed"], 1)
        self.assertEqual(per_model["modelB"]["safe"]["total"], 1)
        self.assertAlmostEqual(per_model["modelB"]["safe"]["pass_rate"], 1.0)

        # Model B: grounded: false + true => 1/2
        self.assertEqual(per_model["modelB"]["grounded"]["passed"], 1)
        self.assertEqual(per_model["modelB"]["grounded"]["total"], 2)
        self.assertAlmostEqual(per_model["modelB"]["grounded"]["pass_rate"], 0.5)

        # Overall: safe: (1 + 1) / (2 + 1) = 2/3 ≈ 0.6667
        self.assertEqual(overall["safe"]["passed"], 2)
        self.assertEqual(overall["safe"]["total"], 3)
        self.assertAlmostEqual(overall["safe"]["pass_rate"], 2/3)

        # Overall: grounded: (2 + 1) / (2 + 2) = 3/4 = 0.75
        self.assertEqual(overall["grounded"]["passed"], 3)
        self.assertEqual(overall["grounded"]["total"], 4)
        self.assertAlmostEqual(overall["grounded"]["pass_rate"], 0.75)

    def test_write_outputs(self):
        result = agg.compute_pass_rates(str(self.csv_path))
        json_out, csv_out = agg.write_outputs(result, str(self.tmp_path))

        # Files exist
        self.assertTrue(os.path.exists(json_out))
        self.assertTrue(os.path.exists(csv_out))

        # JSON structure round-trips
        data = json.loads(Path(json_out).read_text(encoding="utf-8"))
        self.assertIn("metrics", data)

        # CSV rows include overall and per-model lines with formatted pass_rate
        with open(csv_out, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertTrue(any(r["model"] == "__overall__" for r in rows))
            # Ensure formatted pass_rate with four decimals or blank
            for r in rows:
                pr = r["pass_rate"]
                self.assertTrue(pr == "" or "." in pr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
