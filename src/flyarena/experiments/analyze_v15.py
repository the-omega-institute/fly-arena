"""Prospective v15 analysis using accepted strict paired-state and cycle contracts."""
import json
from pathlib import Path
import numpy as np
import mujoco as mj
from ..common import file_sha, write_json
from .mechanical_v15 import CORE, DENSE, CONTACT, DT, _slices, _width, panel, PROFILE, CONTROL, validate_freeze
from .behavior_v12_correction import (
    ROWS, TOLERANCE, _read_dense, _read_stream, _int_column, _prepare_detached_state,
    _geometry_from_prepared, _foot_metadata, _body_point_velocities, _point_jacobian_velocities,
    _cycle_metrics, _phase_window_contract,
)


def trial_identity(root, trial, registration, expected):
    starts = [json.loads((trial/stream/'start.json').read_text()) for stream in ('core','dense','contacts')]
    wanted = {'stage': trial.parent.name, 'profile': expected[0], 'seed': expected[1], 'case': expected[2],
              'registration_sha256': file_sha(root/'registration.json'), 'sources_sha256': registration['sources_sha256']}
    if any(value != wanted for value in starts) or not json.loads((trial/'trial-terminal.json').read_text())['complete']:
        raise ValueError('v15 retained trial identity/completion mismatch')
    return starts[0]


def tracking(model, core):
    cs = _slices(CORE)
    addresses = model.jnt_qposadr[model.actuator_trnid[:42, 0]]
    actual = core[:, cs['qpos']][:, addresses]
    error = actual-core[:, cs['ctrl']][:, :42]
    passive = sorted(set(range(7, model.nq))-set(int(i) for i in addresses))
    return {'actuated_qpos_addresses': addresses.tolist(),
            'active_tracking_rms_rad': np.sqrt(np.mean(error[6000:25001]**2, axis=0)).tolist(),
            'active_tracking_max_abs_rad': np.max(np.abs(error[6000:25001]), axis=0).tolist(),
            'passive_qpos_addresses': passive,
            'active_passive_range_rad': np.ptp(core[6000:25001, cs['qpos']][:, passive], axis=0).tolist(),
            'source': 'actual qpos versus retained applied ctrl; passive positions retained every tick in core'}


def durations(cycle):
    return {kind: [[(record['end_tick_exclusive']-record['start_tick'])*DT for record in records]
                   for records in cycle[kind+'_cycles']] for kind in ('swing','stance')}


def aggregate(trials, stage):
    result = {}
    seeds = (42, 43) if stage == 'development' else (31042, 31043)
    profiles = (CONTROL, PROFILE) if stage == 'development' else (PROFILE,)
    for profile in profiles:
        for seed in seeds:
            values = [trials[f'{profile}--{seed}--{case}']['forward_mean_mm_s']
                      for case in ('straight-008','straight-02','straight-04')]
            result[f'{profile}--{seed}--speed-dose'] = bool(values[0] > .2 and all(b-a > .2 for a,b in zip(values, values[1:])))
    return result


def analyze_trial(
    original_root: Path,
    trial: Path,
    expected: tuple[str, int, list],
    original_registration: dict,
    model: mj.MjModel,
    model_meta: dict,
    derived_dir: Path,
    budget,
) -> dict:
    cs, ds, es = _slices(CORE), _slices(DENSE), _slices(CONTACT)
    meta = trial_identity(original_root, trial, original_registration, expected)
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
    endpoint_root = np.empty((ROWS, 3), dtype=np.float64)
    endpoint_rotation = np.empty((ROWS, 9), dtype=np.float64)
    coherent_contacts = np.zeros((len(contacts), 3), dtype=np.float64)
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
        if state_tick % 1000 == 0:
            budget.check()
        _prepare_detached_state(
            model,
            detached,
            core[state_tick, cs["qpos"]],
            core[state_tick, cs["qvel"]],
        )
        endpoint_height[state_tick], endpoint_center[state_tick], endpoint_ap[state_tick] = _geometry_from_prepared(
            detached, model_meta
        )

        endpoint_root[state_tick] = detached.xpos[model_meta["thorax"]]
        endpoint_rotation[state_tick] = detached.xmat[model_meta["thorax"]]

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
            coherent_contacts[begin:end] = pre_velocity
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
        strict_active_window=common > original_registration["controller"]["silence_common_max"],
    )
    position = endpoint_root
    rotation = endpoint_rotation.reshape(-1, 3, 3)
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
            endpoint_thorax_position=endpoint_root,
            endpoint_thorax_rotation=endpoint_rotation,
            coherent_contact_ticks=contact_ticks,
            coherent_contact_velocity=coherent_contacts,
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
        "feedback": {"trigger_counts":core[3001:25001,cs["trigger_mask"]].sum(axis=0).astype(int).tolist(), "raw_retraction_max":core[:,cs["retraction"]].max(axis=0).tolist(), "raw_retraction_over80_ticks":(core[3001:25001,cs["retraction"]]>80).sum(axis=0).tolist(), "minimum_vertex_changes":np.count_nonzero(np.diff(core[3001:25001,cs["minimum_vertex"]],axis=0),axis=0).tolist()},
        "schema": "behavior-v15-trial/v1",
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
        "tracking_and_passive_response": tracking(model, core),
        "realized_swing_stance_durations": durations(cycle),
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


def analyze_panel(root, stage, budget):
    registration = validate_freeze(root)
    expected = panel(stage)
    actual = {p.name for p in (root/stage).iterdir() if p.is_dir()}
    names = {f'{profile}--{seed}--{case[0]}' for profile,seed,case in expected}
    if actual != names:
        raise ValueError('v15 panel exact trial set mismatch')
    derived = root/f'{stage}-derived'
    derived.mkdir(exist_ok=False)
    model = mj.MjModel.from_binary_path(str(root/'model.mjb'))
    meta = _foot_metadata(model, registration)
    trials = {}
    for profile, seed, case in expected:
        name = f'{profile}--{seed}--{case[0]}'
        trials[name] = analyze_trial(root, root/stage/name, (profile,seed,case), registration, model, meta, derived, budget)
        print(json.dumps({'analyzed': stage+'/'+name, 'physical_seconds': budget.steps*DT}), flush=True)
    aggregates = aggregate(trials, stage)
    candidate_passed = (all(all(value['gates'].values()) for name,value in trials.items() if name.startswith(PROFILE+'--'))
                        and all(value for name,value in aggregates.items() if name.startswith(PROFILE+'--')))
    result = {'schema':'behavior-v15-analysis/v1','stage':stage,'registration_sha256':file_sha(root/'registration.json'),
              'trials':trials,'aggregate_gates':aggregates,'candidate_passed':candidate_passed,
              'trial_count':len(trials),'raw_contact_rows':sum(value['raw_contact_rows'] for value in trials.values()),
              'scientific_admission':False,'resources':budget.report()}
    write_json(root/f'{stage}-analysis.json',result)
    return result
