"""Independent verifier for the sealed v12 retained-data correction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

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
VALIDATION_SCHEMA = "behavior-v12-correction-validation/v2"
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


def _validate_v2_registration(repo: Path, output: Path) -> dict:
    registration = json.loads((output / "registration.json").read_text())
    if registration.get("schema") != VALIDATION_SCHEMA or registration.get("identity") != "contract-01":
        raise ValueError("independent verifier requires v2 validation identity")
    for relative, expected in registration["validation_source_seal"].items():
        if file_sha(repo / relative) != expected:
            raise ValueError(f"v2 executed source seal mismatch: {relative}")
    for relative, expected in registration["sealed_source_snapshots"].items():
        snapshot = output / relative
        if not snapshot.is_file() or snapshot.is_symlink() or file_sha(snapshot) != expected:
            raise ValueError(f"v2 sealed source snapshot mismatch: {relative}")
    for record in registration["legacy_input_seal"].values():
        path = Path(record["path"])
        if (not path.is_file() or path.is_symlink() or path.stat().st_size != record["bytes"]
                or file_sha(path) != record["sha256"]):
            raise ValueError(f"v2 legacy input seal mismatch: {path}")
    legacy_registration = json.loads((Path(registration["legacy_analysis"]) / "registration.json").read_text())
    if legacy_registration.get("schema") != "behavior-v12-correction-registration/v1":
        raise ValueError("legacy v1 identity changed")
    for relative, expected in legacy_registration["computation_source_seal"].items():
        if file_sha(Path(registration["legacy_repo"]) / relative) != expected:
            raise ValueError(f"legacy v1 source changed: {relative}")
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
    cache_digests = expected_digests.get("cache")
    controller_digests = expected_digests.get("controller_state_sha256")
    if (expected_digests != actual_digests
            or not isinstance(cache_digests, list) or len(cache_digests) != 100
            or not all(isinstance(value, dict) and set(value) == set(checkpoint.get("cache", {}))
                       for value in cache_digests)
            or not isinstance(controller_digests, list) or len(controller_digests) != 100
            or not all(isinstance(value, str) and len(value) == 64 for value in controller_digests)):
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


def verify_retained_v2(repo: Path, output: Path) -> dict:
    started = time.monotonic()
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    registration = _validate_v2_registration(repo, output)
    destination = output / "independent-verification.json"
    if destination.exists():
        raise FileExistsError(destination)
    producer = json.loads((output / "retained-validation.json").read_text())
    if producer.get("passed") is not True or producer.get("schema") != "behavior-v12-correction-retained-validation/v2":
        raise ValueError("producer v2 retained receipt missing or invalid")
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
        "schema": "behavior-v12-correction-independent-verification/v2",
        "passed": True,
        "scientific_admission": False,
        "registration_sha256": file_sha(output / "registration.json"),
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
    parser.add_argument("--validation-v2", action="store_true")
    args = parser.parse_args()
    result = (verify_retained_v2(args.repo.resolve(), args.output.resolve())
              if args.validation_v2 else verify(args.repo.resolve(), args.output.resolve()))
    trial_count = result.get("trial_count", result.get("coverage", {}).get("trials"))
    if not isinstance(trial_count, int):
        raise ValueError("verification result is missing trial coverage")
    print(json.dumps({"passed": result["passed"], "trial_count": trial_count}, sort_keys=True))


if __name__ == "__main__":
    main()
