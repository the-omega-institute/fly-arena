"""Strict, evidence-derived admission policy. This module never runs a trial.

A qualification is a reproducible summary, not an authority for its own gates.
All eight receipts and observations are reverified on every admission decision.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ..common import canonical, digest, file_sha
from .probes import make_scene, measured_metrics, runtime_closure, verify_evidence
from .checkpoints import require_checkpoint_versions

SCHEMA = "motor-qualification/v4"
CASES = (
    ("heldout-left", "gradient-v2", 20042, 10, {}),
    ("heldout-right", "gradient-v2", 20043, 10, {}),
    ("heldout-repeat", "gradient-v2", 20042, 10, {}),
    ("bifurcation-left", "bifurcation-v2", 20044, 10, {}),
    ("bifurcation-right", "bifurcation-v2", 20045, 10, {}),
    ("blank", "gradient-v2", 20042, 3, {"stimulus": "blank"}),
    ("output-ablation", "gradient-v2", 20042, 3, {"ablation": "output"}),
    ("delayed-cue", "delayed-cue-v2", 20042, 3, {}),
)
TRIALS = frozenset(case[0] for case in CASES)
GATES = frozenset({
    "heldout-left-long-approach", "heldout-left-direction",
    "heldout-right-long-approach", "heldout-right-direction",
    "bifurcation-left-choice-and-food", "bifurcation-left-upright",
    "bifurcation-right-choice-and-food", "bifurcation-right-upright",
    "repeat-identical", "blank-and-ablation-passive", "blank-stop",
    "output-ablation-stop", "cue-offset-stop", "fullgraph", "final-source",
})
FIELDS = frozenset({"schema_version", "profile_sha256", "policy_sha256", "checks",
                    "receipts", "metrics", "measured", "sha256"})
# Frozen unmodified WT on the retained MaleCNS graph, shared by all eight trials.
# Identity comes from canonical compiler/reference artifacts, not report labels.
WT_ARTIFACT = "aaf1fb32e763e7bda8b34bea1519e1041e9b73b07bed6b5dc1c4552840785bd7"
WT_FLY = "0c136a17a43c84c2eb32539454285783"
GRAPH = "473ff8f53214a9a6fecf5b866c4bb11bf6302c938e569898d2ce03fbf3917ccc"
TRAJECTORY_FIELDS = {"time", "x", "y", "yaw"}
TRACE_FIELDS = {"time", "z", "upright_z", "total_spikes", "olfactory", "projection",
                "local", "memory", "readout", "descending", "visual", "motor",
                "raw_odor_left", "raw_odor_right", "encoded_odor_left", "encoded_odor_right",
                "command_left", "command_right", "drive_left", "drive_right", "game_energy",
                "food_intake", "wall_contact_ticks"}
EVIDENCE_FIELDS = {"schema_version", "fly_id", "artifact_id", "condition_key", "probe_id",
                   "seed", "duration_seconds", "trajectory", "metrics", "neural_trace", "profile", "scene"}
RECEIPT_FIELDS = {"schema_version", "conditions", "subject", "neuron_count", "edge_count",
                  "final_tick", "total_spikes", "wall_seconds", "files", "sha256"}


def _keys(value, expected, label):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(f"Invalid {label}: missing or unknown fields")


def _same(actual, expected, label):
    # Canonical JSON distinguishes booleans, integers, floats, null and strings;
    # Python's == alone would accept True == 1 and 10 == 10.0.
    if canonical(actual) != canonical(expected):
        raise ValueError(f"Qualification {label} mismatch")


def _read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Nonfinite JSON value: {value}")

    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def _sha(value, label):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"Invalid {label} SHA-256")


def _number(value, label, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value):
        raise ValueError(f"Invalid {label} numeric type")


def _observations(evidence, seconds):
    for key, fields in (("trajectory", TRAJECTORY_FIELDS), ("neural_trace", TRACE_FIELDS)):
        rows = evidence[key]
        if type(rows) is not list or len(rows) != seconds * 100 + 1:
            raise ValueError(f"Incomplete {key} horizon")
        for index, row in enumerate(rows):
            _keys(row, fields, key)
            for field, value in row.items():
                _number(value, f"{key}.{field}", integer=field == "wall_contact_ticks")
            if abs(row["time"] - index * .01) > 1e-10:
                raise ValueError(f"Invalid {key} time grid")


def _document(document, expected_profile, policy_sha):
    _keys(document, FIELDS, "qualification")
    _same(document["schema_version"], SCHEMA, "schema")
    _same(document["profile_sha256"], digest(expected_profile), "current scientific profile")
    _same(document["policy_sha256"], policy_sha, "evaluator source")
    _keys(document["checks"], GATES, "gate set")
    if any(type(v) is not bool for v in document["checks"].values()):
        raise ValueError("Qualification gates must be strict booleans")
    for key in ("receipts", "metrics"):
        _keys(document[key], TRIALS, key)
    for value in document["receipts"].values():
        _sha(value, "receipt")
    _keys(document["measured"], {"heldout-left", "heldout-right"}, "measured")
    _sha(document["sha256"], "qualification")
    _same(document["sha256"], digest({k: v for k, v in document.items() if k != "sha256"}), "digest")


def _build(root: Path, expected_profile: dict) -> dict:
    root = root.resolve()
    policy_sha = file_sha(Path(__file__))
    closure = runtime_closure()
    if (expected_profile.get("ready") is not True
            or expected_profile.get("id") != "sensorimotor-research-v2"
            or expected_profile.get("actual_backend") != "cpu-numba"
            or expected_profile.get("protocol_id") != "probe-protocol-v3"
            or not expected_profile.get("motor_id", "").startswith("dn-cpg-")
            or not expected_profile["motor_id"].endswith("-v4")):
        raise ValueError("Qualification requires a ready versioned v4 neural motor profile")
    _same(expected_profile["hashes"]["runtime_closure"], digest(closure), "current source closure")
    require_checkpoint_versions(expected_profile, closure)
    _same(expected_profile["hashes"]["connectome"], GRAPH, "retained graph")
    reports, receipts, metrics = {}, {}, {}
    for name, probe, seed, seconds, options in CASES:
        folder = root / name
        if folder.is_symlink() or not folder.resolve().is_relative_to(root):
            raise ValueError("Invalid qualification trial path")
        # No externally redirected receipt or checkpoint may stand in for a trial.
        for filename in ("receipt.json", "report.json", "evidence.json", "scene.json", "events.json", "brain.npz", "physics.npz"):
            if (folder / filename).is_symlink():
                raise ValueError("Invalid qualification evidence symlink")
        receipt = _read(folder / "receipt.json")
        report = _read(folder / "report.json")
        evidence = _read(folder / "evidence.json")
        _keys(receipt, RECEIPT_FIELDS, "receipt")
        _keys(evidence, EVIDENCE_FIELDS, "evidence")
        _keys(report, EVIDENCE_FIELDS | {"receipt_sha256", "status"}, "report")
        _same(receipt["schema_version"], "probe-receipt/v2", "receipt schema")
        _same(evidence["schema_version"], "probe-report/v2", "report schema")
        _same(report, evidence | {"receipt_sha256": receipt["sha256"], "status": "complete"}, "complete report")
        conditions = {"profile": expected_profile, "runtime": closure, "scene": make_scene(probe, seed),
                      "seed": seed, "duration_seconds": seconds, "probe_id": probe,
                      "ablation": options.get("ablation"), "stimulus": options.get("stimulus", "normal"),
                      "decoder_version": "v2"}
        _same(receipt["conditions"], conditions, f"{name} conditions")
        for key in ("profile", "scene", "seed", "duration_seconds", "probe_id"):
            _same(evidence[key], conditions[key], f"{name} {key}")
        _same(evidence["condition_key"], digest(conditions), "condition digest")
        subject = receipt["subject"]
        _keys(subject, {"fly_id", "artifact_id", "weights_sha256", "phenotype"}, "subject")
        _same(subject["artifact_id"], WT_ARTIFACT, "baseline artifact")
        _same(subject["fly_id"], WT_FLY, "baseline reference")
        _same(digest(subject["phenotype"]), WT_ARTIFACT, "baseline phenotype")
        _same(subject["weights_sha256"], subject["phenotype"]["weights_sha256"], "baseline weights")
        for key in ("fly_id", "artifact_id"):
            _same(evidence[key], subject[key], "report subject")
        for key in ("neuron_count", "edge_count", "final_tick", "total_spikes"):
            _number(receipt[key], key, integer=True)
        _number(receipt["wall_seconds"], "wall_seconds")
        _same(receipt["neuron_count"], 165122, "retained neuron count")
        _same(receipt["edge_count"], 25563197, "retained edge count")
        _observations(evidence, seconds)
        # Hashes, checkpoints, ticks, full time grids, scene, metrics and profile.
        verified = verify_evidence(folder, report)
        _same(verified, evidence, "verified observations")
        metrics[name] = measured_metrics(evidence["trajectory"], evidence["neural_trace"], conditions["scene"])
        _same(evidence["metrics"], metrics[name], "recomputed metrics")
        reports[name], receipts[name] = evidence, receipt

    checks, measured = {}, {}
    for name in ("heldout-left", "heldout-right"):
        report = reports[name]
        trajectory = report["trajectory"]
        goal = np.array(report["scene"]["food"][0]["position"][:2])
        distance = np.linalg.norm(np.array([[p["x"], p["y"]] for p in trajectory]) - goal, axis=1)
        yaw = np.unwrap([p["yaw"] for p in trajectory])
        measured[name] = {"closest_distance_mm": float(distance.min()), "initial_distance_mm": float(distance[0]),
                          "yaw_at_half_second": float(yaw[50] - yaw[0]), "horizon": report["duration_seconds"]}
        checks[name + "-long-approach"] = bool(report["duration_seconds"] >= 8 and distance.min() < 1.8 and metrics[name]["food_intake"] > 0)
        checks[name + "-direction"] = bool(report["scene"]["mirror"] * (yaw[50] - yaw[0]) > .05)
    for name in ("bifurcation-left", "bifurcation-right"):
        checks[name + "-choice-and-food"] = metrics[name]["correct_branch"] == 1 and metrics[name]["food_intake"] > 0
        checks[name + "-upright"] = min(t["upright_z"] for t in reports[name]["neural_trace"]) > .8
    a, b = reports["heldout-left"], reports["heldout-repeat"]
    checks["repeat-identical"] = a["trajectory"] == b["trajectory"] and a["neural_trace"] == b["neural_trace"]
    checks["blank-and-ablation-passive"] = reports["blank"]["trajectory"] == reports["output-ablation"]["trajectory"]
    for name in ("blank", "output-ablation"):
        checks[name + "-stop"] = metrics[name]["mean_drive"] < 1e-8 and metrics[name]["displacement_mm"] < .25
    checks["cue-offset-stop"] = metrics["delayed-cue"]["post_cue_mean_drive"] < .05
    checks["fullgraph"] = all(r["neuron_count"] > 100000 for r in receipts.values())
    _same(runtime_closure(), closure, "final source closure")
    _same(file_sha(Path(__file__)), policy_sha, "final evaluator source")
    checks["final-source"] = True
    result = {"schema_version": SCHEMA, "profile_sha256": digest(expected_profile), "policy_sha256": policy_sha,
              "checks": checks, "receipts": {n: r["sha256"] for n, r in receipts.items()},
              "metrics": metrics, "measured": measured}
    result["sha256"] = digest(result)
    _document(result, expected_profile, policy_sha)
    return result


def build_qualification(root: Path, expected_profile: dict) -> dict:
    """Read eight complete trial directories; return derived v4 proof, even if gates fail.

    Does not write evidence or admit a candidate. Invalid evidence raises ValueError.
    """
    try:
        return _build(Path(root), expected_profile)
    except (OSError, KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError(f"Invalid qualification evidence: {error}") from error


def verify_qualification(path: Path, expected_profile: dict) -> dict:
    """Return the fully recomputed document; reject any document/evidence disagreement.

    A valid failed proof is returned with false gates. Admission must additionally
    require every value in its exact GATES set to be True.
    """
    try:
        path = Path(path)
        document = _read(path)
        _document(document, expected_profile, file_sha(Path(__file__)))
        recomputed = build_qualification(path.parent, expected_profile)
        _same(document, recomputed, "document versus verified observations")
        return recomputed
    except (OSError, KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError(f"Invalid qualification evidence: {error}") from error
