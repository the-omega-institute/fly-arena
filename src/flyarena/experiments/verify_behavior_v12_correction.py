"""Independent verifier for the sealed v12 retained-data correction."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import time

import mujoco as mj
import numpy as np

from ..common import file_sha, write_json
from .mechanical_v12 import CONTACT, CORE, DT, _slices, _width


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
    window = np.asarray(state[lo:hi + 1], dtype=bool)
    changes = np.flatnonzero(np.r_[True, window[1:] != window[:-1], True])
    complete, partial, invalid = [], [], []
    for left, right in zip(changes[:-1], changes[1:]):
        if not window[left]:
            continue
        start, end = lo + int(left), lo + int(right)
        if start == lo or end == hi + 1:
            partial.append((start, end))
        elif phase[end - 1] <= phase[start]:
            invalid.append((start, end))
        else:
            complete.append((start, end))
    return complete, partial, invalid


def _cycle_gate(phases, ap, heights, normal, weighted, periods):
    recovery_all = True
    support_all = True
    invalid_total = 0
    status = []
    for leg, name in enumerate(LEGS):
        start_phase, end_phase = periods[name]
        mod = np.mod(phases[:, leg], 2 * np.pi)
        swing_runs, swing_partial, swing_invalid = _runs(
            (mod > start_phase) & (mod < end_phase), phases[:, leg]
        )
        stance_runs, stance_partial, stance_invalid = _runs(
            ~((mod > start_phase) & (mod < end_phase)), phases[:, leg]
        )
        invalid_total += len(swing_invalid) + len(stance_invalid)
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
        if not swing_runs or swing_invalid:
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
        if not stance_runs or stance_invalid:
            support_all = False
        status.append({
            "leg": name,
            "swings": swing_status,
            "stances": stance_status,
            "swing_boundary_partials": len(swing_partial),
            "stance_boundary_partials": len(stance_partial),
            "invalid": len(swing_invalid) + len(stance_invalid),
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.repo.resolve(), args.output.resolve())
    print(json.dumps({"passed": result["passed"], "trial_count": result["trial_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
