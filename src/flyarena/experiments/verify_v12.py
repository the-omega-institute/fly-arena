"""Independent reconstruction of v12 metrics from immutable saved raw streams."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from ..common import file_sha, write_json
from .cadence_v12 import PROFILE
from .mechanical_v12 import CONTACT, CORE, DENSE, DT, _slices, _width


def read_stream(path, rows, width):
    terminal = json.loads((path / "terminal.json").read_text())
    if not terminal["complete"] or terminal["primary_failure"] is not None or terminal["retention_failures"]:
        raise ValueError(f"incomplete scientific stream: {path}")
    if terminal["initialized_rows"] != rows:
        raise ValueError("wrong scientific horizon")
    chunks = sorted(path.glob("chunk-*.npz"))
    expected = {p.name for p in chunks}
    if expected != {name for name in terminal["files"] if name.startswith("chunk-")}:
        raise ValueError("chunk manifest mismatch")
    ticks, values = [], []
    for index, chunk in enumerate(chunks):
        if chunk.name != f"chunk-{index:05d}.npz" or file_sha(chunk) != terminal["files"][chunk.name]:
            raise ValueError("chunk order/hash mismatch")
        with np.load(chunk, allow_pickle=False) as archive:
            if set(archive.files) != {"ticks", "values"}:
                raise ValueError("invalid archive fields")
            tick, value = archive["ticks"], archive["values"]
            if tick.dtype != np.int64 or value.dtype != np.float64 or value.shape != (len(tick), width):
                raise ValueError("invalid archive dtype/shape")
            if not np.isfinite(value).all():
                raise ValueError("nonfinite raw evidence")
            ticks.append(tick)
            values.append(value)
    return np.concatenate(ticks), np.concatenate(values)


def read_dense(path, rows, width):
    ticks, values = read_stream(path, rows, width)
    if not np.array_equal(ticks, np.arange(rows, dtype=np.int64)):
        raise ValueError("missing/duplicate dense ticks")
    return ticks, values


def complete_runs(state, phase, lo, hi):
    """Return complete half-open runs and explicitly count boundary/invalid partials."""
    window = state[lo:hi + 1].astype(bool)
    switches = np.flatnonzero(window[1:] != window[:-1]) + lo + 1
    complete = []
    invalid = 0
    for start, end in zip(switches[:-1], switches[1:]):
        if state[start] and phase[end - 1] > phase[start]:
            complete.append((int(start), int(end)))
        elif state[start]:
            invalid += 1
    partial = int(bool(window[0])) + int(bool(window[-1])) + invalid
    return complete, partial


def _longest_true(values):
    padded = np.r_[False, np.asarray(values, dtype=bool), False]
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return int(np.max(changes[1::2] - changes[::2], initial=0))


def _median31(values):
    if len(values) < 31:
        return np.empty(0)
    return np.median(np.lib.stride_tricks.sliding_window_view(values, 31), axis=1)


def _event_groups(ticks, values):
    groups = {}
    for index, tick in enumerate(ticks):
        groups.setdefault(int(tick), []).append(values[index])
    return groups


def _verify_geometry_and_velocities(model, core, dense, contact_ticks, contacts, foot_ids, thorax):
    cs, ds, es = _slices(CORE), _slices(DENSE), _slices(CONTACT)
    data = mj.MjData(model)
    foot_centers = []
    for geom in foot_ids:
        mesh = int(model.geom_dataid[geom])
        begin, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
        foot_centers.append(np.asarray(model.mesh_vert[begin:begin + count]).mean(axis=0))
    events = _event_groups(contact_ticks, contacts)
    max_geometry_error = 0.0
    max_velocity_error = 0.0
    checked_velocities = 0
    for tick in range(len(core)):
        data.qpos[:] = core[tick, cs["qpos"]]
        data.qvel[:] = core[tick, cs["qvel"]]
        mj.mj_kinematics(model, data)
        mj.mj_comPos(model, data)
        heights = np.full(6, np.inf)
        centers = np.empty((6, 3))
        for index, geom in enumerate(foot_ids):
            mesh = int(model.geom_dataid[geom])
            begin, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
            vertices = np.asarray(model.mesh_vert[begin:begin + count])
            rotation = data.geom_xmat[geom].reshape(3, 3)
            heights[index // 5] = min(heights[index // 5],
                float((vertices @ rotation[2]).min() + data.geom_xpos[geom, 2]))
            if index % 5 == 4:
                centers[index // 5] = rotation @ foot_centers[index] + data.geom_xpos[geom]
        rotation = data.xmat[thorax].reshape(3, 3)
        ap = (centers - data.xpos[thorax]) @ rotation[:, 0]
        saved_heights = dense[tick, ds["whole_foot_min_height"]]
        saved_centers = dense[tick, ds["tarsus5_centroid"]].reshape(6, 3)
        saved_ap = dense[tick, ds["thorax_ap"]]
        max_geometry_error = max(max_geometry_error,
            float(np.max(np.abs(np.r_[heights - saved_heights, (centers - saved_centers).ravel(), ap - saved_ap]))))
        # Every 100th tick with contacts is checked independently with point Jacobians.
        if tick % 100 or tick not in events:
            continue
        for event in events[tick]:
            foot_geom = int(event[es["foot_geom"]][0])
            ground_geom = int(event[es["ground_geom"]][0])
            point = event[es["position"]]
            jac_foot = np.zeros((3, model.nv))
            jac_ground = np.zeros((3, model.nv))
            mj.mj_jac(model, data, jac_foot, None, point, int(model.geom_bodyid[foot_geom]))
            mj.mj_jac(model, data, jac_ground, None, point, int(model.geom_bodyid[ground_geom]))
            independent = (jac_foot - jac_ground) @ data.qvel
            saved = event[es["relative_velocity_world"]]
            max_velocity_error = max(max_velocity_error, float(np.max(np.abs(independent - saved))))
            checked_velocities += 1
    if max_geometry_error > 5e-12 or max_velocity_error > 5e-10 or checked_velocities == 0:
        raise ValueError("saved native geometry/contact velocity mismatch")
    return {"max_geometry_error": max_geometry_error, "max_contact_velocity_error": max_velocity_error,
            "contact_velocities_checked": checked_velocities}


def reconstruct_trial(root, trial, reg):
    cs, ds, es = _slices(CORE), _slices(DENSE), _slices(CONTACT)
    ticks, core = read_dense(trial / "core", 40001, _width(CORE))
    dense_ticks, dense = read_dense(trial / "dense", 40001, _width(DENSE))
    contact_terminal = json.loads((trial / "contacts" / "terminal.json").read_text())
    contact_ticks, contacts = read_stream(trial / "contacts", contact_terminal["initialized_rows"], _width(CONTACT))
    if len(contact_ticks) and (np.any(np.diff(contact_ticks) < 0) or contact_ticks[0] < 0 or contact_ticks[-1] > 40000):
        raise ValueError("invalid contact event ticks")
    meta = json.loads((trial / "core" / "start.json").read_text())
    if meta != json.loads((trial / "dense" / "start.json").read_text()) or meta != json.loads((trial / "contacts" / "start.json").read_text()):
        raise ValueError("stream identities differ")
    if meta["registration_sha256"] != file_sha(root / "registration.json") or meta["sources_sha256"] != reg["sources_sha256"]:
        raise ValueError("wrong immutable stage identity")
    name, common, asymmetry = meta["case"]
    expected = np.zeros((40001, 2))
    expected[3001:25001] = [common * (1 - asymmetry), common * (1 + asymmetry)]
    if not np.array_equal(core[:, cs["input"]], expected):
        raise ValueError("wrong waveform")
    model = mj.MjModel.from_binary_path(str(root / "model.mjb"))
    foot = np.array(reg["measurement"]["foot_geom_ids"] if "foot_geom_ids" in reg["measurement"] else [
        mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, f"fly-0/{leg}_tarsus{i}")
        for leg in ("lf", "lm", "lh", "rf", "rm", "rh") for i in range(1, 6)
    ], dtype=int)
    thorax = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, "fly-0/c_thorax")
    native_check = _verify_geometry_and_velocities(model, core, dense, contact_ticks, contacts, foot, thorax)
    # Reconstruct dense force summaries directly from the retained per-contact native rows.
    rebuilt = np.zeros((40001, 6, 5))
    for tick, event in zip(contact_ticks, contacts):
        geom = int(event[es["foot_geom"]][0])
        matches = np.flatnonzero(foot == geom)
        if len(matches) != 1 or int(event[es["ground_geom"]][0]) < 0:
            raise ValueError("invalid saved contact identity")
        leg = int(matches[0] // 5)
        wrench = event[es["wrench_contact_frame"]]
        frame = event[es["frame"]].reshape(3, 3)
        relative = event[es["relative_velocity_world"]]
        tangent = relative - frame[0] * np.dot(relative, frame[0])
        speed = float(np.linalg.norm(tangent))
        rebuilt[int(tick), leg, 2] = max(rebuilt[int(tick), leg, 2], speed)
        rebuilt[int(tick), leg, 3] += 1
        if wrench[0] > 0:
            rebuilt[int(tick), leg, 0] += wrench[0]
            rebuilt[int(tick), leg, 1] += wrench[0] * speed
            rebuilt[int(tick), leg, 4] += 1
    saved_summary = np.stack([
        dense[:, ds["summed_positive_normal"]],
        dense[:, ds["force_weighted_tangent_numerator"]],
        dense[:, ds["peak_tangent_speed"]], dense[:, ds["contact_count"]],
        dense[:, ds["positive_force_count"]],
    ], axis=2)
    if not np.array_equal(rebuilt, saved_summary):
        raise ValueError("raw contact rows do not reproduce dense support/slip values")
    pos = core[:, cs["thorax_position"]]
    rot = core[:, cs["thorax_rotation"]].reshape(-1, 3, 3)
    phases = core[:, cs["phases"]]
    yaw = np.unwrap(np.arctan2(rot[:, 1, 0], rot[:, 0, 0]))
    velocity = np.diff(pos, axis=0) / DT
    forward = (velocity[6000:25000] * rot[6000:25000, :, 0]).sum(axis=1)
    stop_speed = float(np.linalg.norm(velocity[30000:40000], axis=1).mean())
    stop_displacement = float(np.linalg.norm(pos[40000] - pos[30000]))
    min_upright = float(rot[:, 2, 2].min())
    net_yaw = float(yaw[25000] - yaw[3000])
    yaw_rate = float((yaw[25000] - yaw[6000]) / 1.9)
    heights = dense[:, ds["whole_foot_min_height"]]
    ap_raw = dense[:, ds["thorax_ap"]]
    normal = dense[:, ds["summed_positive_normal"]]
    weighted = dense[:, ds["force_weighted_tangent_numerator"]]
    swings, stances = [], []
    all_swings = True
    all_stances = True
    periods = reg["controller"]["swing_periods_strict_modulo"]
    for leg, leg_name in enumerate(("lf", "lm", "lh", "rf", "rm", "rh")):
        start_phase, end_phase = periods[leg_name]
        mod = np.mod(phases[:, leg], 2 * np.pi)
        commanded_swing = (mod > start_phase) & (mod < end_phase)
        swing_runs, swing_partials = complete_runs(commanded_swing, phases[:, leg], 6000, 25000)
        stance_runs, stance_partials = complete_runs(~commanded_swing, phases[:, leg], 6000, 25000)
        leg_swings = []
        for begin, end in swing_runs:
            raw = ap_raw[begin:end, leg]
            filtered = _median31(raw)
            record = {"start_tick": begin, "end_tick_exclusive": end,
                      "partial_count_for_leg": swing_partials, "filtered_ticks": [begin + 15, end - 16]}
            valid = True
            if not len(filtered):
                record.update(status="inconclusive", reason="no full 31-sample median window")
                valid = False
            else:
                minimum, maximum = float(filtered.min()), float(filtered.max())
                pep_local = int(np.flatnonzero(filtered == minimum)[0])
                later_global = np.flatnonzero((filtered == maximum) & (np.arange(len(filtered)) > pep_local))
                diffs = np.diff(filtered)
                signs = np.sign(diffs[diffs != 0])
                reversals = int(np.count_nonzero(signs[1:] != signs[:-1])) if len(signs) > 1 else 0
                record.update(filtered_min_mm=minimum, filtered_max_mm=maximum,
                    min_ties=int(np.count_nonzero(filtered == minimum)),
                    max_ties=int(np.count_nonzero(filtered == maximum)),
                    flat_differences=int(np.count_nonzero(diffs == 0)), reversals=reversals)
                if not len(later_global):
                    record.update(status="inconclusive", reason="global maximum not later than earliest global minimum")
                    valid = False
                else:
                    aep_local = int(later_global[0])
                    pep = begin + 15 + pep_local
                    aep = begin + 15 + aep_local
                    excursion = float(maximum - minimum)
                    recovery_mask = (heights[pep:aep + 1, leg] > 0.02) & (normal[pep:aep + 1, leg] == 0)
                    dwell = _longest_true(recovery_mask)
                    passed = bool(aep > pep and excursion > 0.02 and dwell >= 30)
                    record.update(status="pass" if passed else "fail", pep_tick=pep, aep_tick=aep,
                        duration_s=(aep - pep) * DT, excursion_mm=excursion,
                        recovery_dwell_ticks=dwell, recovery_dwell_s=dwell * DT,
                        peak_whole_foot_height_mm=float(heights[pep:aep + 1, leg].max()))
                    valid = passed
            all_swings &= valid
            leg_swings.append(record)
        if not leg_swings:
            all_swings = False
        leg_stances = []
        for begin, end in stance_runs:
            loaded = normal[begin:end, leg] > 0
            support_dwell = _longest_true(loaded)
            ratios = np.divide(weighted[begin:end, leg], normal[begin:end, leg],
                               out=np.zeros(end - begin), where=loaded)
            slip = float(DT * ratios.sum())
            passed = bool(support_dwell >= 30 and slip < 0.15)
            leg_stances.append({"start_tick": begin, "end_tick_exclusive": end,
                "partial_count_for_leg": stance_partials, "status": "pass" if passed else "fail",
                "support_dwell_ticks": support_dwell, "support_dwell_s": support_dwell * DT,
                "slip_mm": slip, "loaded_samples": int(loaded.sum()),
                "force_impulse_native_s": float(DT * normal[begin:end, leg].sum()),
                "peak_contact_tangent_speed_mm_s": float(dense[begin:end, ds["peak_tangent_speed"]][:, leg].max(initial=0))})
            all_stances &= passed
        if not leg_stances:
            all_stances = False
        swings.append(leg_swings)
        stances.append(leg_stances)
    gate = {"finite": True, "upright": min_upright > 0.8,
            "stop": stop_displacement < 0.25 and stop_speed < 0.1}
    if common > 0:
        gate["recovery"] = bool(all_swings)
        gate["support_slip"] = bool(all_stances)
        if asymmetry:
            gate["turn"] = bool(np.sign(net_yaw) == np.sign(asymmetry) and abs(net_yaw) > 0.1)
        else:
            gate["straight_yaw"] = abs(yaw_rate) < 0.15
    controls = core[:, cs["ctrl"]]
    force = core[:, cs["actuator_force"]]
    position = np.flatnonzero(model.actuator_trntype == int(mj.mjtTrn.mjTRN_JOINT))
    saturation = np.abs(force[:, position]) >= model.actuator_forcerange[position, 1] - 1e-9
    return {
        "conditions": meta, "gates": gate, "forward_mean_mm_s": float(forward.mean()),
        "mean_yaw_rate_rad_s": yaw_rate, "net_active_yaw_rad": net_yaw,
        "min_upright_z": min_upright, "stop_displacement_mm": stop_displacement,
        "stop_mean_speed_mm_s": stop_speed, "swing_cycles": swings, "stance_cycles": stances,
        "raw_contact_rows": int(len(contacts)), "native_reconstruction": native_check,
        "position_force_saturation_fraction": float(saturation.mean()),
        "max_native_position_force": float(np.abs(force[:, position]).max()),
        "core_terminal_sha256": file_sha(trial / "core" / "terminal.json"),
        "dense_terminal_sha256": file_sha(trial / "dense" / "terminal.json"),
        "contacts_terminal_sha256": file_sha(trial / "contacts" / "terminal.json"),
    }


def _verify_restoration(root, reg):
    dest = root / "restoration"
    result = json.loads((dest / "result.json").read_text())
    checkpoint = json.loads((dest / "checkpoint.json").read_text())
    expected_binding = {
        "profile": PROFILE, "trial": "development/source-native-excursion-v12--42--straight-02",
        "seed": 42, "case": "straight-02", "checkpoint_tick": 10000, "dt": DT,
        "grid": [0, 40000, 1], "model_sha256": reg["model_sha256"],
        "sources_sha256": reg["sources_sha256"], "registration_sha256": file_sha(root / "registration.json"),
        "generation": "v12-development-seed42-straight02-active-tick10000",
    }
    if checkpoint["binding"] != expected_binding or result["registration_sha256"] != expected_binding["registration_sha256"]:
        raise ValueError("restoration identity mismatch")
    with np.load(dest / "expected.npz", allow_pickle=False) as expected, np.load(dest / "actual.npz", allow_pickle=False) as actual:
        if set(expected.files) != set(actual.files) or not all(np.array_equal(expected[name], actual[name]) for name in expected.files):
            return False
        if expected["core"].shape[0] != 100 or expected["dense"].shape[0] != 100:
            raise ValueError("restoration continuation horizon mismatch")
    a = json.loads((dest / "expected-digests.json").read_text())
    b = json.loads((dest / "actual-digests.json").read_text())
    return bool(result["passed"] and result["corrupted_destination_before_restore"] and a == b)


def verify_panel(root, stage):
    reg = json.loads((root / "registration.json").read_text())
    if file_sha(root / "model.mjb") != reg["model_sha256"] or file_sha(root / "sources.json") != reg["sources_sha256"]:
        raise ValueError("changed immutable experiment identity")
    for name, entry in json.loads((root / "sources.json").read_text()).items():
        if file_sha(root / entry["archive"]) != entry["sha256"] or file_sha(Path(name)) != entry["sha256"]:
            raise ValueError(f"changed stage source: {name}")
    seeds = reg["development_seeds"] if stage == "development" else reg["evaluation_seeds"]
    profiles = reg["profiles"] if stage == "development" else [PROFILE]
    expected = {f"{profile}--{seed}--{case[0]}": (profile, seed, case)
                for profile in profiles for seed in seeds for case in reg["cases"]}
    if {path.name for path in (root / stage).iterdir()} != set(expected):
        raise ValueError("incomplete/extra mechanical panel")
    metrics = {}
    for name, (profile, seed, case) in expected.items():
        result = reconstruct_trial(root, root / stage / name, reg)
        meta = result["conditions"]
        if (meta["profile"], meta["seed"], meta["case"], meta["stage"]) != (profile, seed, case, stage):
            raise ValueError("condition identity mismatch")
        metrics[name] = result
    aggregate = {}
    for seed in seeds:
        speed = [metrics[f"{PROFILE}--{seed}--{case}"]["forward_mean_mm_s"]
                 for case in ["straight-008", "straight-02", "straight-04"]]
        aggregate[f"speed-{seed}"] = bool(speed[0] > 0.2 and all(b - a > 0.2 for a, b in zip(speed, speed[1:])))
    if stage == "development":
        aggregate["active_restoration"] = _verify_restoration(root, reg)
    else:
        original = root / stage / f"{PROFILE}--31042--straight-02"
        repeat = root / "repeat" / f"{PROFILE}--31042--straight-02"
        reconstruct_trial(root, repeat, reg)
        equal = True
        for stream, width in [("core", _width(CORE)), ("dense", _width(DENSE))]:
            left = read_dense(original / stream, 40001, width)
            right = read_dense(repeat / stream, 40001, width)
            equal &= all(np.array_equal(a, b) for a, b in zip(left, right))
        lt = json.loads((original / "contacts" / "terminal.json").read_text())["initialized_rows"]
        rt = json.loads((repeat / "contacts" / "terminal.json").read_text())["initialized_rows"]
        left = read_stream(original / "contacts", lt, _width(CONTACT))
        right = read_stream(repeat / "contacts", rt, _width(CONTACT))
        equal &= all(np.array_equal(a, b) for a, b in zip(left, right))
        aggregate["repeat"] = bool(equal)
    candidate = [value for value in metrics.values() if value["conditions"]["profile"] == PROFILE]
    passed = all(aggregate.values()) and all(all(trial["gates"].values()) for trial in candidate)
    return {
        "schema": "independent-mechanical-decision/v12", "stage": stage,
        "candidate_passed": bool(passed), "scientific_admission": False,
        "registration_sha256": file_sha(root / "registration.json"),
        "aggregate_gates": aggregate, "trials": metrics,
        "evaluation_allowed": bool(passed and stage == "development"),
        "neural_allowed": bool(passed and stage == "evaluation"),
        "product_allowed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--stage", choices=["development", "evaluation"], default="development")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_panel(args.root, args.stage)
    write_json(args.output, result)
    print(json.dumps({"candidate_passed": result["candidate_passed"],
                      "aggregate_gates": result["aggregate_gates"]}))


if __name__ == "__main__":
    main()
