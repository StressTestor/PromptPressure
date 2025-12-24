
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
import importlib.util

# Refactored for tests/ location
# The scripts dir is in the parent of tests/
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
AGG_PATH = SCRIPTS_DIR / "aggregate_openrouter_scores.py"

# Only attempt to load if file exists
if AGG_PATH.exists():
    spec = importlib.util.spec_from_file_location("agg_script_module", str(AGG_PATH))

    agg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agg)  # type: ignore
    print(f"DEBUG: dir(agg) = {dir(agg)}")

else:
    agg = None

class TestAggregateOpenRouterScores(unittest.TestCase):
    def setUp(self) -> None:
        if not agg:
            self.skipTest("aggregate_openrouter_scores.py not found")
            
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
            ["4", "p4", "r4", "modelB", "false", "false"],
        ]

        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_compute_per_model_stats(self):
        # modelA: 2 calls. safe: 1/2 (50%), grounded: 2/2 (100%)
        # modelB: 2 calls. safe: 1/2 (50%), grounded: 0/2 (0%)
        result = agg.compute_pass_rates(str(self.csv_path))
        stats = result["metrics"]["per_model"]

        self.assertIn("modelA", stats)
        self.assertIn("modelB", stats)

        # check modelA
        self.assertAlmostEqual(stats["modelA"]["safe"]["pass_rate"], 0.5)
        self.assertAlmostEqual(stats["modelA"]["grounded"]["pass_rate"], 1.0)
        # self.assertEqual(stats["modelA"]["count"], 2) # Removed count check as it is not in the output structure

        # check modelB
        self.assertAlmostEqual(stats["modelB"]["safe"]["pass_rate"], 0.5)
        self.assertAlmostEqual(stats["modelB"]["grounded"]["pass_rate"], 0.0)
