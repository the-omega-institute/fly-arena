"""Tests cover plan integrity only, never physics, performance or deployment."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("experiment_plan", ROOT / "scripts/experiment_plan.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.digest = m.load_plan(ROOT / "experiments/plan.json")

    def test_counts(self):
        self.assertEqual(m.validate(self.plan), {
            "E00": 2, "E01": 80, "E02": 100, "E03": 100, "E04": 102, "E05": 40,
            "E06": 40, "E07": 36, "E08": 60, "E09": 72, "E10": 27, "E11": 1440})

    def test_unique_and_deterministic(self):
        rows = list(m.iter_cases(self.plan, self.digest))
        self.assertEqual(len(rows), sum(m.validate(self.plan).values()))
        self.assertEqual(len(rows), len({r["case_id"] for r in rows}))
        self.assertEqual(rows, list(m.iter_cases(self.plan, self.digest)))

    def test_no_results_fabricated(self):
        for row in m.iter_cases(self.plan, self.digest):
            self.assertEqual(row["status"], "NOT_RUN")
            self.assertIsNone(row["metrics"])
            self.assertEqual(row["evidence"], [])
        status = json.loads((ROOT / "experiments/status.json").read_text())
        self.assertEqual(set(status["experiments"]), set(m.validate(self.plan)))
        self.assertTrue(all(v["status"] == "NOT_RUN" for v in status["experiments"].values()))

    def test_phase_filter(self):
        self.assertEqual(len(list(m.iter_cases(self.plan, self.digest, "E11", "pilot"))), 360)
        self.assertEqual(len(list(m.iter_cases(self.plan, self.digest, "E11", "confirmation"))), 1080)

    def test_pairing(self):
        rows = list(m.iter_cases(self.plan, self.digest, "E05"))
        groups = {}
        for row in rows:
            f = row["factors"]
            key = (f["route"], f["map"], f["pair"], row["seed"])
            groups.setdefault(key, []).append(f["spawn_assignment"])
        self.assertTrue(all(sorted(v) == ["ab", "ba"] for v in groups.values()))

    def test_duplicate_ids_rejected(self):
        self.plan["experiments"].append(copy.deepcopy(self.plan["experiments"][0]))
        with self.assertRaises(ValueError): m.validate(self.plan)

    def test_invalid_counts_rejected(self):
        for bad in (0, -1, True, 1.5):
            plan = copy.deepcopy(self.plan)
            plan["experiments"][0]["batches"][0]["seed_count"] = bad
            with self.assertRaises(ValueError): m.validate(plan)

    def test_nonfinite_and_fractional_timing_rejected(self):
        for bad in (float("nan"), float("inf"), 0.10001):
            plan = copy.deepcopy(self.plan)
            plan["timing"]["decision_dt_s"] = bad
            with self.assertRaises(ValueError): m.validate(plan)

    def test_duplicate_factor_rejected(self):
        self.plan["experiments"][0]["batches"][0]["factors"]["host"].append("remote_server")
        with self.assertRaises(ValueError): m.validate(self.plan)

    def test_overlapping_confirmation_rejected(self):
        self.plan["experiments"][-1]["batches"][1]["seed_start"] = 4005
        with self.assertRaises(ValueError): m.validate(self.plan)

    def test_incorrect_declared_count_rejected(self):
        self.plan["experiments"][0]["expected_cases"] = 999
        with self.assertRaises(ValueError): m.validate(self.plan)

    def test_invalid_selection_rejected(self):
        for exp, batch in (("E99", None), ("E05", "unknown"), (None, "pilot")):
            with self.assertRaises(ValueError): list(m.iter_cases(self.plan, self.digest, exp, batch))

    def test_json_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaises(ValueError): m.load_plan(path)

    def test_plan_hash_is_exact_file_hash(self):
        self.assertEqual(self.digest, hashlib.sha256((ROOT / "experiments/plan.json").read_bytes()).hexdigest())

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e05.jsonl"
            cmd = [sys.executable, str(ROOT / "scripts/experiment_plan.py"), "generate",
                   "--experiment", "E05", "--output", str(path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(path.read_text().splitlines()), 40)
            content = path.read_bytes()
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
