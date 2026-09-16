"""Independent verifier for the sealed v12 retained-data correction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import re
import sys
import time
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np

from ..common import file_sha, write_json
from .mechanical_v12 import CONTACT, CORE, DENSE, DT, _slices, _width


ROWS = 40001
TOLERANCE = 5e-12
LEGS = ("lf", "lm", "lh", "rf", "rm", "rh")
EXPECTED_DERIVED_FIELDS = {
    "ticks",
    "endpoint_source_core_row",
    "endpoint_thorax_ap",
    "endpoint_whole_foot_min_height",
    "interval_contact_row_tick",
    "interval_state_start_core_row",
    "interval_state_end_core_row",
    "interval_summed_positive_normal",
    "interval_force_weighted_pre_tangent",
    "interval_peak_pre_tangent_speed",
}
VALIDATION_SCHEMA = "behavior-v12-correction-validation/v3"
VALIDATION_IDENTITY = "contract-03"
VALIDATION_SOURCE_PATHS = (
    "src/flyarena/experiments/behavior_v12_correction.py",
    "src/flyarena/experiments/verify_behavior_v12_correction.py",
    "tests/test_behavior_v12_correction.py",
)
VALIDATION_SNAPSHOT_PATHS = {
    relative: f"sealed-sources/{Path(relative).name}" for relative in VALIDATION_SOURCE_PATHS
}
EXPECTED_VALIDATION_REPO = Path("/tmp/fly-arena-behavior-v12-final").resolve()
EXPECTED_VALIDATION_OUTPUT = EXPECTED_VALIDATION_REPO / "var/behavior-v12-correction-validation/contract-03"
EXPECTED_LEGACY_REPO = Path("/tmp/fly-arena-behavior-v12").resolve()
EXPECTED_LEGACY_ANALYSIS = EXPECTED_LEGACY_REPO / "var/behavior-v12-correction/analysis-01/revision-02"
FAILED_ATTEMPT_REGISTRATION_SHA256 = "d93334a0a43ddf750a2eb23067208060c6ebe9e85e812124d002707fbc57c35b"
FAILED_ATTEMPT_SOURCE_IDENTITY_SHA256 = "6bf979a72b72cea811f6f7a543dee373490b657ecb177e34f17e5e0a4df0bfcc"
FAILED_ATTEMPT_SOURCE_SEAL = {
    "src/flyarena/experiments/behavior_v12_correction.py": {"bytes": 126599, "sha256": "8e7cb467fa1ee8cb3c38021d964741efda39cc6de5e8566911aaa82e698e7bfb"},
    "src/flyarena/experiments/verify_behavior_v12_correction.py": {"bytes": 55145, "sha256": "c0d23ebfb25076dfe880de21c7a845a967ceccf2f8e68073fb9767463f99d218"},
    "tests/test_behavior_v12_correction.py": {"bytes": 28713, "sha256": "4302d44ff84718cfa068fa47592826358fced641dd6e9e285819b05cfcb4e731"},
}
VALIDATION_PAYLOAD = sorted((
    "attempts/registration-01.json",
    "attempts/sealed-sources-01/behavior_v12_correction.py",
    "attempts/sealed-sources-01/test_behavior_v12_correction.py",
    "attempts/sealed-sources-01/verify_behavior_v12_correction.py",
    "attempts/tests/test-invocation-01.json",
    "attempts/tests/test-invocation-01.junit.xml",
    "attempts/tests/test-invocation-02.json",
    "attempts/tests/test-invocation-02.junit.xml",
    "chronology.json", "independent-verification.json", "registration.json", "resource-receipt.json",
    "retained-validation.json", "sealed-sources/behavior_v12_correction.py",
    "sealed-sources/test_behavior_v12_correction.py", "sealed-sources/verify_behavior_v12_correction.py",
    "tests/test-invocation-01.json", "tests/test-invocation-01.junit.xml",
    "tests/test-invocation-02.json", "tests/test-invocation-02.junit.xml",
))
PARENT_CONTRACT = {'identity': 'contract-02', 'status': 'rejected', 'registration_path': '/tmp/fly-arena-behavior-v12-boundary/var/behavior-v12-correction-validation/contract-02/registration.json', 'registration_sha256': '331a1e16d7e2f61ddfa69f29fefa4a1a9d73bf3328551a06182c3a0a9260ba67', 'inventory_path': '/tmp/fly-arena-behavior-v12-boundary/var/behavior-v12-correction-validation/contract-02/output-inventory.json', 'inventory_sha256': 'af534057e0db6a8f82071997cca9a709a676f37d8a5cfec7e0ba85dcecde8d75', 'source_sha256': {'src/flyarena/experiments/behavior_v12_correction.py': 'a23d4bc9a5fd48378b54253e5acce57172cf29653fe0ae37cf3673759966b957', 'src/flyarena/experiments/verify_behavior_v12_correction.py': 'c05e5df452039e8dd92e845d0d0f0ad55c46cb77abbdfa0a74f66e0b368a79d7', 'tests/test_behavior_v12_correction.py': '159ac41d33c116eb07c0ae6e1a3ff0fcaa9050141ee19b2a93fc67bc24538891'}}
RESTORATION_FIELDS = {"integration", "core", "dense", "contacts", "contact_offsets"}


def _int_column(values: np.ndarray, selector: slice) -> np.ndarray:
    result = np.asarray(values[:, selector], dtype=np.int64).reshape(-1)
    if result.shape != (len(values),):
        raise ValueError("invalid one-column schema slice")
    return result


def _read_stream(path: Path, width: int, expected_rows: int | None = None):
    terminal = json.loads((path / "terminal.json").read_text())
    if not terminal["complete"] or terminal["primary_failure"] is not None or terminal["retention_failures"]:
        raise ValueError(f"incomplete raw stream: {path}")
    if expected_rows is not None and terminal["initialized_rows"] != expected_rows:
        raise ValueError("raw stream row count mismatch")
    ticks, values = [], []
    chunks = sorted(path.glob("chunk-*.npz"))
    names = {name for name in terminal["files"] if name.startswith("chunk-")}
    if {chunk.name for chunk in chunks} != names:
        raise ValueError("raw chunk manifest mismatch")
    for index, chunk in enumerate(chunks):
        if chunk.name != f"chunk-{index:05d}.npz" or file_sha(chunk) != terminal["files"][chunk.name]:
            raise ValueError("raw chunk hash/order mismatch")
        with np.load(chunk, allow_pickle=False) as archive:
            if set(archive.files) != {"ticks", "values"}:
                raise ValueError("raw archive field mismatch")
            tick, value = archive["ticks"], archive["values"]
            if (tick.dtype != np.int64 or value.dtype != np.float64
                    or value.shape != (len(tick), width) or not np.isfinite(value).all()):
                raise ValueError("raw archive dtype/shape/value mismatch")
            ticks.append(tick)
            values.append(value)
    ticks = np.concatenate(ticks) if ticks else np.empty(0, dtype=np.int64)
    values = np.concatenate(values) if values else np.empty((0, width), dtype=np.float64)
    if len(ticks) != terminal["initialized_rows"]:
        raise ValueError("raw stream terminal count mismatch")
    return ticks, values


def _longest(values: np.ndarray) -> int:
    padded = np.r_[False, np.asarray(values, dtype=bool), False]
    switches = np.flatnonzero(padded[1:] != padded[:-1])
    return int(np.max(switches[1::2] - switches[::2], initial=0))


def _runs(state: np.ndarray, phase: np.ndarray):
    lo, hi = 6000, 25000
    state, phase = np.asarray(state), np.asarray(phase)
    if (state.ndim != 1 or phase.ndim != 1 or state.shape != phase.shape
            or phase.dtype != np.float64 or len(phase) <= hi):
        raise ValueError("invalid independent phase/run input")
    increments = np.diff(phase[lo:hi + 1])
    bad = np.flatnonzero(~np.isfinite(increments) | (increments <= 0))
    if len(bad):
        return [], [], [(lo + int(index), lo + int(index) + 1) for index in bad]
    window = np.asarray(state[lo:hi + 1], dtype=bool)
    changes = np.flatnonzero(np.r_[True, window[1:] != window[:-1], True])
    complete, partial, invalid = [], [], []
    for left, right in zip(changes[:-1], changes[1:]):
        if not window[left]:
            continue
        start, end = lo + int(left), lo + int(right)
        run = phase[start:end]
        if np.any(~np.isfinite(np.diff(run)) | (np.diff(run) <= 0)):
            invalid.append((start, end))
        elif start == lo or end == hi + 1:
            partial.append((start, end))
        else:
            complete.append((start, end))
    return complete, partial, invalid


def _cycle_gate(phases, ap, heights, normal, weighted, periods):
    recovery_all = True
    support_all = True
    invalid_total = 0
    status = []
    for leg, name in enumerate(LEGS):
        increments = np.diff(phases[6000:25001, leg])
        full_invalid = int(np.count_nonzero(~np.isfinite(increments) | (increments <= 0)))
        start_phase, end_phase = periods[name]
        mod = np.mod(phases[:, leg], 2 * np.pi)
        swing_runs, swing_partial, swing_invalid = _runs(
            (mod > start_phase) & (mod < end_phase), phases[:, leg]
        )
        stance_runs, stance_partial, stance_invalid = _runs(
            ~((mod > start_phase) & (mod < end_phase)), phases[:, leg]
        )
        invalid_total += full_invalid + len(swing_invalid) + len(stance_invalid)
        swing_status = []
        for begin, end in swing_runs:
            raw = ap[begin:end, leg]
            filtered = (np.median(np.lib.stride_tricks.sliding_window_view(raw, 31), axis=1)
                        if len(raw) >= 31 else np.empty(0))
            passed = False
            if len(filtered):
                minimum, maximum = filtered.min(), filtered.max()
                pep_local = int(np.flatnonzero(filtered == minimum)[0])
                later = np.flatnonzero((filtered == maximum) & (np.arange(len(filtered)) > pep_local))
                if len(later):
                    pep = begin + 15 + pep_local
                    aep = begin + 15 + int(later[0])
                    dwell = _longest(
                        (heights[pep:aep + 1, leg] > 0.02) & (normal[pep:aep + 1, leg] == 0)
                    )
                    passed = bool(aep > pep and maximum - minimum > 0.02 and dwell >= 30)
            recovery_all &= passed
            swing_status.append(passed)
        if not swing_runs or swing_invalid or full_invalid:
            recovery_all = False
        stance_status = []
        for begin, end in stance_runs:
            loaded = normal[begin:end, leg] > 0
            ratio = np.divide(
                weighted[begin:end, leg], normal[begin:end, leg],
                out=np.zeros(end - begin), where=loaded,
            )
            passed = bool(_longest(loaded) >= 30 and DT * ratio.sum() < 0.15)
            support_all &= passed
            stance_status.append(passed)
        if not stance_runs or stance_invalid or full_invalid:
            support_all = False
        status.append({
            "leg": name,
            "swings": swing_status,
            "stances": stance_status,
            "swing_boundary_partials": len(swing_partial),
            "stance_boundary_partials": len(stance_partial),
            "invalid": full_invalid + len(swing_invalid) + len(stance_invalid),
            "full_active_window_invalid_increments": full_invalid,
        })
    return bool(recovery_all), bool(support_all), invalid_total, status


def _geometry_sample(model, data, qpos, meta):
    data.qpos[:] = qpos
    mj.mj_kinematics(model, data)
    mj.mj_comPos(model, data)
    heights = np.full(6, np.inf)
    centers = np.empty((6, 3))
    for index, geom in enumerate(meta["foot"]):
        rotation = data.geom_xmat[geom].reshape(3, 3)
        heights[index // 5] = min(
            heights[index // 5],
            float((meta["vertices"][index] @ rotation[2]).min() + data.geom_xpos[geom, 2]),
        )
        if index % 5 == 4:
            centers[index // 5] = rotation @ meta["centroids"][index] + data.geom_xpos[geom]
    thorax = meta["thorax"]
    ap = (centers - data.xpos[thorax]) @ data.xmat[thorax].reshape(3, 3)[:, 0]
    return heights, ap


def _jacobian_velocity(model, data, points, foot_geom, ground_geom):
    out = np.empty((len(points), 3))
    left = np.zeros((3, model.nv))
    right = np.zeros((3, model.nv))
    for index, point in enumerate(points):
        left.fill(0)
        right.fill(0)
        mj.mj_jac(model, data, left, None, point, int(model.geom_bodyid[foot_geom[index]]))
        mj.mj_jac(model, data, right, None, point, int(model.geom_bodyid[ground_geom[index]]))
        out[index] = (left - right) @ data.qvel
    return out


def verify(repo: Path, output: Path) -> dict:
    started = time.monotonic()
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    registration = json.loads((output / "registration.json").read_text())
    for relative, expected in registration["computation_source_seal"].items():
        if file_sha(repo / relative) != expected:
            raise ValueError(f"sealed source changed: {relative}")
    if not json.loads((output / "raw-closure.json").read_text())["passed"]:
        raise ValueError("raw closure not passed")
    analysis = json.loads((output / "analysis.json").read_text())
    if analysis["status"] != "complete" or analysis["scientific_admission"]:
        raise ValueError("invalid correction analysis scope/status")
    original_root = Path(registration["original_experiment"])
    original_registration = json.loads((original_root / "registration.json").read_text())
    model = mj.MjModel.from_binary_path(str(original_root / "model.mjb"))
    foot = np.asarray(original_registration["measurement"]["foot_geom_ids"], dtype=np.int64)
    ground = mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, "ground_plane")
    leg_by_geom = np.full(model.ngeom, -1, dtype=np.int64)
    leg_by_geom[foot] = np.arange(30) // 5
    vertices, centroids = [], []
    for geom in foot:
        mesh = int(model.geom_dataid[geom])
        begin, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
        value = np.asarray(model.mesh_vert[begin:begin + count], dtype=np.float64)
        vertices.append(value)
        centroids.append(value.mean(axis=0, dtype=np.float64))
    meta = {
        "foot": foot,
        "ground": ground,
        "leg_by_geom": leg_by_geom,
        "vertices": vertices,
        "centroids": np.asarray(centroids),
        "thorax": mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, "fly-0/c_thorax"),
    }
    cs, es = _slices(CORE), _slices(CONTACT)
    trial_receipts = {}
    aggregate = {}
    total_contacts = 0
    max_geometry_error = 0.0
    max_pre_velocity_error = 0.0
    for name, reported in sorted(analysis["trials"].items()):
        trial = original_root / "development" / name
        core_ticks, core = _read_stream(trial / "core", _width(CORE), ROWS)
        if not np.array_equal(core_ticks, np.arange(ROWS, dtype=np.int64)):
            raise ValueError("independent core grid failure")
        contact_ticks, contacts = _read_stream(trial / "contacts", _width(CONTACT))
        total_contacts += len(contacts)
        derived_path = output / "derived" / reported["derived_npz"]
        if file_sha(derived_path) != reported["derived_npz_sha256"]:
            raise ValueError("derived hash mismatch")
        with np.load(derived_path, allow_pickle=False) as archive:
            if set(archive.files) != EXPECTED_DERIVED_FIELDS:
                raise ValueError("derived field mismatch")
            derived = {key: archive[key] for key in archive.files}
        for key in ("ticks", "endpoint_source_core_row", "interval_contact_row_tick", "interval_state_start_core_row", "interval_state_end_core_row"):
            if derived[key].dtype != np.int64 or derived[key].shape != (ROWS,):
                raise ValueError("derived index dtype/shape mismatch")
        for key in EXPECTED_DERIVED_FIELDS - {
            "ticks", "endpoint_source_core_row", "interval_contact_row_tick",
            "interval_state_start_core_row", "interval_state_end_core_row",
        }:
            if derived[key].dtype != np.float64 or derived[key].shape != (ROWS, 6) or not np.isfinite(derived[key]).all():
                raise ValueError("derived numeric dtype/shape/value mismatch")
        expected_start = np.r_[-1, np.arange(ROWS - 1, dtype=np.int64)]
        if (not np.array_equal(derived["ticks"], np.arange(ROWS))
                or not np.array_equal(derived["endpoint_source_core_row"], np.arange(ROWS))
                or not np.array_equal(derived["interval_contact_row_tick"], np.arange(ROWS))
                or not np.array_equal(derived["interval_state_start_core_row"], expected_start)
                or not np.array_equal(derived["interval_state_end_core_row"], np.arange(ROWS))):
            raise ValueError("derived paired row identity mismatch")

        normal = np.zeros((ROWS, 6), dtype=np.float64)
        if len(contacts):
            geom = _int_column(contacts, es["foot_geom"])
            other = _int_column(contacts, es["ground_geom"])
            if np.any(other != ground) or np.any(leg_by_geom[geom] < 0):
                raise ValueError("independent contact identity failure")
            force = contacts[:, es["wrench_contact_frame"]][:, 0]
            loaded = (force > 0) & (contact_ticks > 0)
            np.add.at(normal, (contact_ticks[loaded], leg_by_geom[geom[loaded]]), force[loaded])
        if not np.array_equal(normal, derived["interval_summed_positive_normal"]):
            raise ValueError("independent raw normal-force closure failed")

        data = mj.MjData(model)
        sample_ticks = np.unique(np.r_[np.arange(0, ROWS, 100), ROWS - 1])
        geometry_error = 0.0
        velocity_error = 0.0
        contact_samples = 0
        for tick in sample_ticks:
            height, ap = _geometry_sample(model, data, core[tick, cs["qpos"]], meta)
            geometry_error = max(
                geometry_error,
                float(np.max(np.abs(height - derived["endpoint_whole_foot_min_height"][tick]))),
                float(np.max(np.abs(ap - derived["endpoint_thorax_ap"][tick]))),
            )
            interval_tick = int(tick)
            if not interval_tick:
                continue
            selected = contact_ticks == interval_tick
            if not np.any(selected):
                continue
            event = contacts[selected]
            data.qpos[:] = core[interval_tick - 1, cs["qpos"]]
            data.qvel[:] = core[interval_tick - 1, cs["qvel"]]
            mj.mj_kinematics(model, data)
            mj.mj_comPos(model, data)
            points = event[:, es["position"]]
            fg = _int_column(event, es["foot_geom"])
            gg = _int_column(event, es["ground_geom"])
            relative = _jacobian_velocity(model, data, points, fg, gg)
            frames = event[:, es["frame"]].reshape(-1, 3, 3)
            tangent = relative - frames[:, 0] * np.sum(relative * frames[:, 0], axis=1)[:, None]
            speed = np.linalg.norm(tangent, axis=1)
            force = event[:, es["wrench_contact_frame"]][:, 0]
            loaded = force > 0
            weighted = np.zeros(6)
            peak = np.zeros(6)
            legs = leg_by_geom[fg]
            np.maximum.at(peak, legs, speed)
            if np.any(loaded):
                np.add.at(weighted, legs[loaded], force[loaded] * speed[loaded])
            velocity_error = max(
                velocity_error,
                float(np.max(np.abs(weighted - derived["interval_force_weighted_pre_tangent"][interval_tick]))),
                float(np.max(np.abs(peak - derived["interval_peak_pre_tangent_speed"][interval_tick]))),
            )
            contact_samples += len(event)
        if geometry_error > TOLERANCE or velocity_error > TOLERANCE or contact_samples == 0:
            raise ValueError("independent sampled phase reconstruction failed")
        max_geometry_error = max(max_geometry_error, geometry_error)
        max_pre_velocity_error = max(max_pre_velocity_error, velocity_error)

        recovery, support, invalid, cycle_status = _cycle_gate(
            core[:, cs["phases"]],
            derived["endpoint_thorax_ap"],
            derived["endpoint_whole_foot_min_height"],
            derived["interval_summed_positive_normal"],
            derived["interval_force_weighted_pre_tangent"],
            original_registration["controller"]["swing_periods_strict_modulo"],
        )
        if (recovery != reported["recovery_passed"] or support != reported["support_slip_passed"]
                or invalid != reported["invalid_interior_phase_episodes"]):
            raise ValueError("independent cycle/gate result mismatch")
        trial_receipts[name] = {
            "derived_sha256": reported["derived_npz_sha256"],
            "raw_contact_rows": len(contacts),
            "sampled_endpoint_rows": len(sample_ticks),
            "sampled_contact_velocities": contact_samples,
            "max_endpoint_geometry_error": geometry_error,
            "max_pre_velocity_aggregate_error": velocity_error,
            "recovery": recovery,
            "support_slip": support,
            "invalid_interior_phase_episodes": invalid,
            "cycle_status": cycle_status,
        }

    candidate = "source-native-excursion-v12"
    for seed in original_registration["development_seeds"]:
        speed = [analysis["trials"][f"{candidate}--{seed}--{case}"]["forward_mean_mm_s"]
                 for case in ("straight-008", "straight-02", "straight-04")]
        aggregate[f"speed-{seed}"] = bool(speed[0] > 0.2 and all(b - a > 0.2 for a, b in zip(speed, speed[1:])))
    aggregate["active_restoration_raw_join"] = bool(analysis["restoration_raw_join"]["passed"])
    if aggregate != analysis["aggregate_gates"] or total_contacts != analysis["raw_contact_rows"]:
        raise ValueError("independent panel aggregate mismatch")
    result = {
        "schema": "behavior-v12-correction-independent-verification/v1",
        "passed": True,
        "scientific_admission": False,
        "analysis_sha256": file_sha(output / "analysis.json"),
        "registration_sha256": file_sha(output / "registration.json"),
        "trial_count": len(trial_receipts),
        "raw_contact_rows": total_contacts,
        "aggregate_gates": aggregate,
        "max_sampled_endpoint_geometry_error": max_geometry_error,
        "max_sampled_pre_velocity_aggregate_error": max_pre_velocity_error,
        "tolerance": TOLERANCE,
        "trials": trial_receipts,
        "scope_stop": "verification only; no retrospective or downstream admission",
        "resources": {
            "wall_seconds": time.monotonic() - started,
            "user_cpu_seconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime - usage_start.ru_utime,
            "system_cpu_seconds": resource.getrusage(resource.RUSAGE_SELF).ru_stime - usage_start.ru_stime,
            "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if sys.platform == "darwin"
                                  else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            "additional_physics_seconds": 0,
            "workers": 1,
        },
    }
    path = output / "independent-verification.json"
    if path.exists():
        raise FileExistsError(path)
    write_json(path, result)
    return result


def _json_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_digest_document(document: object, checkpoint_cache: dict, label: str) -> None:
    if not isinstance(document, dict) or set(document) != {"cache", "controller_state_sha256"}:
        raise ValueError(f"independent {label} digest document schema mismatch")
    cache, controllers = document["cache"], document["controller_state_sha256"]
    if (not isinstance(cache, list) or len(cache) != 100
            or not isinstance(controllers, list) or len(controllers) != 100):
        raise ValueError(f"independent {label} digest horizon mismatch")
    for entry in cache:
        if not isinstance(entry, dict) or set(entry) != set(checkpoint_cache):
            raise ValueError(f"independent {label} cache keys mismatch")
        for name, record in entry.items():
            template = checkpoint_cache[name]
            if not isinstance(record, dict) or not isinstance(template, dict):
                raise ValueError(f"independent {label} cache record mismatch: {name}")
            if set(template) == {"value"}:
                value = record.get("value")
                if (set(record) != {"value"} or not isinstance(value, (int, float))
                        or isinstance(value, bool) or not np.isfinite(value)):
                    raise ValueError(f"independent {label} scalar record mismatch: {name}")
            else:
                if set(record) != {"dtype", "shape", "finite", "sha256"}:
                    raise ValueError(f"independent {label} array record keys mismatch: {name}")
                shape = record["shape"]
                if (not isinstance(record["dtype"], str) or not record["dtype"]
                        or not isinstance(shape, list)
                        or any(not isinstance(size, int) or isinstance(size, bool) or size < 0 for size in shape)
                        or record["finite"] is not True or not _is_sha256(record["sha256"])):
                    raise ValueError(f"independent {label} array record mismatch: {name}")
                if record["dtype"] != template["dtype"]:
                    raise ValueError(f"restoration pinned dtype mismatch: {name}")
                expected_shape = template["shape"]
                if name.startswith("contact."):
                    count = entry.get("scalar.ncon", {}).get("value")
                    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                        raise ValueError("restoration contact count mismatch")
                    expected_shape = [count, *expected_shape[1:]]
                elif name in {"efc_D", "efc_force", "efc_frictionloss", "efc_margin", "efc_pos", "efc_vel"}:
                    count = entry.get("scalar.nefc", {}).get("value")
                    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                        raise ValueError("restoration constraint count mismatch")
                    expected_shape = [count]
                elif name == "efc_J":
                    # MuJoCo stores this sparse Jacobian as a flat variable-length nnz buffer.
                    if len(shape) != 1:
                        raise ValueError("restoration sparse constraint Jacobian rank mismatch")
                    expected_shape = shape
                if shape != expected_shape:
                    raise ValueError(f"restoration pinned shape mismatch: {name}")
                try:
                    np.dtype(record["dtype"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"independent {label} dtype mismatch: {name}") from exc
    if not all(_is_sha256(value) for value in controllers):
        raise ValueError(f"independent {label} controller digest mismatch")


def _independent_file_record(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"independent sealed path is not regular: {path}")
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": file_sha(path)}


def _independent_legacy_input_seal(legacy_analysis: Path, original_root: Path) -> dict:
    names = (
        "analysis.json", "independent-verification.json", "preregistration.json", "raw-closure.json",
        "registration.json", "resource-receipt.json", "test-receipt.json",
    )
    restoration = (
        "actual-digests.json", "actual.npz", "checkpoint.json", "expected-digests.json",
        "expected.npz", "result.json",
    )
    paths = [legacy_analysis / name for name in names]
    paths += sorted((legacy_analysis / "derived").glob("*"))
    paths += [original_root.parent / "evidence-index.json"]
    paths += [original_root / name for name in ("model.mjb", "registration.json", "sources.json")]
    paths += [original_root / "restoration" / name for name in restoration]
    return {str(index): _independent_file_record(path) for index, path in enumerate(paths)}


def _independent_junit_counts(path: Path) -> tuple[int, int, int, int]:
    root = ET.parse(path).getroot()
    names = ("tests", "failures", "errors", "skipped")

    def counts(node):
        if node.tag not in {"testsuites", "testsuite"}:
            raise ValueError("unsupported JUnit root/suite")
        total = [0, 0, 0, 0]
        for child in node:
            if child.tag == "testsuite":
                values = counts(child)
                total = [a + b for a, b in zip(total, values)]
            elif child.tag == "testcase" and node.tag == "testsuite":
                if not child.get("name"):
                    raise ValueError("JUnit testcase identity missing")
                if any(item.tag not in {"failure", "error", "skipped", "system-out", "system-err", "properties"} for item in child):
                    raise ValueError("unsupported JUnit testcase structure")
                outcomes = [item.tag for item in child if item.tag in {"failure", "error", "skipped"}]
                if len(outcomes) > 1:
                    raise ValueError("ambiguous JUnit testcase outcome")
                total[0] += 1
                for index, tag in enumerate(("failure", "error", "skipped"), 1):
                    total[index] += int(tag in outcomes)
            elif child.tag not in {"properties", "system-out", "system-err"}:
                raise ValueError("unsupported JUnit suite structure")
        for index, name in enumerate(names):
            declared = node.get(name)
            if declared is None and node.tag == "testsuites":
                continue
            if declared is None or re.fullmatch(r"[0-9]+", declared) is None or int(declared) != total[index]:
                raise ValueError(f"JUnit {name} disagrees with actual testcase outcomes")
        return tuple(total)

    return counts(root)


def _validate_prior_failed_attempt(output: Path, registered: object) -> None:
    if not isinstance(registered, dict) or set(registered) != {
        "status", "registration_sha256", "source_identity_sha256", "test_invocations", "artifacts",
    }:
        raise ValueError("independent prior failed-attempt record mismatch")
    if (registered["status"] != "preserved failed contract-02 attempt; not current successful evidence"
            or registered["registration_sha256"] != FAILED_ATTEMPT_REGISTRATION_SHA256
            or registered["source_identity_sha256"] != FAILED_ATTEMPT_SOURCE_IDENTITY_SHA256
            or registered["test_invocations"] != {
                "passed": {"invocation": 1, "tests": 31, "passed": 31, "failed": 0, "process_exit": 0},
                "failed": {"invocation": 2, "tests": 76, "passed": 75, "failed": 1, "process_exit": 1},
            }):
        raise ValueError("independent prior failed-attempt identity mismatch")
    expected_paths = {
        "attempts/registration-01.json",
        "attempts/sealed-sources-01/behavior_v12_correction.py",
        "attempts/sealed-sources-01/test_behavior_v12_correction.py",
        "attempts/sealed-sources-01/verify_behavior_v12_correction.py",
        "attempts/tests/test-invocation-01.json", "attempts/tests/test-invocation-01.junit.xml",
        "attempts/tests/test-invocation-02.json", "attempts/tests/test-invocation-02.junit.xml",
    }
    if not isinstance(registered["artifacts"], dict) or set(registered["artifacts"]) != expected_paths:
        raise ValueError("independent prior failed-attempt artifact set mismatch")
    for relative, record in registered["artifacts"].items():
        path = output / relative
        if (not isinstance(record, dict) or set(record) != {"bytes", "sha256"}
                or not isinstance(record["bytes"], int) or isinstance(record["bytes"], bool)
                or not _is_sha256(record["sha256"]) or not path.is_file() or path.is_symlink()
                or path.stat().st_size != record["bytes"] or file_sha(path) != record["sha256"]):
            raise ValueError(f"independent prior failed-attempt artifact mismatch: {relative}")
    old_registration_path = output / "attempts/registration-01.json"
    if file_sha(old_registration_path) != FAILED_ATTEMPT_REGISTRATION_SHA256:
        raise ValueError("independent prior failed-attempt registration hash mismatch")
    old_registration = json.loads(old_registration_path.read_text())
    if (old_registration.get("source_identity_sha256") != FAILED_ATTEMPT_SOURCE_IDENTITY_SHA256
            or old_registration.get("validation_source_seal") != FAILED_ATTEMPT_SOURCE_SEAL):
        raise ValueError("independent prior failed-attempt source seal mismatch")
    for relative, record in FAILED_ATTEMPT_SOURCE_SEAL.items():
        snapshot = output / "attempts/sealed-sources-01" / Path(relative).name
        if (snapshot.stat().st_size != record["bytes"] or file_sha(snapshot) != record["sha256"]):
            raise ValueError(f"independent prior failed-attempt snapshot mismatch: {relative}")
    for invocation, status, exit_code, counts in (
        (1, "passed", 0, (31, 31, 0, 0, 0)),
        (2, "failed", 1, (76, 75, 1, 0, 0)),
    ):
        receipt = json.loads((output / f"attempts/tests/test-invocation-{invocation:02d}.json").read_text())
        junit = output / "attempts" / receipt.get("junit", "")
        if (receipt.get("schema") != "behavior-v12-correction-validation-test-run/v3"
                or receipt.get("invocation") != invocation or receipt.get("status") != status
                or receipt.get("process_exit") != exit_code
                or tuple(receipt.get(key) for key in ("tests", "passed", "failed", "errors", "skipped")) != counts
                or receipt.get("registration_sha256") != FAILED_ATTEMPT_REGISTRATION_SHA256
                or receipt.get("trusted_registration_sha256") != FAILED_ATTEMPT_REGISTRATION_SHA256
                or receipt.get("source_identity_sha256") != FAILED_ATTEMPT_SOURCE_IDENTITY_SHA256
                or receipt.get("executed_source_seal") != FAILED_ATTEMPT_SOURCE_SEAL
                or receipt.get("junit_sha256") != file_sha(junit)
                or _independent_junit_counts(junit) != (counts[0], counts[2], counts[3], counts[4])):
            raise ValueError(f"independent prior failed-attempt receipt mismatch: {invocation}")


def _validate_v3_registration(repo: Path, output: Path, trusted_registration_sha256: str) -> dict:
    path = output / "registration.json"
    if not _is_sha256(trusted_registration_sha256) or file_sha(path) != trusted_registration_sha256:
        raise ValueError("independent trusted registration digest mismatch")
    registration = json.loads(path.read_text())
    required = {
        "schema", "identity", "purpose", "registered_utc", "repo", "output", "legacy_repo",
        "legacy_analysis", "original_experiment", "legacy_v1_registration_sha256",
        "legacy_v1_analysis_sha256", "legacy_v1_source_seal", "validation_source_seal",
        "sealed_source_snapshots", "source_identity_sha256", "legacy_input_seal",
        "rejected_parent_contract", "prior_failed_attempt", "eligibility", "active_window", "restoration", "legacy_status",
        "future_positive_policy", "scientific_admission", "scope_stop", "payload_allowlist",
        "inventory_self_exclusion", "test_plan", "limits",
    }
    if not isinstance(registration, dict) or set(registration) != required:
        raise ValueError("independent v3 registration field set mismatch")
    if (registration["schema"] != VALIDATION_SCHEMA or registration["identity"] != VALIDATION_IDENTITY
            or registration["purpose"] != "targeted post-outcome boundary correction; retained-data validation only; no new science or admission"
            or not isinstance(registration["registered_utc"], str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", registration["registered_utc"]) is None
            or repo.resolve() != EXPECTED_VALIDATION_REPO
            or output.resolve() != EXPECTED_VALIDATION_OUTPUT.resolve()
            or registration["repo"] != str(EXPECTED_VALIDATION_REPO)
            or registration["output"] != str(EXPECTED_VALIDATION_OUTPUT.resolve())):
        raise ValueError("independent v3 identity/location mismatch")
    exact_limits = {
        "workers": 1, "wall_seconds": 2700, "peak_rss_bytes": 2147483648,
        "new_output_scratch_bytes": 104857600, "physics_seconds": 0, "neural_seconds": 0,
        "network": False, "installs": False, "gpu": False, "remote_operations": False,
    }
    if (registration["eligibility"] != "registered command common > silence_common_max; zero/silence controls are separate safety/stop controls"
            or registration["active_window"] != {"ticks_inclusive": [6000, 25000], "required_increment": "finite and strictly positive"}
            or registration["restoration"] != {"fields": sorted(RESTORATION_FIELDS), "ticks_inclusive": [10001, 10100], "ticks": 100, "seconds": 0.01, "integration_width": 752}
            or registration["legacy_status"] != "rejected; this validation never upgrades v1 for positive admission"
            or registration["future_positive_policy"] != "fresh preregistration and repaired producer/verifier seals required"
            or registration["scientific_admission"] is not False
            or registration["scope_stop"] != "no walking, held-out, neural, phenotype, ablation, Lab/API/replay, or product admission"
            or registration["payload_allowlist"] != VALIDATION_PAYLOAD
            or registration["inventory_self_exclusion"] != "output-inventory.json"
            or registration["test_plan"] != {"invocations": [1, 2], "final_invocation": 2}
            or registration["limits"] != exact_limits):
        raise ValueError("independent v3 policy/limits mismatch")
    if (set(registration["validation_source_seal"]) != set(VALIDATION_SOURCE_PATHS)
            or set(registration["sealed_source_snapshots"]) != set(VALIDATION_SNAPSHOT_PATHS.values())):
        raise ValueError("independent v3 source/snapshot set mismatch")
    for relative in VALIDATION_SOURCE_PATHS:
        source_record = registration["validation_source_seal"][relative]
        snapshot_relative = VALIDATION_SNAPSHOT_PATHS[relative]
        snapshot_record = registration["sealed_source_snapshots"][snapshot_relative]
        for target, record in ((repo / relative, source_record), (output / snapshot_relative, snapshot_record)):
            if (not isinstance(record, dict) or set(record) != {"bytes", "sha256"}
                    or not isinstance(record["bytes"], int) or isinstance(record["bytes"], bool)
                    or record["bytes"] < 0 or not _is_sha256(record["sha256"])
                    or not target.is_file() or target.is_symlink()
                    or target.stat().st_size != record["bytes"] or file_sha(target) != record["sha256"]):
                raise ValueError(f"independent v3 source record mismatch: {target}")
        if source_record != snapshot_record:
            raise ValueError(f"independent source/snapshot identity mismatch: {relative}")
    if registration["source_identity_sha256"] != _json_sha(registration["validation_source_seal"]):
        raise ValueError("independent v3 source identity mismatch")
    legacy_repo = Path(registration["legacy_repo"])
    legacy_analysis = Path(registration["legacy_analysis"])
    legacy_registration_path = legacy_analysis / "registration.json"
    legacy_registration = json.loads(legacy_registration_path.read_text())
    original_root = Path(legacy_registration["original_experiment"]).resolve()
    if (legacy_registration.get("schema") != "behavior-v12-correction-registration/v1"
            or legacy_repo.resolve() != EXPECTED_LEGACY_REPO
            or legacy_analysis.resolve() != EXPECTED_LEGACY_ANALYSIS
            or registration["legacy_repo"] != str(EXPECTED_LEGACY_REPO)
            or registration["legacy_analysis"] != str(EXPECTED_LEGACY_ANALYSIS)
            or registration["original_experiment"] != str(original_root)
            or registration["legacy_v1_registration_sha256"] != file_sha(legacy_registration_path)
            or registration["legacy_v1_analysis_sha256"] != file_sha(legacy_analysis / "analysis.json")
            or registration["legacy_v1_source_seal"] != legacy_registration["computation_source_seal"]
            or registration["legacy_input_seal"] != _independent_legacy_input_seal(legacy_analysis, original_root)):
        raise ValueError("independent legacy identity mismatch")
    if len(legacy_registration["computation_source_seal"]) != 5:
        raise ValueError("independent legacy source set mismatch")
    for relative, expected in legacy_registration["computation_source_seal"].items():
        if file_sha(legacy_repo / relative) != expected:
            raise ValueError(f"independent legacy source changed: {relative}")
    if registration["rejected_parent_contract"] != PARENT_CONTRACT:
        raise ValueError("independent rejected-parent identity mismatch")
    _validate_prior_failed_attempt(output, registration["prior_failed_attempt"])
    for kind in ("registration", "inventory"):
        parent_path = Path(PARENT_CONTRACT[f"{kind}_path"])
        if not parent_path.is_file() or file_sha(parent_path) != PARENT_CONTRACT[f"{kind}_sha256"]:
            raise ValueError(f"independent rejected-parent {kind} mismatch")
    parent_repo = Path("/tmp/fly-arena-behavior-v12-boundary")
    for relative, expected in PARENT_CONTRACT["source_sha256"].items():
        if file_sha(parent_repo / relative) != expected:
            raise ValueError(f"independent rejected-parent source mismatch: {relative}")
    return registration


def _load_derived_v2(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != EXPECTED_DERIVED_FIELDS:
            raise ValueError("independent derived field mismatch")
        values = {name: archive[name] for name in archive.files}
    index_fields = {
        "ticks", "endpoint_source_core_row", "interval_contact_row_tick",
        "interval_state_start_core_row", "interval_state_end_core_row",
    }
    grid = np.arange(ROWS, dtype=np.int64)
    for name, value in values.items():
        shape = (ROWS,) if name in index_fields else (ROWS, 6)
        dtype = np.dtype(np.int64) if name in index_fields else np.dtype(np.float64)
        if value.shape != shape or value.dtype != dtype or not np.isfinite(value).all():
            raise ValueError(f"independent derived schema mismatch: {name}")
    if (not np.array_equal(values["ticks"], grid)
            or not np.array_equal(values["endpoint_source_core_row"], grid)
            or not np.array_equal(values["interval_contact_row_tick"], grid)
            or not np.array_equal(values["interval_state_end_core_row"], grid)
            or not np.array_equal(values["interval_state_start_core_row"], np.r_[-1, grid[:-1]])):
        raise ValueError("independent derived row binding mismatch")
    return values


def _verify_restoration_v2(original_root: Path, original_registration: dict) -> dict:
    root = original_root / "restoration"
    checkpoint = json.loads((root / "checkpoint.json").read_text())
    result = json.loads((root / "result.json").read_text())
    expected_binding = {
        "profile": "source-native-excursion-v12",
        "trial": "development/source-native-excursion-v12--42--straight-02",
        "seed": 42,
        "case": "straight-02",
        "checkpoint_tick": 10000,
        "dt": DT,
        "grid": [0, 40000, 1],
        "model_sha256": original_registration["model_sha256"],
        "sources_sha256": original_registration["sources_sha256"],
        "registration_sha256": file_sha(original_root / "registration.json"),
        "generation": "v12-development-seed42-straight02-active-tick10000",
    }
    if checkpoint.get("binding") != expected_binding:
        raise ValueError("independent restoration binding mismatch")
    model = mj.MjModel.from_binary_path(str(original_root / "model.mjb"))
    width = int(mj.mj_stateSize(model, mj.mjtState.mjSTATE_INTEGRATION))
    if width != 752 or checkpoint.get("integration_shape") != [width] or checkpoint.get("integration_dtype") != "<f8":
        raise ValueError("independent restoration native state contract mismatch")
    if (result.get("registration_sha256") != expected_binding["registration_sha256"]
            or result.get("ticks") != [10001, 10100]
            or result.get("additional_physical_seconds") != 100 * DT
            or result.get("passed") is not True
            or result.get("corrupted_destination_before_restore") is not True):
        raise ValueError("independent restoration result contract mismatch")
    archives = []
    for filename in ("expected.npz", "actual.npz"):
        with np.load(root / filename, allow_pickle=False) as archive:
            if set(archive.files) != RESTORATION_FIELDS:
                raise ValueError("independent restoration field mismatch")
            values = {name: archive[name] for name in archive.files}
        contacts = values["contacts"]
        contracts = {
            "core": ((100, 303), np.dtype(np.float64)),
            "dense": ((100, 60), np.dtype(np.float64)),
            "integration": ((100, width), np.dtype(np.float64)),
            "contacts": ((len(contacts), 26), np.dtype(np.float64)),
            "contact_offsets": ((101,), np.dtype(np.int64)),
        }
        for name, (shape, dtype) in contracts.items():
            if values[name].shape != shape or values[name].dtype != dtype or not np.isfinite(values[name]).all():
                raise ValueError(f"independent restoration array mismatch: {name}")
        offsets = values["contact_offsets"]
        if (offsets[0] != 0 or offsets[-1] != len(contacts) or np.any(offsets < 0)
                or np.any(offsets > len(contacts)) or np.any(np.diff(offsets) < 0)):
            raise ValueError("independent restoration offsets mismatch")
        archives.append(values)
    if not all(np.array_equal(archives[0][name], archives[1][name]) for name in RESTORATION_FIELDS):
        raise ValueError("independent expected/actual restoration mismatch")
    expected_digests = json.loads((root / "expected-digests.json").read_text())
    actual_digests = json.loads((root / "actual-digests.json").read_text())
    checkpoint_cache = checkpoint.get("cache")
    if not isinstance(checkpoint_cache, dict) or not checkpoint_cache:
        raise ValueError("independent checkpoint cache schema missing")
    _validate_digest_document(expected_digests, checkpoint_cache, "expected")
    _validate_digest_document(actual_digests, checkpoint_cache, "actual")
    if expected_digests != actual_digests:
        raise ValueError("independent restoration digest mismatch")
    trial = original_root / expected_binding["trial"]
    core_ticks, core = _read_stream(trial / "core", _width(CORE), ROWS)
    dense_ticks, dense = _read_stream(trial / "dense", _width(DENSE), ROWS)
    contact_ticks, contacts = _read_stream(trial / "contacts", _width(CONTACT))
    ticks = np.arange(10001, 10101, dtype=np.int64)
    if (not np.array_equal(core_ticks, np.arange(ROWS)) or not np.array_equal(dense_ticks, np.arange(ROWS))
            or not np.array_equal(archives[0]["core"], core[ticks])
            or not np.array_equal(archives[0]["dense"], dense[ticks])):
        raise ValueError("independent restoration core/dense raw join mismatch")
    offsets = archives[0]["contact_offsets"]
    for index, tick in enumerate(ticks):
        if not np.array_equal(
            archives[0]["contacts"][offsets[index]:offsets[index + 1]], contacts[contact_ticks == tick]
        ):
            raise ValueError("independent restoration contact raw join mismatch")
    return {
        "passed": True,
        "fields": sorted(RESTORATION_FIELDS),
        "integration_width_from_pinned_model": width,
        "ticks_checked": 100,
        "core_rows_joined": 100,
        "dense_rows_joined": 100,
        "contact_rows_joined": len(archives[0]["contacts"]),
        "contact_offsets_checked": 101,
    }


def verify_retained_v3(repo: Path, output: Path, trusted_registration_sha256: str) -> dict:
    started = time.monotonic()
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    registration = _validate_v3_registration(repo, output, trusted_registration_sha256)
    destination = output / "independent-verification.json"
    if destination.exists():
        raise FileExistsError(destination)
    producer = json.loads((output / "retained-validation.json").read_text())
    expected_producer_keys = {
        "schema", "passed", "terminal_state", "process_exit", "scientific_admission",
        "legacy_v1_status", "future_positive_experiments", "registration_sha256",
        "trusted_registration_sha256", "source_identity_sha256", "legacy_analysis_sha256",
        "trial_count", "active_trial_count", "zero_control_count", "active_phase_increments_checked",
        "complete_phase_runs_recalculated", "endpoint_next_cache_rows_checked",
        "final_endpoints_without_next_cache", "stance_slip_formulas_checked", "raw_contact_rows_closed",
        "index_closure", "restoration", "aggregate_gates", "trials", "scope", "scope_stop", "resources",
    }
    expected_coverage = {
        "trial_count": 32, "active_trial_count": 28, "zero_control_count": 4,
        "active_phase_increments_checked": 3192000, "complete_phase_runs_recalculated": 5008,
        "endpoint_next_cache_rows_checked": 1280000, "final_endpoints_without_next_cache": 32,
        "stance_slip_formulas_checked": 2768, "raw_contact_rows_closed": 9095759,
    }
    if (not isinstance(producer, dict) or set(producer) != expected_producer_keys
            or producer["schema"] != "behavior-v12-correction-retained-validation/v3"
            or producer["passed"] is not True or producer["terminal_state"] != "completed"
            or producer["process_exit"] != 0 or producer["scientific_admission"] is not False
            or producer["legacy_v1_status"] != "rejected"
            or producer["registration_sha256"] != trusted_registration_sha256
            or producer["trusted_registration_sha256"] != trusted_registration_sha256
            or producer["source_identity_sha256"] != registration["source_identity_sha256"]
            or producer["legacy_analysis_sha256"] != registration["legacy_v1_analysis_sha256"]
            or any(producer[key] != value for key, value in expected_coverage.items())
            or not isinstance(producer["trials"], dict) or len(producer["trials"]) != 32
            or producer["scope_stop"] != registration["scope_stop"]
            or producer["restoration"].get("passed") is not True):
        raise ValueError("producer v3 retained receipt missing or invalid")
    legacy_analysis = Path(registration["legacy_analysis"])
    original_root = Path(registration["original_experiment"])
    legacy = json.loads((legacy_analysis / "analysis.json").read_text())
    original_registration = json.loads((original_root / "registration.json").read_text())
    expected_trials = {
        f"{profile}--{seed}--{case[0]}": (profile, seed, case)
        for profile in original_registration["profiles"]
        for seed in original_registration["development_seeds"]
        for case in original_registration["cases"]
    }
    if set(legacy["trials"]) != set(expected_trials) or len(expected_trials) != 32:
        raise ValueError("independent retained panel mismatch")
    model = mj.MjModel.from_binary_path(str(original_root / "model.mjb"))
    ground = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, "ground_plane"))
    foot = np.asarray(original_registration["measurement"]["foot_geom_ids"], dtype=np.int64)
    leg_by_geom = np.full(model.ngeom, -1, dtype=np.int64)
    leg_by_geom[foot] = np.arange(30, dtype=np.int64) // 5
    cs, ds, es = _slices(CORE), _slices(DENSE), _slices(CONTACT)
    trials = {}
    total_contacts = total_endpoints = total_slips = total_phase = complete_runs = 0
    active_trials = zero_controls = 0
    for name, reported in sorted(legacy["trials"].items()):
        profile, seed, case = expected_trials[name]
        trial = original_root / "development" / name
        starts = [json.loads((trial / stream / "start.json").read_text()) for stream in ("core", "dense", "contacts")]
        if starts[0] != starts[1] or starts[0] != starts[2]:
            raise ValueError("independent stream identity mismatch")
        if ((starts[0].get("profile"), starts[0].get("seed"), starts[0].get("case"), starts[0].get("stage"))
                != (profile, seed, case, "development")
                or starts[0].get("registration_sha256") != file_sha(original_root / "registration.json")
                or starts[0].get("sources_sha256") != original_registration["sources_sha256"]):
            raise ValueError("independent trial identity mismatch")
        core_ticks, core = _read_stream(trial / "core", _width(CORE), ROWS)
        dense_ticks, dense = _read_stream(trial / "dense", _width(DENSE), ROWS)
        contact_ticks, contacts = _read_stream(trial / "contacts", _width(CONTACT))
        grid = np.arange(ROWS, dtype=np.int64)
        if not np.array_equal(core_ticks, grid) or not np.array_equal(dense_ticks, grid):
            raise ValueError("independent retained grid mismatch")
        derived_path = legacy_analysis / "derived" / reported["derived_npz"]
        if file_sha(derived_path) != reported["derived_npz_sha256"]:
            raise ValueError("independent retained derived hash mismatch")
        derived = _load_derived_v2(derived_path)
        _, common, asymmetry = case
        waveform = np.zeros((ROWS, 2), dtype=np.float64)
        waveform[3001:25001] = [common * (1 - asymmetry), common * (1 + asymmetry)]
        if not np.array_equal(core[:, cs["input"]], waveform):
            raise ValueError("independent registered waveform mismatch")
        active = common > original_registration["controller"]["silence_common_max"]
        if active:
            active_trials += 1
            increments = np.diff(core[6000:25001, cs["phases"]], axis=0)
            total_phase += increments.size
            if np.any(~np.isfinite(increments) | (increments <= 0)):
                raise ValueError("independent full-window phase failure")
            recovery, support, invalid, status = _cycle_gate(
                core[:, cs["phases"]], derived["endpoint_thorax_ap"],
                derived["endpoint_whole_foot_min_height"], derived["interval_summed_positive_normal"],
                derived["interval_force_weighted_pre_tangent"],
                original_registration["controller"]["swing_periods_strict_modulo"],
            )
            if (recovery != reported["recovery_passed"] or support != reported["support_slip_passed"]
                    or invalid != reported["invalid_interior_phase_episodes"]):
                raise ValueError("independent phase/cycle decision mismatch")
            complete_runs += sum(len(record["swings"]) + len(record["stances"]) for record in status)
        else:
            zero_controls += 1
            recovery = support = False
            invalid = 0
            status = []
            if not np.isfinite(core[:, cs["phases"]]).all():
                raise ValueError("independent zero-control phase state failure")

        endpoint_error = float(max(
            np.max(np.abs(derived["endpoint_thorax_ap"][:-1] - dense[1:, ds["thorax_ap"]])),
            np.max(np.abs(derived["endpoint_whole_foot_min_height"][:-1] - dense[1:, ds["whole_foot_min_height"]])),
        ))
        if endpoint_error > TOLERANCE:
            raise ValueError("independent endpoint-next-cache mismatch")
        total_endpoints += ROWS - 1
        normal = np.zeros((ROWS, 6), dtype=np.float64)
        if len(contacts):
            fg = _int_column(contacts, es["foot_geom"])
            gg = _int_column(contacts, es["ground_geom"])
            if np.any(fg < 0) or np.any(fg >= model.ngeom) or np.any(gg != ground) or np.any(leg_by_geom[fg] < 0):
                raise ValueError("independent raw contact identity mismatch")
            force = contacts[:, es["wrench_contact_frame"]][:, 0]
            loaded = (force > 0) & (contact_ticks > 0)
            np.add.at(normal, (contact_ticks[loaded], leg_by_geom[fg[loaded]]), force[loaded])
        if not np.array_equal(normal, derived["interval_summed_positive_normal"]):
            raise ValueError("independent full normal-force closure mismatch")
        slip_error = 0.0
        slip_count = 0
        for leg, records in enumerate(reported["stance_cycles"]):
            for record in records:
                begin, end = record["start_tick"], record["end_tick_exclusive"]
                loaded = normal[begin:end, leg] > 0
                ratios = np.divide(
                    derived["interval_force_weighted_pre_tangent"][begin:end, leg], normal[begin:end, leg],
                    out=np.zeros(end - begin, dtype=np.float64), where=loaded,
                )
                actual = float(DT * ratios.sum())
                slip_error = max(slip_error, abs(actual - record["slip_mm"]))
                if actual != record["slip_mm"]:
                    raise ValueError("independent stance-slip formula mismatch")
                slip_count += 1
        total_slips += slip_count

        position = core[:, cs["thorax_position"]]
        rotation = core[:, cs["thorax_rotation"]].reshape(-1, 3, 3)
        yaw = np.unwrap(np.arctan2(rotation[:, 1, 0], rotation[:, 0, 0]))
        velocity = np.diff(position, axis=0) / DT
        values = {
            "forward_mean_mm_s": float(((velocity[6000:25000] * rotation[6000:25000, :, 0]).sum(axis=1)).mean()),
            "mean_yaw_rate_rad_s": float((yaw[25000] - yaw[6000]) / 1.9),
            "net_active_yaw_rad": float(yaw[25000] - yaw[3000]),
            "min_upright_z": float(rotation[:, 2, 2].min()),
            "stop_displacement_mm": float(np.linalg.norm(position[40000] - position[30000])),
            "stop_mean_speed_mm_s": float(np.linalg.norm(velocity[30000:40000], axis=1).mean()),
        }
        if any(values[key] != reported[key] for key in values):
            raise ValueError("independent reported kinematics mismatch")
        gates = {
            "finite": True,
            "upright": values["min_upright_z"] > 0.8,
            "stop": values["stop_displacement_mm"] < 0.25 and values["stop_mean_speed_mm_s"] < 0.1,
        }
        if active:
            gates.update(recovery=recovery, support_slip=support)
            if asymmetry:
                gates["turn"] = bool(np.sign(values["net_active_yaw_rad"]) == np.sign(asymmetry)
                                     and abs(values["net_active_yaw_rad"]) > 0.1)
            else:
                gates["straight_yaw"] = abs(values["mean_yaw_rate_rad_s"]) < 0.15
        if gates != reported["gates"]:
            raise ValueError("independent operational gate mismatch")
        total_contacts += len(contacts)
        trials[name] = {
            "eligible_active": active,
            "zero_control": not active,
            "identity_sha256": _json_sha(starts[0]),
            "raw_contact_rows": len(contacts),
            "active_phase_increments_checked": 6 * 19000 if active else 0,
            "endpoint_next_cache_rows": 40000,
            "final_endpoint_without_next_cache": 1,
            "stance_slips_checked": slip_count,
            "max_endpoint_next_cache_error": endpoint_error,
            "max_slip_formula_error": slip_error,
            "raw_positive_normal_force_closed": True,
            "gates": gates,
            "cycle_status": status,
        }
    if total_contacts != legacy["raw_contact_rows"]:
        raise ValueError("independent raw contact total mismatch")
    restoration = _verify_restoration_v2(original_root, original_registration)
    aggregate = {"active_restoration_raw_join": True}
    for seed in original_registration["development_seeds"]:
        speed = [legacy["trials"][f"source-native-excursion-v12--{seed}--{case}"]["forward_mean_mm_s"]
                 for case in ("straight-008", "straight-02", "straight-04")]
        aggregate[f"speed-{seed}"] = bool(speed[0] > 0.2 and all(
            right - left > 0.2 for left, right in zip(speed, speed[1:])
        ))
    if aggregate != legacy["aggregate_gates"]:
        raise ValueError("independent aggregate gate mismatch")
    coverage = {
        "trials": len(trials),
        "active_trials": active_trials,
        "zero_controls": zero_controls,
        "active_phase_increments": total_phase,
        "complete_phase_runs": complete_runs,
        "endpoint_next_cache_rows": total_endpoints,
        "final_endpoints_without_next_cache": len(trials),
        "stance_slip_formulas": total_slips,
        "raw_positive_normal_force_rows": total_contacts,
    }
    producer_coverage = {
        "trials": producer["trial_count"],
        "active_trials": producer["active_trial_count"],
        "zero_controls": producer["zero_control_count"],
        "active_phase_increments": producer["active_phase_increments_checked"],
        "complete_phase_runs": producer["complete_phase_runs_recalculated"],
        "endpoint_next_cache_rows": producer["endpoint_next_cache_rows_checked"],
        "final_endpoints_without_next_cache": producer["final_endpoints_without_next_cache"],
        "stance_slip_formulas": producer["stance_slip_formulas_checked"],
        "raw_positive_normal_force_rows": producer["raw_contact_rows_closed"],
    }
    if coverage != producer_coverage:
        raise ValueError("independent/producer coverage mismatch")
    result = {
        "schema": "behavior-v12-correction-independent-verification/v3",
        "passed": True,
        "terminal_state": "completed",
        "process_exit": 0,
        "scientific_admission": False,
        "registration_sha256": trusted_registration_sha256,
        "trusted_registration_sha256": trusted_registration_sha256,
        "source_identity_sha256": registration["source_identity_sha256"],
        "producer_receipt_sha256": file_sha(output / "retained-validation.json"),
        "legacy_v1_status": "rejected",
        "coverage": coverage,
        "aggregate_gates": aggregate,
        "restoration": restoration,
        "trials": trials,
        "scope": "full retained normal-force/cache/slip/phase/gate validation; no exhaustive Jacobian velocity or six-component wrench reconstruction",
        "scope_stop": "no walking, held-out, neural, phenotype, ablation, Lab/API/replay, or product admission",
        "resources": {
            "wall_seconds": time.monotonic() - started,
            "user_cpu_seconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime - usage_start.ru_utime,
            "system_cpu_seconds": resource.getrusage(resource.RUSAGE_SELF).ru_stime - usage_start.ru_stime,
            "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if sys.platform == "darwin"
                                  else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            "physics_seconds": 0,
            "neural_seconds": 0,
            "workers": 1,
        },
    }
    write_json(destination, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-v3", action="store_true")
    parser.add_argument("--trusted-registration-sha256")
    args = parser.parse_args()
    if args.validation_v3 and args.trusted_registration_sha256 is None:
        parser.error("--trusted-registration-sha256 is required with --validation-v3")
    result = (verify_retained_v3(
        args.repo.resolve(), args.output.resolve(), args.trusted_registration_sha256,
    ) if args.validation_v3 else verify(args.repo.resolve(), args.output.resolve()))
    trial_count = result.get("trial_count", result.get("coverage", {}).get("trials"))
    if not isinstance(trial_count, int):
        raise ValueError("verification result is missing trial coverage")
    print(json.dumps({"passed": result["passed"], "trial_count": trial_count}, sort_keys=True))


if __name__ == "__main__":
    main()
