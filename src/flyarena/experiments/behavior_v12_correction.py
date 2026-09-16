"""Phase-correct, retained-data-only analysis for the frozen v12 experiment.

This module is additive.  It never changes or regrades the historical v12
receipt.  The correction binds solver contact rows to their owning integration
interval and reconstructs endpoint geometry from the separately retained core
state.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys
import time
import traceback
from typing import Callable
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np

from ..common import file_sha, write_json
from .mechanical_v12 import CONTACT, CORE, DENSE, DT, _slices, _width


TOLERANCE = 5e-12
ROWS = 40001
ANALYSIS_TICKS = (6000, 25000)
LEGS = ("lf", "lm", "lh", "rf", "rm", "rh")
IMMUTABLE_SOURCE_HASHES = {
    "docs/BEHAVIOR_V12_RESULTS.md": "c445c07f628cae004c77ac5e22889db321ae13d98a1c93ab8a4ec80b0fec677d",
    "docs/evidence/behavior-v12-failure.png": "55c335d3a0ef37a5e3ef1dd9479ba110649ef58b3b71b1c5bca067b5a87bd929",
    "scripts/behavior_v12.sh": "ea108523becd002054599a24e78b594fac5b2daa437e1d039fe2030333f6f5c8",
    "scripts/plot_behavior_v12.py": "1211282ebe700dbccd2a281c3088948957cf76bc85fc80922d72fe4f1c8e14b1",
    "src/flyarena/experiments/cadence_v12.py": "6dc960b1eaf6bb37ec97ba6793cdd1582006d773cc9c460095f73f796288f7d0",
    "src/flyarena/experiments/mechanical_v12.py": "a03ed8309acbf8a30d68cb1775fe1d65e9bfde10f5979510dd0453098886bacc",
    "src/flyarena/experiments/verify_v12.py": "e12c8209a03412acefef4977f5061abcff271a0f7f9b40e1a5a0df64871f6de5",
    "tests/test_behavior_v12.py": "2f0328d65fd8a038405d34037e93b275f9ba6e602b9b53ce53b3b34db62bb1e6",
}
ORIGINAL_INDEX_SHA256 = "2feab6649e24a2b8d3dde616cdfd4ef0db13d723bd1b232aa7d631ecb7aeae1f"
ORIGINAL_ARCHIVE_SHA256 = "b9f5921112812e23f7f581bbc24c776178946e9148bba10cba2e2f5830b53bf8"


def _json_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def _failure(exc: BaseException) -> dict:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(exc)),
    }


def _int_column(values: np.ndarray, selector: slice) -> np.ndarray:
    """Return a one-column schema slice as a row-aligned integer vector."""
    result = np.asarray(values[:, selector], dtype=np.int64).reshape(-1)
    if result.shape != (len(values),):
        raise ValueError("invalid one-column schema slice")
    return result


def _write_exclusive_json(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(path)
    write_json(path, value)


@dataclass(frozen=True)
class PairedNativeCapture:
    """One native integration with cache and integration endpoints separated."""

    state_start_qpos: np.ndarray
    state_start_qvel: np.ndarray
    state_start_time: float
    state_end_qpos: np.ndarray
    state_end_qvel: np.ndarray
    state_end_time: float
    cache_geom_xpos: np.ndarray
    cache_geom_xmat: np.ndarray
    contact_rows: np.ndarray


CAPTURE_CONTACT_WIDTH = 1 + 2 + 1 + 3 + 9 + 6 + 3


def capture_native_step(
    model: mj.MjModel,
    data: mj.MjData,
    step_fn: Callable[[mj.MjModel, mj.MjData], None] = mj.mj_step,
) -> PairedNativeCapture:
    """Capture one step without forwarding or otherwise observing live dynamics.

    ``step_fn`` is invoked exactly once.  All reads after it are cache reads or
    non-mutating Jacobian/contact-force queries; no forward call is made on the
    live ``MjData``.
    """
    start_qpos = np.asarray(data.qpos, dtype=np.float64).copy()
    start_qvel = np.asarray(data.qvel, dtype=np.float64).copy()
    start_time = float(data.time)
    step_fn(model, data)
    rows = []
    wrench = np.empty(6, dtype=np.float64)
    jac1 = np.zeros((3, model.nv), dtype=np.float64)
    jac2 = np.zeros((3, model.nv), dtype=np.float64)
    for index in range(data.ncon):
        contact = data.contact[index]
        point = np.asarray(contact.pos, dtype=np.float64).copy()
        body1 = int(model.geom_bodyid[int(contact.geom1)])
        body2 = int(model.geom_bodyid[int(contact.geom2)])
        jac1.fill(0)
        jac2.fill(0)
        mj.mj_jac(model, data, jac1, None, point, body1)
        mj.mj_jac(model, data, jac2, None, point, body2)
        hybrid_velocity = (jac1 - jac2) @ data.qvel
        mj.mj_contactForce(model, data, index, wrench)
        rows.append(np.concatenate([
            [index, int(contact.geom1), int(contact.geom2), float(contact.dist)],
            point,
            np.asarray(contact.frame, dtype=np.float64).copy(),
            wrench.copy(),
            hybrid_velocity,
        ]))
    contacts = (np.asarray(rows, dtype=np.float64).reshape(-1, CAPTURE_CONTACT_WIDTH)
                if rows else np.empty((0, CAPTURE_CONTACT_WIDTH), dtype=np.float64))
    return PairedNativeCapture(
        state_start_qpos=start_qpos,
        state_start_qvel=start_qvel,
        state_start_time=start_time,
        state_end_qpos=np.asarray(data.qpos, dtype=np.float64).copy(),
        state_end_qvel=np.asarray(data.qvel, dtype=np.float64).copy(),
        state_end_time=float(data.time),
        cache_geom_xpos=np.asarray(data.geom_xpos, dtype=np.float64).copy(),
        cache_geom_xmat=np.asarray(data.geom_xmat, dtype=np.float64).copy(),
        contact_rows=contacts,
    )


def _integration_state(model: mj.MjModel, data: mj.MjData) -> np.ndarray:
    signature = mj.mjtState.mjSTATE_INTEGRATION
    out = np.empty(mj.mj_stateSize(model, signature), dtype=np.float64)
    mj.mj_getState(model, data, out, signature)
    return out


def _body_point_velocities(
    model: mj.MjModel,
    data: mj.MjData,
    points: np.ndarray,
    body1: np.ndarray,
    body2: np.ndarray,
) -> np.ndarray:
    """Native object-velocity equivalent of point Jacobian material velocity."""
    velocities: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for body in np.unique(np.r_[body1, body2]):
        value = np.empty(6, dtype=np.float64)
        mj.mj_objectVelocity(model, data, mj.mjtObj.mjOBJ_BODY, int(body), value, 0)
        velocities[int(body)] = (value[:3].copy(), value[3:].copy(), data.xipos[int(body)].copy())

    def point_velocity(bodies: np.ndarray) -> np.ndarray:
        result = np.empty((len(points), 3), dtype=np.float64)
        for body in np.unique(bodies):
            selected = bodies == body
            angular, linear, origin = velocities[int(body)]
            result[selected] = linear + np.cross(angular, points[selected] - origin)
        return result

    return point_velocity(body1) - point_velocity(body2)


def _prepare_detached_state(
    model: mj.MjModel, data: mj.MjData, qpos: np.ndarray, qvel: np.ndarray
) -> None:
    data.qpos[:] = qpos
    data.qvel[:] = qvel
    mj.mj_kinematics(model, data)
    mj.mj_comPos(model, data)
    mj.mj_fwdVelocity(model, data)


def _point_jacobian_velocities(
    model: mj.MjModel,
    data: mj.MjData,
    points: np.ndarray,
    body1: np.ndarray,
    body2: np.ndarray,
) -> np.ndarray:
    out = np.empty((len(points), 3), dtype=np.float64)
    jac1 = np.zeros((3, model.nv), dtype=np.float64)
    jac2 = np.zeros((3, model.nv), dtype=np.float64)
    for index, point in enumerate(points):
        jac1.fill(0)
        jac2.fill(0)
        mj.mj_jac(model, data, jac1, None, point, int(body1[index]))
        mj.mj_jac(model, data, jac2, None, point, int(body2[index]))
        out[index] = (jac1 - jac2) @ data.qvel
    return out


def _foot_metadata(model: mj.MjModel, registration: dict) -> dict:
    foot = np.asarray(registration["measurement"]["foot_geom_ids"], dtype=np.int64)
    if foot.shape != (30,) or len(np.unique(foot)) != 30:
        raise ValueError("invalid frozen foot geometry identities")
    thorax = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, "fly-0/c_thorax")
    ground = mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, "ground_plane")
    vertices = []
    centroids = []
    for geom in foot:
        mesh = int(model.geom_dataid[int(geom)])
        begin = int(model.mesh_vertadr[mesh])
        count = int(model.mesh_vertnum[mesh])
        # The cast intentionally precedes the mean.  This is the corrected
        # arithmetic order and exactly matches the historical recorder.
        value = np.asarray(model.mesh_vert[begin:begin + count], dtype=np.float64)
        vertices.append(value)
        centroids.append(value.mean(axis=0, dtype=np.float64))
    leg_by_geom = np.full(model.ngeom, -1, dtype=np.int64)
    leg_by_geom[foot] = np.arange(30, dtype=np.int64) // 5
    return {
        "foot": foot,
        "thorax": int(thorax),
        "ground": int(ground),
        "vertices": vertices,
        "centroids": np.asarray(centroids, dtype=np.float64),
        "leg_by_geom": leg_by_geom,
    }


def _geometry_from_prepared(data: mj.MjData, meta: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    heights = np.full(6, np.inf, dtype=np.float64)
    centers = np.empty((6, 3), dtype=np.float64)
    for index, geom in enumerate(meta["foot"]):
        rotation = data.geom_xmat[int(geom)].reshape(3, 3)
        low = float((meta["vertices"][index] @ rotation[2]).min() + data.geom_xpos[int(geom), 2])
        leg = index // 5
        heights[leg] = min(heights[leg], low)
        if index % 5 == 4:
            centers[leg] = rotation @ meta["centroids"][index] + data.geom_xpos[int(geom)]
    thorax = meta["thorax"]
    rotation = data.xmat[thorax].reshape(3, 3)
    ap = (centers - data.xpos[thorax]) @ rotation[:, 0]
    return heights, centers, ap


def _read_stream(path: Path, expected_rows: int | None, width: int) -> tuple[np.ndarray, np.ndarray, dict]:
    terminal = json.loads((path / "terminal.json").read_text())
    if (not terminal["complete"] or terminal["primary_failure"] is not None
            or terminal["retention_failures"]):
        raise ValueError(f"incomplete retained stream: {path}")
    rows = int(terminal["initialized_rows"])
    if expected_rows is not None and rows != expected_rows:
        raise ValueError(f"wrong retained row count: {path}")
    chunks = sorted(path.glob("chunk-*.npz"))
    expected_names = {name for name in terminal["files"] if name.startswith("chunk-")}
    if {p.name for p in chunks} != expected_names:
        raise ValueError("chunk manifest mismatch")
    all_ticks, all_values = [], []
    for index, chunk in enumerate(chunks):
        if chunk.name != f"chunk-{index:05d}.npz" or file_sha(chunk) != terminal["files"][chunk.name]:
            raise ValueError("chunk order/hash mismatch")
        with np.load(chunk, allow_pickle=False) as archive:
            if set(archive.files) != {"ticks", "values"}:
                raise ValueError("invalid retained archive fields")
            ticks = archive["ticks"]
            values = archive["values"]
            if (ticks.dtype != np.int64 or values.dtype != np.float64
                    or values.shape != (len(ticks), width) or not np.isfinite(values).all()):
                raise ValueError("invalid retained archive dtype/shape/value")
            all_ticks.append(ticks)
            all_values.append(values)
    ticks = np.concatenate(all_ticks) if all_ticks else np.empty(0, dtype=np.int64)
    values = (np.concatenate(all_values) if all_values
              else np.empty((0, width), dtype=np.float64))
    if len(ticks) != rows:
        raise ValueError("retained terminal row count mismatch")
    return ticks, values, terminal


def _read_dense(path: Path, width: int) -> tuple[np.ndarray, np.ndarray, dict]:
    ticks, values, terminal = _read_stream(path, ROWS, width)
    if not np.array_equal(ticks, np.arange(ROWS, dtype=np.int64)):
        raise ValueError("malformed dense grid")
    return ticks, values, terminal


def _partition_true_runs(state: np.ndarray, phase: np.ndarray, lo: int, hi: int) -> dict:
    if state.shape != phase.shape or not np.isfinite(phase[lo:hi + 1]).all():
        raise ValueError("invalid phase/run inputs")
    window = np.asarray(state[lo:hi + 1], dtype=bool)
    changes = np.flatnonzero(np.r_[True, window[1:] != window[:-1], True])
    complete, boundary, invalid = [], [], []
    for left, right in zip(changes[:-1], changes[1:]):
        if not window[left]:
            continue
        start = lo + int(left)
        end = lo + int(right)
        record = {"start_tick": start, "end_tick_exclusive": end}
        if start == lo or end == hi + 1:
            record["reason"] = "analysis-window boundary"
            boundary.append(record)
        elif phase[end - 1] <= phase[start]:
            record.update(
                reason="nonincreasing interior phase",
                phase_start=float(phase[start]),
                phase_end=float(phase[end - 1]),
            )
            invalid.append(record)
        else:
            complete.append((start, end))
    return {"complete": complete, "boundary_partials": boundary, "invalid_interior": invalid}


def _longest_true(values: np.ndarray) -> int:
    padded = np.r_[False, np.asarray(values, dtype=bool), False]
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return int(np.max(changes[1::2] - changes[::2], initial=0))


def _median31(values: np.ndarray) -> np.ndarray:
    if len(values) < 31:
        return np.empty(0, dtype=np.float64)
    return np.median(np.lib.stride_tricks.sliding_window_view(values, 31), axis=1)


def _cycle_metrics(
    phases: np.ndarray,
    ap: np.ndarray,
    heights: np.ndarray,
    normal: np.ndarray,
    weighted_pre: np.ndarray,
    peak_pre: np.ndarray,
    periods: dict,
) -> dict:
    swings, stances, partitions = [], [], []
    all_swings = True
    all_stances = True
    invalid_interior_total = 0
    for leg, leg_name in enumerate(LEGS):
        start_phase, end_phase = periods[leg_name]
        phase = phases[:, leg]
        mod = np.mod(phase, 2 * np.pi)
        commanded_swing = (mod > start_phase) & (mod < end_phase)
        swing_partition = _partition_true_runs(commanded_swing, phase, *ANALYSIS_TICKS)
        stance_partition = _partition_true_runs(~commanded_swing, phase, *ANALYSIS_TICKS)
        invalid_count = len(swing_partition["invalid_interior"]) + len(stance_partition["invalid_interior"])
        invalid_interior_total += invalid_count
        leg_swings = []
        for begin, end in swing_partition["complete"]:
            raw = ap[begin:end, leg]
            filtered = _median31(raw)
            record = {
                "start_tick": begin,
                "end_tick_exclusive": end,
                "endpoint_source_rows": [begin, end - 1],
                "raw_ap_samples": int(len(raw)),
                "raw_ap_min_mm": float(raw.min()),
                "raw_ap_max_mm": float(raw.max()),
                "filtered_ticks": [begin + 15, end - 16],
            }
            passed = False
            if not len(filtered):
                record.update(status="inconclusive", reason="no full 31-sample median window")
            else:
                minimum, maximum = float(filtered.min()), float(filtered.max())
                pep_local = int(np.flatnonzero(filtered == minimum)[0])
                later = np.flatnonzero((filtered == maximum) & (np.arange(len(filtered)) > pep_local))
                diffs = np.diff(filtered)
                signs = np.sign(diffs[diffs != 0])
                reversals = int(np.count_nonzero(signs[1:] != signs[:-1])) if len(signs) > 1 else 0
                record.update(
                    filtered_min_mm=minimum,
                    filtered_max_mm=maximum,
                    min_ties=int(np.count_nonzero(filtered == minimum)),
                    max_ties=int(np.count_nonzero(filtered == maximum)),
                    flat_differences=int(np.count_nonzero(diffs == 0)),
                    reversals=reversals,
                )
                if not len(later):
                    record.update(status="inconclusive", reason="global maximum not later than earliest global minimum")
                else:
                    aep_local = int(later[0])
                    pep = begin + 15 + pep_local
                    aep = begin + 15 + aep_local
                    excursion = maximum - minimum
                    # Endpoint pose k is joined to the separately owned interval
                    # row k.  Tick zero never reaches this analysis window.
                    recovery = (heights[pep:aep + 1, leg] > 0.02) & (normal[pep:aep + 1, leg] == 0)
                    dwell = _longest_true(recovery)
                    passed = bool(aep > pep and excursion > 0.02 and dwell >= 30)
                    record.update(
                        status="pass" if passed else "fail",
                        pep_tick=pep,
                        aep_tick=aep,
                        interval_rows=[pep, aep],
                        duration_s=(aep - pep) * DT,
                        excursion_mm=float(excursion),
                        recovery_dwell_ticks=dwell,
                        recovery_dwell_s=dwell * DT,
                        peak_whole_foot_height_mm=float(heights[pep:aep + 1, leg].max()),
                    )
            all_swings &= passed
            leg_swings.append(record)
        if not leg_swings or swing_partition["invalid_interior"]:
            all_swings = False

        leg_stances = []
        for begin, end in stance_partition["complete"]:
            loaded = normal[begin:end, leg] > 0
            support_dwell = _longest_true(loaded)
            ratios = np.divide(
                weighted_pre[begin:end, leg],
                normal[begin:end, leg],
                out=np.zeros(end - begin, dtype=np.float64),
                where=loaded,
            )
            slip = float(DT * ratios.sum())
            passed = bool(support_dwell >= 30 and slip < 0.15)
            leg_stances.append({
                "start_tick": begin,
                "end_tick_exclusive": end,
                "owned_interval_rows": [begin, end - 1],
                "status": "pass" if passed else "fail",
                "support_dwell_ticks": support_dwell,
                "support_dwell_s": support_dwell * DT,
                "slip_mm": slip,
                "loaded_intervals": int(loaded.sum()),
                "force_impulse_native_s": float(DT * normal[begin:end, leg].sum()),
                "peak_pre_state_contact_tangent_speed_mm_s": float(peak_pre[begin:end, leg].max(initial=0)),
            })
            all_stances &= passed
        if not leg_stances or stance_partition["invalid_interior"]:
            all_stances = False
        swings.append(leg_swings)
        stances.append(leg_stances)
        partitions.append({
            "leg": leg_name,
            "swing_boundary_partials": swing_partition["boundary_partials"],
            "stance_boundary_partials": stance_partition["boundary_partials"],
            "swing_invalid_interior": swing_partition["invalid_interior"],
            "stance_invalid_interior": stance_partition["invalid_interior"],
        })
    return {
        "swing_cycles": swings,
        "stance_cycles": stances,
        "phase_partitions": partitions,
        "invalid_interior_phase_episodes": invalid_interior_total,
        "recovery_passed": bool(all_swings),
        "support_slip_passed": bool(all_stances),
    }


def _expected_trials(registration: dict) -> dict[str, tuple[str, int, list]]:
    return {
        f"{profile}--{seed}--{case[0]}": (profile, seed, case)
        for profile in registration["profiles"]
        for seed in registration["development_seeds"]
        for case in registration["cases"]
    }


def _validate_model_arrays(root: Path, model: mj.MjModel, original_registration: dict) -> dict:
    checked = 0
    for name, record in original_registration["compiled_arrays"].items():
        path = root / f"model-{name}.npy"
        if file_sha(path) != record["sha256"]:
            raise ValueError(f"frozen model array hash mismatch: {name}")
        saved = np.load(path, allow_pickle=False)
        live = np.asarray(getattr(model, name))
        if saved.shape != live.shape or saved.dtype != live.dtype or not np.array_equal(saved, live):
            raise ValueError(f"MJB array differs from frozen array: {name}")
        checked += 1
    return {"arrays_checked": checked, "all_exact": True, "mesh_arithmetic": "float64 cast before mean"}


def _validate_trial_identity(
    original_root: Path,
    trial: Path,
    original_registration: dict,
    expected: tuple[str, int, list],
) -> dict:
    starts = [json.loads((trial / stream / "start.json").read_text()) for stream in ("core", "dense", "contacts")]
    if starts[0] != starts[1] or starts[0] != starts[2]:
        raise ValueError("stream identities differ")
    meta = starts[0]
    profile, seed, case = expected
    if (meta.get("profile"), meta.get("seed"), meta.get("case"), meta.get("stage")) != (
        profile, seed, case, "development"
    ):
        raise ValueError("trial identity mismatch")
    if (meta.get("registration_sha256") != file_sha(original_root / "registration.json")
            or meta.get("sources_sha256") != original_registration["sources_sha256"]):
        raise ValueError("trial source/registration binding mismatch")
    return meta


def _analyze_trial(
    original_root: Path,
    trial: Path,
    expected: tuple[str, int, list],
    original_registration: dict,
    model: mj.MjModel,
    model_meta: dict,
    derived_dir: Path,
) -> dict:
    cs, ds, es = _slices(CORE), _slices(DENSE), _slices(CONTACT)
    meta = _validate_trial_identity(original_root, trial, original_registration, expected)
    ticks, core, core_terminal = _read_dense(trial / "core", _width(CORE))
    _, dense, dense_terminal = _read_dense(trial / "dense", _width(DENSE))
    contact_terminal = json.loads((trial / "contacts" / "terminal.json").read_text())
    contact_ticks, contacts, contact_terminal = _read_stream(
        trial / "contacts", int(contact_terminal["initialized_rows"]), _width(CONTACT)
    )
    if (len(contact_ticks) and (contact_ticks[0] < 0 or contact_ticks[-1] >= ROWS
            or np.any(np.diff(contact_ticks) < 0))):
        raise ValueError("malformed contact tick grid")
    _, common, asymmetry = meta["case"]
    expected_input = np.zeros((ROWS, 2), dtype=np.float64)
    expected_input[3001:25001] = [common * (1 - asymmetry), common * (1 + asymmetry)]
    if not np.array_equal(core[:, cs["input"]], expected_input):
        raise ValueError("registered waveform mismatch")

    endpoint_height = np.empty((ROWS, 6), dtype=np.float64)
    endpoint_center = np.empty((ROWS, 6, 3), dtype=np.float64)
    endpoint_ap = np.empty((ROWS, 6), dtype=np.float64)
    interval_normal = np.zeros((ROWS, 6), dtype=np.float64)
    interval_weighted_pre = np.zeros((ROWS, 6), dtype=np.float64)
    interval_peak_pre = np.zeros((ROWS, 6), dtype=np.float64)
    rebuilt_normal = np.zeros((ROWS, 6), dtype=np.float64)
    rebuilt_hybrid_weighted = np.zeros((ROWS, 6), dtype=np.float64)
    rebuilt_hybrid_peak = np.zeros((ROWS, 6), dtype=np.float64)
    rebuilt_counts = np.zeros((ROWS, 6), dtype=np.float64)
    rebuilt_positive = np.zeros((ROWS, 6), dtype=np.float64)
    groups: dict[int, tuple[int, int]] = {}
    if len(contact_ticks):
        unique, first, counts = np.unique(contact_ticks, return_index=True, return_counts=True)
        groups = {int(tick): (int(begin), int(begin + count)) for tick, begin, count in zip(unique, first, counts)}

    detached = mj.MjData(model)
    max_hybrid_error = 0.0
    max_object_jacobian_error = 0.0
    max_wrong_same_row_velocity_error = 0.0
    checked_velocities = 0
    sampled_wrong_velocities = 0
    for state_tick in range(ROWS):
        _prepare_detached_state(
            model,
            detached,
            core[state_tick, cs["qpos"]],
            core[state_tick, cs["qvel"]],
        )
        endpoint_height[state_tick], endpoint_center[state_tick], endpoint_ap[state_tick] = _geometry_from_prepared(
            detached, model_meta
        )

        # At state k, derive coherent material velocity for interval row k+1.
        interval_tick = state_tick + 1
        if interval_tick < ROWS and interval_tick in groups:
            begin, end = groups[interval_tick]
            event = contacts[begin:end]
            foot_geom = _int_column(event, es["foot_geom"])
            ground_geom = _int_column(event, es["ground_geom"])
            if (np.any(foot_geom < 0) or np.any(foot_geom >= model.ngeom)
                    or np.any(ground_geom != model_meta["ground"])):
                raise ValueError("invalid retained contact identity")
            legs = model_meta["leg_by_geom"][foot_geom]
            if np.any(legs < 0):
                raise ValueError("contact does not own a frozen foot geometry")
            points = event[:, es["position"]]
            body1 = model.geom_bodyid[foot_geom].astype(np.int64)
            body2 = model.geom_bodyid[ground_geom].astype(np.int64)
            pre_velocity = _body_point_velocities(model, detached, points, body1, body2)
            if interval_tick % 100 == 0:
                jacobian_velocity = _point_jacobian_velocities(model, detached, points, body1, body2)
                max_object_jacobian_error = max(
                    max_object_jacobian_error,
                    float(np.max(np.abs(pre_velocity - jacobian_velocity), initial=0)),
                )

            # Positions stay at state_start while qvel advances to state_end:
            # this reproduces and labels the historical hybrid diagnostic.
            detached.qvel[:] = core[interval_tick, cs["qvel"]]
            mj.mj_fwdVelocity(model, detached)
            hybrid = _body_point_velocities(model, detached, points, body1, body2)
            saved_hybrid = event[:, es["relative_velocity_world"]]
            max_hybrid_error = max(max_hybrid_error, float(np.max(np.abs(hybrid - saved_hybrid), initial=0)))
            checked_velocities += len(event)

            frames = event[:, es["frame"]].reshape(-1, 3, 3)
            normals = frames[:, 0]
            tangent_pre = pre_velocity - normals * np.sum(pre_velocity * normals, axis=1)[:, None]
            tangent_hybrid = saved_hybrid - normals * np.sum(saved_hybrid * normals, axis=1)[:, None]
            speed_pre = np.linalg.norm(tangent_pre, axis=1)
            speed_hybrid = np.linalg.norm(tangent_hybrid, axis=1)
            fn = event[:, es["wrench_contact_frame"]][:, 0]
            loaded = fn > 0
            np.add.at(rebuilt_counts[interval_tick], legs, 1)
            np.maximum.at(rebuilt_hybrid_peak[interval_tick], legs, speed_hybrid)
            np.maximum.at(interval_peak_pre[interval_tick], legs, speed_pre)
            if np.any(loaded):
                np.add.at(rebuilt_normal[interval_tick], legs[loaded], fn[loaded])
                np.add.at(interval_normal[interval_tick], legs[loaded], fn[loaded])
                np.add.at(interval_weighted_pre[interval_tick], legs[loaded], fn[loaded] * speed_pre[loaded])
                np.add.at(rebuilt_hybrid_weighted[interval_tick], legs[loaded], fn[loaded] * speed_hybrid[loaded])
                np.add.at(rebuilt_positive[interval_tick], legs[loaded], 1)

        # A sampled deliberately wrong same-row calculation must not match the
        # saved hybrid velocity.  It is diagnostic only and never feeds metrics.
        if state_tick and state_tick % 100 == 0 and state_tick in groups:
            detached.qvel[:] = core[state_tick, cs["qvel"]]
            mj.mj_fwdVelocity(model, detached)
            begin, end = groups[state_tick]
            event = contacts[begin:end]
            points = event[:, es["position"]]
            foot_geom = _int_column(event, es["foot_geom"])
            ground_geom = _int_column(event, es["ground_geom"])
            wrong = _body_point_velocities(
                model,
                detached,
                points,
                model.geom_bodyid[foot_geom].astype(np.int64),
                model.geom_bodyid[ground_geom].astype(np.int64),
            )
            saved = event[:, es["relative_velocity_world"]]
            max_wrong_same_row_velocity_error = max(
                max_wrong_same_row_velocity_error,
                float(np.max(np.abs(wrong - saved), initial=0)),
            )
            sampled_wrong_velocities += len(event)

    # Tick zero has contacts but no completed interval.  Rebuild only its
    # historical summaries, then keep correction quadrature arrays at zero.
    if 0 in groups:
        begin, end = groups[0]
        event = contacts[begin:end]
        foot_geom = _int_column(event, es["foot_geom"])
        legs = model_meta["leg_by_geom"][foot_geom]
        saved = event[:, es["relative_velocity_world"]]
        frames = event[:, es["frame"]].reshape(-1, 3, 3)
        normals = frames[:, 0]
        speeds = np.linalg.norm(saved - normals * np.sum(saved * normals, axis=1)[:, None], axis=1)
        fn = event[:, es["wrench_contact_frame"]][:, 0]
        loaded = fn > 0
        np.add.at(rebuilt_counts[0], legs, 1)
        np.maximum.at(rebuilt_hybrid_peak[0], legs, speeds)
        if np.any(loaded):
            np.add.at(rebuilt_normal[0], legs[loaded], fn[loaded])
            np.add.at(rebuilt_hybrid_weighted[0], legs[loaded], fn[loaded] * speeds[loaded])
            np.add.at(rebuilt_positive[0], legs[loaded], 1)

    expected_cache_height = np.vstack([endpoint_height[0], endpoint_height[:-1]])
    expected_cache_center = np.concatenate([endpoint_center[[0]], endpoint_center[:-1]], axis=0)
    expected_cache_ap = np.vstack([endpoint_ap[0], endpoint_ap[:-1]])
    saved_height = dense[:, ds["whole_foot_min_height"]]
    saved_center = dense[:, ds["tarsus5_centroid"]].reshape(ROWS, 6, 3)
    saved_ap = dense[:, ds["thorax_ap"]]
    cache_error = float(np.max(np.abs(np.concatenate([
        (saved_height - expected_cache_height).ravel(),
        (saved_center - expected_cache_center).ravel(),
        (saved_ap - expected_cache_ap).ravel(),
    ]))))
    next_cache_error = float(np.max(np.abs(np.concatenate([
        (dense[1:, ds["whole_foot_min_height"]] - endpoint_height[:-1]).ravel(),
        (dense[1:, ds["tarsus5_centroid"]].reshape(ROWS - 1, 6, 3) - endpoint_center[:-1]).ravel(),
        (dense[1:, ds["thorax_ap"]] - endpoint_ap[:-1]).ravel(),
    ]))))
    wrong_same_row_geometry_error = float(np.max(np.abs(np.concatenate([
        (saved_height - endpoint_height).ravel(),
        (saved_center - endpoint_center).ravel(),
        (saved_ap - endpoint_ap).ravel(),
    ]))))
    saved_summary = np.stack([
        dense[:, ds["summed_positive_normal"]],
        dense[:, ds["force_weighted_tangent_numerator"]],
        dense[:, ds["peak_tangent_speed"]],
        dense[:, ds["contact_count"]],
        dense[:, ds["positive_force_count"]],
    ], axis=2)
    rebuilt_summary = np.stack([
        rebuilt_normal,
        rebuilt_hybrid_weighted,
        rebuilt_hybrid_peak,
        rebuilt_counts,
        rebuilt_positive,
    ], axis=2)
    if not np.array_equal(saved_summary, rebuilt_summary):
        raise ValueError("raw contacts do not exactly close the historical dense summaries")
    interval_normal[0] = 0
    if (cache_error > TOLERANCE or next_cache_error > TOLERANCE
            or max_hybrid_error > TOLERANCE or max_object_jacobian_error > TOLERANCE):
        raise ValueError("strict paired-state reconstruction tolerance exceeded")
    if wrong_same_row_geometry_error <= TOLERANCE or max_wrong_same_row_velocity_error <= TOLERANCE:
        raise ValueError("deliberately wrong phase pairing was not detected")

    phases = core[:, cs["phases"]]
    cycle = _cycle_metrics(
        phases,
        endpoint_ap,
        endpoint_height,
        interval_normal,
        interval_weighted_pre,
        interval_peak_pre,
        original_registration["controller"]["swing_periods_strict_modulo"],
    )
    position = core[:, cs["thorax_position"]]
    rotation = core[:, cs["thorax_rotation"]].reshape(-1, 3, 3)
    yaw = np.unwrap(np.arctan2(rotation[:, 1, 0], rotation[:, 0, 0]))
    velocity = np.diff(position, axis=0) / DT
    forward = (velocity[6000:25000] * rotation[6000:25000, :, 0]).sum(axis=1)
    stop_speed = float(np.linalg.norm(velocity[30000:40000], axis=1).mean())
    stop_displacement = float(np.linalg.norm(position[40000] - position[30000]))
    min_upright = float(rotation[:, 2, 2].min())
    net_yaw = float(yaw[25000] - yaw[3000])
    yaw_rate = float((yaw[25000] - yaw[6000]) / 1.9)
    gates = {
        "finite": True,
        "upright": min_upright > 0.8,
        "stop": stop_displacement < 0.25 and stop_speed < 0.1,
    }
    if common > 0:
        gates["recovery"] = cycle["recovery_passed"]
        gates["support_slip"] = cycle["support_slip_passed"]
        if asymmetry:
            gates["turn"] = bool(np.sign(net_yaw) == np.sign(asymmetry) and abs(net_yaw) > 0.1)
        else:
            gates["straight_yaw"] = abs(yaw_rate) < 0.15

    derived_path = derived_dir / f"{trial.name}.npz"
    with derived_path.open("xb") as handle:
        np.savez_compressed(
            handle,
            ticks=ticks,
            endpoint_source_core_row=ticks,
            endpoint_thorax_ap=endpoint_ap,
            endpoint_whole_foot_min_height=endpoint_height,
            interval_contact_row_tick=ticks,
            interval_state_start_core_row=np.r_[-1, np.arange(ROWS - 1, dtype=np.int64)],
            interval_state_end_core_row=ticks,
            interval_summed_positive_normal=interval_normal,
            interval_force_weighted_pre_tangent=interval_weighted_pre,
            interval_peak_pre_tangent_speed=interval_peak_pre,
        )
    return {
        "schema": "behavior-v12-correction-trial/v1",
        "conditions": meta,
        "state_contract": {
            "tick_zero": "initialization only; no completed interval and zero correction quadrature",
            "interval_k": "((k-1)*dt,k*dt], k>=1",
            "state_start": "core[k-1] qpos/qvel",
            "state_end": "core[k] qpos/qvel and authoritative endpoint pose",
            "raw_cache": "dense/contact/frame/wrench row k at state_start qpos",
            "slip_velocity": "J(qpos[k-1])@qvel[k-1] left endpoint",
            "saved_velocity": "historical diagnostic only: J(qpos[k-1])@qvel[k]",
            "final_endpoint": "core[40000] reconstructed; no next-row cache exists",
        },
        "gates": gates,
        "forward_mean_mm_s": float(forward.mean()),
        "mean_yaw_rate_rad_s": yaw_rate,
        "net_active_yaw_rad": net_yaw,
        "min_upright_z": min_upright,
        "stop_displacement_mm": stop_displacement,
        "stop_mean_speed_mm_s": stop_speed,
        **cycle,
        "raw_contact_rows": int(len(contacts)),
        "tick_zero_contact_rows_excluded_from_quadrature": int(np.count_nonzero(contact_ticks == 0)),
        "paired_state_verification": {
            "tolerance": TOLERANCE,
            "cache_vs_state_start_max_abs_mm": cache_error,
            "endpoint_vs_next_cache_max_abs_mm": next_cache_error,
            "wrong_same_row_geometry_max_abs_mm": wrong_same_row_geometry_error,
            "saved_hybrid_velocity_max_abs_mm_s": max_hybrid_error,
            "pre_object_velocity_vs_jacobian_max_abs_mm_s": max_object_jacobian_error,
            "wrong_same_row_velocity_max_abs_mm_s": max_wrong_same_row_velocity_error,
            "all_contact_velocities_checked": checked_velocities,
            "sampled_wrong_same_row_velocities": sampled_wrong_velocities,
        },
        "source_terminals": {
            "core": file_sha(trial / "core" / "terminal.json"),
            "dense": file_sha(trial / "dense" / "terminal.json"),
            "contacts": file_sha(trial / "contacts" / "terminal.json"),
            "trial": file_sha(trial / "trial-terminal.json"),
            "core_rows": int(core_terminal["initialized_rows"]),
            "dense_rows": int(dense_terminal["initialized_rows"]),
            "contact_rows": int(contact_terminal["initialized_rows"]),
        },
        "derived_npz": str(derived_path.name),
        "derived_npz_sha256": file_sha(derived_path),
    }


def _verify_original_immutability(repo: Path) -> dict:
    changed = {}
    for relative, expected in IMMUTABLE_SOURCE_HASHES.items():
        actual = file_sha(repo / relative)
        if actual != expected:
            changed[relative] = {"expected": expected, "actual": actual}
    index = repo / "var/behavior-v12/evidence-index.json"
    actual_index = file_sha(index)
    if actual_index != ORIGINAL_INDEX_SHA256:
        changed[str(index.relative_to(repo))] = {"expected": ORIGINAL_INDEX_SHA256, "actual": actual_index}
    if changed:
        raise ValueError(f"immutable v12 inputs changed: {changed}")
    return {
        "source_files": len(IMMUTABLE_SOURCE_HASHES),
        "source_hashes": IMMUTABLE_SOURCE_HASHES,
        "evidence_index_sha256": actual_index,
        "archive_sha256_trusted_binding": ORIGINAL_ARCHIVE_SHA256,
    }


def register(repo: Path, output: Path, source_paths: list[Path]) -> dict:
    if output.exists():
        raise FileExistsError(f"exclusive correction output already exists: {output}")
    output.mkdir(parents=True)
    original_root = repo / "var/behavior-v12/mechanical-01"
    immutable = _verify_original_immutability(repo)
    original_registration = json.loads((original_root / "registration.json").read_text())
    source_seal = {str(path.relative_to(repo)): file_sha(path) for path in source_paths}
    registration = {
        "schema": "behavior-v12-correction-registration/v1",
        "purpose": "separately versioned phase-correct retained-data analysis; never retroactive v12 admission",
        "original_experiment": str(original_root),
        "original_registration_sha256": file_sha(original_root / "registration.json"),
        "original_sources_sha256": original_registration["sources_sha256"],
        "original_model_sha256": original_registration["model_sha256"],
        "original_evidence_index_sha256": ORIGINAL_INDEX_SHA256,
        "original_archive_sha256": ORIGINAL_ARCHIVE_SHA256,
        "computation_source_seal": source_seal,
        "clock": {
            "dt_s": DT,
            "rows": ROWS,
            "tick_zero": "initialization only; no force/slip quadrature",
            "interval_k": "((k-1)*dt,k*dt] for k>=1",
            "state_start": "core row k-1 qpos/qvel",
            "state_end": "core row k qpos/qvel",
            "raw_cache_owner": "row k contact/frame/wrench and dense cache use state_start qpos",
            "endpoint_owner": "core row k is authoritative physical endpoint pose",
            "next_cache_check": "endpoint k must match dense cache row k+1 where k<40000",
            "final_endpoint": "core row 40000 reconstructed without a nonexistent next cache row",
        },
        "schemas": {
            "core": CORE,
            "dense": DENSE,
            "contact": CONTACT,
            "derived_npz": [
                "ticks:int64[40001]",
                "endpoint_source_core_row:int64[40001]",
                "endpoint_thorax_ap:float64[40001,6]",
                "endpoint_whole_foot_min_height:float64[40001,6]",
                "interval_contact_row_tick:int64[40001]",
                "interval_state_start_core_row:int64[40001] (-1 only at tick0)",
                "interval_state_end_core_row:int64[40001]",
                "interval_summed_positive_normal:float64[40001,6]",
                "interval_force_weighted_pre_tangent:float64[40001,6]",
                "interval_peak_pre_tangent_speed:float64[40001,6]",
            ],
        },
        "numeric_contract": {
            "dtype": "float64 for all reconstruction arithmetic",
            "mesh_order": "cast frozen mesh vertices to float64 before mean/min/transform",
            "strict_max_abs_tolerance": TOLERANCE,
            "on_violation": "preserve failure and stop; no tolerance relaxation",
            "model_arrays": "every frozen compiled array must equal the MJB-loaded array exactly",
        },
        "outcome_contract": {
            "analysis_ticks_inclusive": list(ANALYSIS_TICKS),
            "median": "centered 31 samples; no padding; earliest exact ties",
            "ap_excursion_mm_strict_gt": 0.02,
            "clearance_mm_strict_gt": 0.02,
            "recovery_intervals_min": 30,
            "support_intervals_min": 30,
            "slip_mm_strict_lt": 0.15,
            "slip": "dt*sum over every owned loaded stance interval of sum(Fn*|v_tangent_pre|)/sum(Fn)",
            "phase_invalidity": "any nonincreasing interior episode fails closed; window-boundary partials remain distinct",
            "unchanged_bounds": original_registration["measurement"]["unchanged_bounds"],
            "waveform": "unchanged original 3001:25001 command grid",
        },
        "execution_limits": {
            "workers": 1,
            "wall_seconds": 7200,
            "peak_rss_bytes": 8 * 1024**3,
            "new_bytes": 2 * 1024**3,
            "tiny_fixture_physical_seconds_max": 1.0,
            "long_physics_seconds": 0,
            "network": False,
        },
        "scope_stop": "newanalysis only; no held-out, repeat, neural15, phenotype, ablation, Lab/API/replay, candidate, tuning, or product admission",
        "immutability": immutable,
    }
    _write_exclusive_json(output / "registration.json", registration)
    _write_exclusive_json(output / "preregistration.json", {
        "schema": "behavior-v12-correction-preregistration/v1",
        "registered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registration_sha256": file_sha(output / "registration.json"),
        "computation_source_seal_sha256": _json_sha(source_seal),
        "outcomes_observed_by_registered_analyzer": False,
    })
    return registration


def validate_registration(repo: Path, output: Path) -> tuple[dict, Path, dict]:
    registration = json.loads((output / "registration.json").read_text())
    preregistration = json.loads((output / "preregistration.json").read_text())
    if preregistration["registration_sha256"] != file_sha(output / "registration.json"):
        raise ValueError("correction registration seal mismatch")
    for relative, expected in registration["computation_source_seal"].items():
        if file_sha(repo / relative) != expected:
            raise ValueError(f"sealed correction source changed: {relative}")
    _verify_original_immutability(repo)
    original_root = Path(registration["original_experiment"])
    original_registration = json.loads((original_root / "registration.json").read_text())
    if (file_sha(original_root / "registration.json") != registration["original_registration_sha256"]
            or original_registration["sources_sha256"] != registration["original_sources_sha256"]
            or file_sha(original_root / "model.mjb") != registration["original_model_sha256"]):
        raise ValueError("original experiment binding changed")
    return registration, original_root, original_registration


def verify_evidence_index(repo: Path, output: Path) -> dict:
    started = time.monotonic()
    index_path = repo / "var/behavior-v12/evidence-index.json"
    if file_sha(index_path) != ORIGINAL_INDEX_SHA256:
        raise ValueError("original evidence index changed")
    index = json.loads(index_path.read_text())
    failures = []
    bytes_checked = 0
    for relative, record in index["files"].items():
        path = repo / relative
        if not path.is_file():
            failures.append({"path": relative, "error": "missing"})
            continue
        size = path.stat().st_size
        actual = file_sha(path)
        bytes_checked += size
        if size != record["bytes"] or actual != record["sha256"]:
            failures.append({"path": relative, "bytes": size, "sha256": actual})
    result = {
        "schema": "behavior-v12-correction-raw-closure/v1",
        "evidence_index_sha256": ORIGINAL_INDEX_SHA256,
        "indexed_files_expected": index["file_count"],
        "indexed_files_checked": len(index["files"]),
        "indexed_bytes_expected": index["total_bytes"],
        "indexed_bytes_checked": bytes_checked,
        "failures": failures,
        "passed": not failures and len(index["files"]) == index["file_count"] and bytes_checked == index["total_bytes"],
        "wall_seconds": time.monotonic() - started,
    }
    _write_exclusive_json(output / "raw-closure.json", result)
    if not result["passed"]:
        raise ValueError("original evidence index closure failed")
    return result


def run_native_fixture(repo: Path, output: Path) -> dict:
    """Run two 0.1 ms detached integrations as a phase/noninterference fixture."""
    registration, original_root, original_registration = validate_registration(repo, output)
    model = mj.MjModel.from_binary_path(str(original_root / "model.mjb"))
    trial = original_root / "development/source-native-excursion-v12--42--straight-02"
    _, core, _ = _read_dense(trial / "core", _width(CORE))
    cs = _slices(CORE)
    # A retained moving state supplies a realistic loaded native configuration;
    # no candidate trial is rerun.
    source_tick = 100
    baseline = mj.MjData(model)
    baseline.qpos[:] = core[source_tick, cs["qpos"]]
    baseline.qvel[:] = core[source_tick, cs["qvel"]]
    baseline.ctrl[:] = core[source_tick, cs["ctrl"]]
    mj.mj_forward(model, baseline)
    captured_data = mj.MjData(model)
    plain_data = mj.MjData(model)
    mj.mj_copyData(captured_data, model, baseline)
    mj.mj_copyData(plain_data, model, baseline)
    paired = capture_native_step(model, captured_data)
    mj.mj_step(model, plain_data)
    trajectory_equal = np.array_equal(
        _integration_state(model, captured_data), _integration_state(model, plain_data)
    )
    cache_equal = (
        np.array_equal(captured_data.geom_xpos, plain_data.geom_xpos)
        and np.array_equal(captured_data.geom_xmat, plain_data.geom_xmat)
        and captured_data.ncon == plain_data.ncon
    )
    detached = mj.MjData(model)
    _prepare_detached_state(model, detached, paired.state_start_qpos, paired.state_start_qvel)
    start_geom_error = float(np.max(np.abs(detached.geom_xpos - paired.cache_geom_xpos)))
    _prepare_detached_state(model, detached, paired.state_end_qpos, paired.state_end_qvel)
    wrong_end_geom_error = float(np.max(np.abs(detached.geom_xpos - paired.cache_geom_xpos)))
    if not len(paired.contact_rows):
        raise ValueError("native fixture has no loaded contacts")
    rows = paired.contact_rows
    g1 = rows[:, 1].astype(np.int64)
    g2 = rows[:, 2].astype(np.int64)
    points = rows[:, 4:7]
    body1 = model.geom_bodyid[g1].astype(np.int64)
    body2 = model.geom_bodyid[g2].astype(np.int64)
    _prepare_detached_state(model, detached, paired.state_start_qpos, paired.state_start_qvel)
    pre_object = _body_point_velocities(model, detached, points, body1, body2)
    pre_jac = _point_jacobian_velocities(model, detached, points, body1, body2)
    _prepare_detached_state(model, detached, paired.state_start_qpos, paired.state_end_qvel)
    hybrid = _point_jacobian_velocities(model, detached, points, body1, body2)
    _prepare_detached_state(model, detached, paired.state_end_qpos, paired.state_end_qvel)
    wrong_same = _point_jacobian_velocities(model, detached, points, body1, body2)
    saved_hybrid = rows[:, -3:]
    pre_jac_error = float(np.max(np.abs(pre_object - pre_jac)))
    hybrid_error = float(np.max(np.abs(hybrid - saved_hybrid)))
    pre_hybrid_difference = float(np.max(np.abs(pre_object - saved_hybrid)))
    wrong_same_difference = float(np.max(np.abs(wrong_same - saved_hybrid)))
    result = {
        "schema": "behavior-v12-paired-native-fixture/v1",
        "source": "frozen candidate seed42 straight-02 core row 100 loaded into detached MjData",
        "source_tick": source_tick,
        "integrations": 2,
        "dt_s": float(model.opt.timestep),
        "physical_seconds": 2 * float(model.opt.timestep),
        "controller_only_steps": 0,
        "contact_rows": int(len(rows)),
        "positive_normal_force_rows": int(np.count_nonzero(rows[:, 16] > 0)),
        "trajectory_integration_state_bitwise_equal": bool(trajectory_equal),
        "post_step_cache_bitwise_equal": bool(cache_equal),
        "cache_vs_state_start_geometry_max_abs_mm": start_geom_error,
        "wrong_state_end_geometry_max_abs_mm": wrong_end_geom_error,
        "pre_object_vs_pre_jacobian_max_abs_mm_s": pre_jac_error,
        "captured_hybrid_vs_start_qpos_end_qvel_max_abs_mm_s": hybrid_error,
        "pre_velocity_vs_captured_hybrid_max_abs_mm_s": pre_hybrid_difference,
        "wrong_same_row_vs_captured_hybrid_max_abs_mm_s": wrong_same_difference,
        "tolerance": TOLERANCE,
        "capture_called_forward": False,
        "passed": bool(
            trajectory_equal and cache_equal and start_geom_error <= TOLERANCE
            and pre_jac_error <= TOLERANCE and hybrid_error <= TOLERANCE
            and wrong_end_geom_error > TOLERANCE and pre_hybrid_difference > TOLERANCE
            and wrong_same_difference > TOLERANCE and np.any(rows[:, 16] > 0)
        ),
        "registration_sha256": file_sha(output / "registration.json"),
    }
    _write_exclusive_json(output / "paired-native-fixture.json", result)
    if not result["passed"]:
        raise ValueError("paired native fixture failed")
    return result


def verify_restoration_join(original_root: Path, original_registration: dict) -> dict:
    dest = original_root / "restoration"
    result = json.loads((dest / "result.json").read_text())
    checkpoint = json.loads((dest / "checkpoint.json").read_text())
    binding = checkpoint["binding"]
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
    if binding != expected_binding or result["registration_sha256"] != expected_binding["registration_sha256"]:
        raise ValueError("restoration binding mismatch")
    trial = original_root / binding["trial"]
    _, raw_core, _ = _read_dense(trial / "core", _width(CORE))
    _, raw_dense, _ = _read_dense(trial / "dense", _width(DENSE))
    terminal = json.loads((trial / "contacts/terminal.json").read_text())
    contact_ticks, raw_contacts, _ = _read_stream(
        trial / "contacts", int(terminal["initialized_rows"]), _width(CONTACT)
    )
    with np.load(dest / "expected.npz", allow_pickle=False) as expected, np.load(
        dest / "actual.npz", allow_pickle=False
    ) as actual:
        if set(expected.files) != set(actual.files) or not all(
            np.array_equal(expected[name], actual[name]) for name in expected.files
        ):
            raise ValueError("expected/actual restoration streams differ")
        ticks = np.arange(10001, 10101, dtype=np.int64)
        core_join = np.array_equal(expected["core"], raw_core[ticks])
        dense_join = np.array_equal(expected["dense"], raw_dense[ticks])
        contact_join = True
        offsets = expected["contact_offsets"]
        for index, tick in enumerate(ticks):
            retained = raw_contacts[contact_ticks == tick]
            replayed = expected["contacts"][offsets[index]:offsets[index + 1]]
            contact_join &= np.array_equal(retained, replayed)
        shapes = {name: list(expected[name].shape) for name in expected.files}
        dtypes = {name: expected[name].dtype.str for name in expected.files}
    digest_equal = json.loads((dest / "expected-digests.json").read_text()) == json.loads(
        (dest / "actual-digests.json").read_text()
    )
    passed = bool(result["passed"] and result["corrupted_destination_before_restore"]
                  and core_join and dense_join and contact_join and digest_equal)
    if not passed:
        raise ValueError("restoration-to-retained-raw join failed")
    return {
        "passed": passed,
        "binding": binding,
        "ticks": [10001, 10100],
        "raw_core_join": bool(core_join),
        "raw_dense_join": bool(dense_join),
        "raw_contact_join": bool(contact_join),
        "cache_controller_digest_join": bool(digest_equal),
        "shapes": shapes,
        "dtypes": dtypes,
        "wrong_identity_policy": "exact dict equality; reject before any read-side comparison; verifier never mutates live state",
    }


def analyze(repo: Path, output: Path) -> dict:
    started = time.monotonic()
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    registration, original_root, original_registration = validate_registration(repo, output)
    if not (output / "raw-closure.json").exists() or not json.loads((output / "raw-closure.json").read_text())["passed"]:
        raise ValueError("whole original evidence closure must pass before analysis")
    if not (output / "paired-native-fixture.json").exists() or not json.loads((output / "paired-native-fixture.json").read_text())["passed"]:
        raise ValueError("paired native fixture must pass before analysis")
    if (output / "analysis.json").exists() or (output / "derived").exists():
        raise FileExistsError("analysis output already exists")
    derived_dir = output / "derived"
    derived_dir.mkdir()
    model = mj.MjModel.from_binary_path(str(original_root / "model.mjb"))
    model_array_check = _validate_model_arrays(original_root, model, original_registration)
    model_meta = _foot_metadata(model, original_registration)
    expected = _expected_trials(original_registration)
    actual_names = {path.name for path in (original_root / "development").iterdir() if path.is_dir()}
    if actual_names != set(expected):
        raise ValueError("incomplete or extra retained development panel")
    trials = {}
    failures = {}
    for name in sorted(expected):
        try:
            trial_result = _analyze_trial(
                original_root,
                original_root / "development" / name,
                expected[name],
                original_registration,
                model,
                model_meta,
                derived_dir,
            )
            trials[name] = trial_result
            _write_exclusive_json(derived_dir / f"{name}.json", trial_result)
        except BaseException as exc:
            failures[name] = _failure(exc)
            _write_exclusive_json(derived_dir / f"{name}.failure.json", failures[name])
            # A phase/arithmetic/identity failure invalidates outcome derivation.
            break
    if failures:
        terminal = {
            "schema": "behavior-v12-correction-analysis/v1",
            "status": "failed",
            "scientific_admission": False,
            "failures": failures,
            "completed_trials": len(trials),
            "registration_sha256": file_sha(output / "registration.json"),
        }
        _write_exclusive_json(output / "analysis.json", terminal)
        raise ValueError("correction analysis failed closed")

    aggregate = {}
    candidate = "source-native-excursion-v12"
    for seed in original_registration["development_seeds"]:
        speeds = [trials[f"{candidate}--{seed}--{case}"]["forward_mean_mm_s"]
                  for case in ("straight-008", "straight-02", "straight-04")]
        aggregate[f"speed-{seed}"] = bool(
            speeds[0] > 0.2 and all(right - left > 0.2 for left, right in zip(speeds, speeds[1:]))
        )
    restoration = verify_restoration_join(original_root, original_registration)
    aggregate["active_restoration_raw_join"] = restoration["passed"]
    candidate_trials = [value for value in trials.values() if value["conditions"]["profile"] == candidate]
    operational_passed = bool(
        all(aggregate.values()) and all(all(trial["gates"].values()) for trial in candidate_trials)
    )
    paired_maxima = {
        key: max(trial["paired_state_verification"][key] for trial in trials.values())
        for key in (
            "cache_vs_state_start_max_abs_mm",
            "endpoint_vs_next_cache_max_abs_mm",
            "wrong_same_row_geometry_max_abs_mm",
            "saved_hybrid_velocity_max_abs_mm_s",
            "pre_object_velocity_vs_jacobian_max_abs_mm_s",
            "wrong_same_row_velocity_max_abs_mm_s",
        )
    }
    result = {
        "schema": "behavior-v12-correction-analysis/v1",
        "status": "complete",
        "scope": "separately versioned retained-data analysis only",
        "scientific_admission": False,
        "retroactive_v12_regrade": False,
        "candidate_operational_gates_passed": operational_passed,
        "downstream_allowed": False,
        "registration_sha256": file_sha(output / "registration.json"),
        "raw_closure_sha256": file_sha(output / "raw-closure.json"),
        "fixture_sha256": file_sha(output / "paired-native-fixture.json"),
        "model_array_check": model_array_check,
        "aggregate_gates": aggregate,
        "restoration_raw_join": restoration,
        "paired_state_maxima": paired_maxima,
        "trials": trials,
        "retained_trial_count": len(trials),
        "raw_contact_rows": int(sum(t["raw_contact_rows"] for t in trials.values())),
        "invalid_interior_phase_episodes": int(sum(t["invalid_interior_phase_episodes"] for t in trials.values())),
        "limits": registration["execution_limits"],
        "remaining_goal_gap": "Actual qualified walking and same-condition WT/official/user neural phenotype and product acceptance remain unresolved.",
    }
    _write_exclusive_json(output / "analysis.json", result)
    elapsed = time.monotonic() - started
    usage = resource.getrusage(resource.RUSAGE_SELF)
    new_bytes = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    resources = {
        "schema": "behavior-v12-correction-resources/v1",
        "analysis_wall_seconds": elapsed,
        "analysis_user_cpu_seconds": usage.ru_utime - usage_start.ru_utime,
        "analysis_system_cpu_seconds": usage.ru_stime - usage_start.ru_stime,
        "peak_rss_bytes": _peak_rss_bytes(),
        "new_output_bytes_at_analysis": new_bytes,
        "workers": 1,
        "long_physics_seconds": 0,
        "full_network_seconds": 0,
        "fixture_physical_seconds_in_registered_receipt": json.loads(
            (output / "paired-native-fixture.json").read_text()
        )["physical_seconds"],
        "controller_only_steps": 0,
        "network": False,
        "within_registered_limits": bool(
            elapsed <= 7200 and _peak_rss_bytes() <= 8 * 1024**3 and new_bytes <= 2 * 1024**3
        ),
    }
    _write_exclusive_json(output / "resource-receipt.json", resources)
    if not resources["within_registered_limits"]:
        raise RuntimeError("correction resource limit exceeded")
    return result


def record_tests(
    output: Path,
    junit: Path,
    test_runs: int,
    test_physics_per_run: float,
    other_tiny_physics_seconds: float,
) -> dict:
    if test_runs < 1 or test_physics_per_run < 0 or other_tiny_physics_seconds < 0:
        raise ValueError("invalid test execution accounting")
    fixture = json.loads((output / "paired-native-fixture.json").read_text())
    tree = ET.parse(junit)
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    # A pytest testsuites root includes one child suite; count only leaves.
    leaves = [suite for suite in suites if not list(suite.findall("testsuite"))]
    tests = sum(int(suite.attrib.get("tests", 0)) for suite in leaves)
    failures = sum(int(suite.attrib.get("failures", 0)) for suite in leaves)
    errors = sum(int(suite.attrib.get("errors", 0)) for suite in leaves)
    skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in leaves)
    destination = output / "correction-tests.junit.xml"
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copyfile(junit, destination)
    result = {
        "schema": "behavior-v12-correction-tests/v1",
        "passed": tests - failures - errors - skipped,
        "failed": failures + errors,
        "skipped": skipped,
        "collected": tests,
        "test_runs": test_runs,
        "junit_sha256": file_sha(destination),
        "junit": str(destination),
        "tiny_physics": {
            "test_integrations_per_run": 2,
            "test_physics_seconds_per_run": test_physics_per_run,
            "test_physics_seconds_all_runs": test_runs * test_physics_per_run,
            "registered_fixture_physics_seconds": fixture["physical_seconds"],
            "preflight_or_other_tiny_physics_seconds": other_tiny_physics_seconds,
        },
        "total_tiny_physics_seconds": (
            test_runs * test_physics_per_run + fixture["physical_seconds"] + other_tiny_physics_seconds
        ),
        "long_physics_seconds": 0,
        "full_network_seconds": 0,
    }
    if result["failed"] or result["passed"] == 0:
        raise ValueError("correction tests did not pass")
    _write_exclusive_json(output / "test-receipt.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("register", "raw-closure", "fixture", "record-tests", "analyze"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--test-runs", type=int, default=1)
    parser.add_argument("--test-physics-per-run", type=float, default=0.002)
    parser.add_argument("--other-tiny-physics-seconds", type=float, default=0.0)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = args.output.resolve()
    if args.command == "register":
        result = register(repo, output, [path.resolve() for path in args.source])
    elif args.command == "raw-closure":
        validate_registration(repo, output)
        result = verify_evidence_index(repo, output)
    elif args.command == "fixture":
        result = run_native_fixture(repo, output)
    elif args.command == "record-tests":
        if args.junit is None:
            parser.error("--junit is required for record-tests")
        validate_registration(repo, output)
        result = record_tests(
            output, args.junit.resolve(), args.test_runs, args.test_physics_per_run,
            args.other_tiny_physics_seconds,
        )
    else:
        result = analyze(repo, output)
    print(json.dumps({
        "command": args.command,
        "status": result.get("status", "passed"),
        "passed": result.get("passed", True),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
