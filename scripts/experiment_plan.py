#!/usr/bin/env python3
"""Validate and expand a design into NOT_RUN cases. Never executes simulations."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
KINDS = {"preflight", "geometry", "physics", "rules_fixture", "network",
         "protocol_fixture", "integration", "fault", "replay", "benchmark",
         "load", "manual", "evaluation"}
MAX_CASES = 100_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def finite(value: Any) -> None:
    if isinstance(value, float):
        require(math.isfinite(value), "Non-finite number")
    elif isinstance(value, dict):
        for item in value.values():
            finite(item)
    elif isinstance(value, list):
        for item in value:
            finite(item)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_plan(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    plan = json.loads(raw, object_pairs_hook=unique_object)
    validate(plan)
    return plan, hashlib.sha256(raw).hexdigest()


def count_batch(batch: dict[str, Any]) -> int:
    return math.prod(len(v) for v in batch["factors"].values()) * batch["seed_count"] * batch["repeats"]


def validate(plan: dict[str, Any]) -> dict[str, int]:
    require(isinstance(plan, dict), "Plan must be an object")
    finite(plan)
    require(type(plan.get("schema_version")) is int and plan["schema_version"] == 1,
            "Unsupported schema version")
    require(plan.get("status") == "DRAFT_NOT_EXECUTED", "Design cannot declare execution success")
    require(isinstance(plan.get("protocol_revision"), str) and bool(plan["protocol_revision"]),
            "Missing protocol_revision")
    timing = plan["timing"]
    for name, value in timing.items():
        require(type(value) in (int, float) and value > 0, f"Invalid timing {name}")
    dt = timing["physics_dt_s"]
    for key in ("decision_dt_s", "snapshot_dt_s", "match_limit_sim_s"):
        ratio = timing[key] / dt
        require(math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-8),
                f"Timing is not an integer number of physics steps: {key}")
    require(type(timing["consecutive_timeout_limit"]) is int, "Timeout count must be an integer")
    experiments = plan["experiments"]
    require(isinstance(experiments, list) and bool(experiments), "No experiments")
    counts: dict[str, int] = {}
    for exp in experiments:
        eid = exp["id"]
        require(isinstance(eid, str) and bool(IDENTIFIER.fullmatch(eid)), "Invalid experiment ID")
        require(eid not in counts, f"Duplicate experiment: {eid}")
        require(type(exp["cpu_release_required"]) is bool, "Missing release flag")
        require(isinstance(exp["batches"], list) and bool(exp["batches"]), "No batches")
        batch_ids: set[str] = set()
        total = 0
        for batch in exp["batches"]:
            bid = batch["id"]
            require(isinstance(bid, str) and bool(IDENTIFIER.fullmatch(bid)), "Invalid batch ID")
            require(bid not in batch_ids, f"Duplicate batch: {bid}")
            batch_ids.add(bid)
            require(batch["kind"] in KINDS, "Unknown case kind")
            for key, minimum in (("seed_start", 0), ("seed_count", 1), ("repeats", 1)):
                require(type(batch[key]) is int and batch[key] >= minimum, f"Invalid {key}")
            factors = batch["factors"]
            require(isinstance(factors, dict) and bool(factors), "Empty factors")
            for key, values in factors.items():
                require(bool(IDENTIFIER.fullmatch(key)), "Invalid factor name")
                require(isinstance(values, list) and bool(values), "Empty factor values")
                require(all(type(v) in (str, int, float) for v in values), "Factor values must be scalars")
                encoded = [json.dumps(v, sort_keys=True, allow_nan=False) for v in values]
                require(len(set(encoded)) == len(values), "Duplicate factor values")
            for key in ("duration_sim_s", "duration_wall_s"):
                if key in batch:
                    require(type(batch[key]) in (int, float) and batch[key] > 0, "Invalid duration")
            n = count_batch(batch)
            require(type(batch["expected_cases"]) is int and batch["expected_cases"] == n,
                    f"Wrong batch count: {eid}/{bid}")
            total += n
        require(type(exp["expected_cases"]) is int and exp["expected_cases"] == total,
                f"Wrong experiment count: {eid}")
        counts[eid] = total
        if eid == "E11":
            by_id = {b["id"]: b for b in exp["batches"]}
            require({"pilot", "confirmation"} <= set(by_id), "E11 requires two phases")
            p, c = by_id["pilot"], by_id["confirmation"]
            require(p["seed_start"] + p["seed_count"] <= c["seed_start"] or
                    c["seed_start"] + c["seed_count"] <= p["seed_start"],
                    "Pilot and confirmation seeds overlap")
    require(sum(counts.values()) <= MAX_CASES, "Schedule exceeds safe expansion limit")
    return counts


def iter_cases(plan: dict[str, Any], digest: str, experiment: str | None = None,
               batch_id: str | None = None) -> Iterator[dict[str, Any]]:
    validate(plan)
    require(bool(re.fullmatch(r"[0-9a-f]{64}", digest)), "Invalid plan SHA-256")
    selected = [e for e in plan["experiments"] if experiment is None or e["id"] == experiment]
    require(bool(selected), f"Unknown experiment: {experiment}")
    require(batch_id is None or experiment is not None, "--batch requires --experiment")
    if batch_id is not None:
        require(any(b["id"] == batch_id for b in selected[0]["batches"]), f"Unknown batch: {batch_id}")
    for exp in selected:
        for batch in exp["batches"]:
            if batch_id is not None and batch["id"] != batch_id:
                continue
            keys = sorted(batch["factors"])
            for values in itertools.product(*(batch["factors"][key] for key in keys)):
                for seed in range(batch["seed_start"], batch["seed_start"] + batch["seed_count"]):
                    for repeat in range(batch["repeats"]):
                        identity = {"experiment_id": exp["id"], "batch_id": batch["id"],
                                    "factors": dict(zip(keys, values)), "seed": seed,
                                    "repeat": repeat, "plan_sha256": digest}
                        raw = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False, allow_nan=False).encode()
                        yield {**identity,
                               "case_id": f'{exp["id"]}.{batch["id"]}.{hashlib.sha256(raw).hexdigest()[:20]}',
                               "kind": batch["kind"], "status": "NOT_RUN", "metrics": None,
                               "evidence": [], "cpu_release_required": exp["cpu_release_required"],
                               "duration_sim_s": batch.get("duration_sim_s"),
                               "duration_wall_s": batch.get("duration_wall_s"),
                               "source": batch.get("source")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "generate"))
    parser.add_argument("--plan", type=Path, default=ROOT / "experiments/plan.json")
    parser.add_argument("--experiment")
    parser.add_argument("--batch")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        plan, digest = load_plan(args.plan)
        if args.command == "validate":
            require(args.output is None and args.experiment is None and args.batch is None,
                    "Selection/output flags are only supported by generate")
            print(json.dumps({"plan_sha256": digest, "case_counts": validate(plan),
                              "scope": "DESIGN_VALIDATION_ONLY", "runtime": "NOT_RUN"}, indent=2))
        else:
            rows = list(iter_cases(plan, digest, args.experiment, args.batch))
            text = "".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows)
            if args.output:
                # Exclusive creation prevents overwriting evidence or an existing schedule.
                with args.output.open("x", encoding="utf-8") as stream:
                    stream.write(text)
                print(f"Generated {len(rows)} NOT_RUN cases: {args.output}")
            else:
                sys.stdout.write(text)
        return 0
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        print(f"Plan error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
