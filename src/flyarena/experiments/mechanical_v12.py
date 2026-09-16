"""Prospectively registered v12 source-native excursion experiment."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import resource
import shutil
import subprocess
import sys
import time
import traceback

import mujoco as mj
import numpy as np
from flygym.anatomy import LEGS
from flygym.compose import ActuatorType
from flygym_demo.complex_terrain.common import (
    apply_locomotion_action,
    get_default_locomotion_dof_order,
)
from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation

from ..body import Bodies
from ..common import ROOT, digest, file_sha, write_json
from .cadence_v12 import ExcursionHybridController, PROFILE
from .evidence_v10 import NumericEvidence
from .mechanical_v10 import (
    Budget,
    CASES,
    DT,
    GEOMETRY,
    SCENE,
    failure_record,
    finish_stream,
    foot_ids,
    integration,
    raise_failure,
    retention_attempt,
    source_files,
    state_finite,
)

ORIGINAL = Path("/Users/lexa/Desktop/lexa/omega/fly-arena")
APPROVAL = ORIGINAL / "var/sshx/behavior-v12/approved-plan.json"
SUBJECTS = ORIGINAL / "var/sshx/sensorimotor-v7/subjects.json"
BASE = "9d25fdac43e6d623fdc34741c2677662421b925c"
ANALYSIS_TICKS = (6000, 25000)
CHECKPOINT_TICK = 10000
CONTINUATION_TICKS = 100

CORE = [
    ("qpos", 73), ("qvel", 72), ("thorax_position", 3), ("thorax_rotation", 9),
    ("input", 2), ("ctrl", 48), ("actuator_force", 48), ("phases", 6),
    ("magnitudes", 6), ("targets", 6), ("adhesion", 6), ("retraction", 6),
    ("stumbling", 6), ("persistence", 6), ("net_correction", 6),
]
DENSE = [
    ("whole_foot_min_height", 6), ("tarsus5_centroid", 18), ("thorax_ap", 6),
    ("summed_positive_normal", 6), ("force_weighted_tangent_numerator", 6),
    ("peak_tangent_speed", 6), ("contact_count", 6), ("positive_force_count", 6),
]
CONTACT = [
    ("contact_index", 1), ("foot_geom", 1), ("ground_geom", 1),
    ("foot_is_geom1", 1), ("signed_distance", 1), ("position", 3),
    ("frame", 9), ("wrench_contact_frame", 6), ("relative_velocity_world", 3),
]
CACHE_CONTACT_FIELDS = (
    "dist", "pos", "frame", "includemargin", "friction", "solref", "solreffriction",
    "solimp", "mu", "H", "dim", "geom", "geom1", "geom2", "flex", "elem",
    "vert", "exclude", "efc_address",
)
CACHED_FIELDS = (
    "qpos", "qvel", "qacc", "qacc_warmstart", "ctrl", "actuator_force", "actuator_velocity",
    "actuator_length", "qfrc_actuator", "qfrc_constraint", "qfrc_smooth", "qfrc_bias",
    "qfrc_passive", "qfrc_gravcomp", "sensordata", "xpos", "xquat", "xmat", "geom_xpos",
    "geom_xmat", "site_xpos", "site_xmat", "subtree_com", "subtree_linvel", "subtree_angmom",
    "cvel", "cdof", "cinert", "efc_J", "efc_D", "efc_force", "efc_vel", "efc_pos",
    "efc_margin", "efc_frictionloss", "qfrc_applied", "xfrc_applied", "mocap_pos",
    "mocap_quat", "userdata", "plugin_state", "actuator_moment",
)


def _width(schema):
    return sum(n for _, n in schema)


def _slices(schema):
    out, offset = {}, 0
    for name, size in schema:
        out[name] = slice(offset, offset + size)
        offset += size
    return out


def new_body(seed, profile):
    body = Bodies(deepcopy(SCENE), 1, seed)
    if profile == PROFILE:
        controller = ExcursionHybridController(timestep=DT)
        controller.reset(seed=seed)
        body.controllers[0] = controller
        apply_locomotion_action(body.sim, "fly-0", controller.step(np.zeros(2), None))
    elif profile != "historical":
        raise ValueError(profile)
    return body


def _sha_array(value):
    value = np.ascontiguousarray(value)
    h = hashlib.sha256()
    h.update(value.dtype.str.encode())
    h.update(np.asarray(value.shape, dtype=np.int64).tobytes())
    h.update(value.tobytes())
    return h.hexdigest()


def _numeric_cache(data):
    """Describe all exposed numeric MjData arrays plus the variable contact cache."""
    result = {}
    for name in CACHED_FIELDS:
        if not hasattr(data, name):
            continue
        value = getattr(data, name)
        if isinstance(value, np.ndarray) and value.dtype.kind in "fiub":
            finite = bool(value.dtype.kind != "f" or np.isfinite(value).all())
            if not finite:
                raise ValueError(f"nonfinite native cache field: {name}")
            result[name] = {
                "shape": list(value.shape), "dtype": value.dtype.str, "finite": finite,
                "sha256": _sha_array(value)
            }
    contacts = data.contact
    for name in CACHE_CONTACT_FIELDS:
        value = np.asarray(getattr(contacts, name))
        if value.dtype.kind == "f" and not np.isfinite(value).all():
            raise ValueError(f"nonfinite native contact cache: {name}")
        result[f"contact.{name}"] = {
            "shape": list(value.shape), "dtype": value.dtype.str, "finite": True,
            "sha256": _sha_array(value)
        }
    result["scalar.time"] = {"value": float(data.time)}
    result["scalar.ncon"] = {"value": int(data.ncon)}
    result["scalar.nefc"] = {"value": int(data.nefc)}
    return result


def _controller_schema(controller):
    cpg = controller.cpg_network
    arrays = {
        "phases": cpg.curr_phases, "magnitudes": cpg.curr_magnitudes,
        "intrinsic_freqs": cpg.intrinsic_freqs, "intrinsic_amps": cpg.intrinsic_amps,
        "coupling_weights": cpg.coupling_weights, "phase_biases": cpg.phase_biases,
        "convergence_coefs": cpg.convergence_coefs,
        "retraction": controller.retraction_correction,
        "stumbling": controller.stumbling_correction,
        "persistence": controller.retraction_persistence_counter,
        "last_angles": controller._last_angles, "last_adhesion": controller._last_adhesion,
        "rng_keys": cpg.random_state.get_state()[1],
    }
    result = {}
    for name, value in arrays.items():
        value = np.asarray(value)
        if value.dtype.kind == "f" and not np.isfinite(value).all():
            raise ValueError(f"nonfinite controller checkpoint: {name}")
        result[name] = {"shape": list(value.shape), "dtype": value.dtype.str}
    return result


def _controller_state_manifest(controller):
    cpg = controller.cpg_network
    arrays = {
        "phases": cpg.curr_phases, "magnitudes": cpg.curr_magnitudes,
        "intrinsic_freqs": cpg.intrinsic_freqs, "intrinsic_amps": cpg.intrinsic_amps,
        "coupling_weights": cpg.coupling_weights, "phase_biases": cpg.phase_biases,
        "convergence_coefs": cpg.convergence_coefs,
        "base_intrinsic_freqs": controller._base_intrinsic_freqs,
        "base_intrinsic_amps": controller._base_intrinsic_amps,
        "base_coupling": controller._base_coupling,
        "retraction": controller.retraction_correction,
        "stumbling": controller.stumbling_correction,
        "persistence": controller.retraction_persistence_counter,
        "last_angles": controller._last_angles, "last_adhesion": controller._last_adhesion,
    }
    for name, value in controller.last_info.items():
        if value is not None:
            arrays[f"last_info.{name}"] = np.asarray(value)
    array_manifest = {}
    for name, value in arrays.items():
        value = np.asarray(value)
        if value.dtype.kind == "f" and not np.isfinite(value).all():
            raise ValueError(f"nonfinite controller state: {name}")
        array_manifest[name] = {"shape": list(value.shape), "dtype": value.dtype.str,
                                "sha256": _sha_array(value)}
    rng = cpg.random_state.get_state()
    scalars = {
        "cpg_timestep": float(cpg.timestep), "cpg_num": int(cpg.num_cpgs),
        "stumbling_force_threshold": float(controller.stumbling_force_threshold),
        "retraction_height_threshold": float(controller.retraction_height_threshold),
        "retraction_rates": [float(x) for x in controller.retraction_rates],
        "stumbling_rates": [float(x) for x in controller.stumbling_rates],
        "max_correction": float(controller.max_correction),
        "swing_extension": float(controller.swing_extension),
        "retraction_persistence_steps": int(controller.retraction_persistence_steps),
        "retraction_persistence_initiation_threshold": float(controller.retraction_persistence_initiation_threshold),
        "enable_adhesion": bool(controller.enable_adhesion), "legs": list(controller.legs),
        "rng_algorithm": rng[0], "rng_keys": _sha_array(rng[1]), "rng_position": int(rng[2]),
        "rng_has_gauss": int(rng[3]), "rng_cached_gaussian": float(rng[4]),
    }
    return {"arrays": array_manifest, "scalars": scalars}


def _controller_state_sha256(controller):
    return digest(_controller_state_manifest(controller))


def _compiled_arrays(model):
    names = [
        "jnt_axis", "jnt_pos", "jnt_type", "jnt_limited", "jnt_range", "jnt_qposadr",
        "jnt_dofadr", "actuator_trntype", "actuator_trnid", "actuator_gear",
        "actuator_gainprm", "actuator_biasprm", "actuator_forcerange",
        "actuator_forcelimited", "actuator_ctrlrange", "actuator_ctrllimited", "geom_type",
        "geom_dataid", "geom_bodyid", "geom_contype", "geom_conaffinity", "geom_friction",
        "mesh_vert", "mesh_vertadr", "mesh_vertnum", "mesh_face", "mesh_faceadr",
        "mesh_facenum", "body_mass", "body_inertia", "dof_damping", "qpos0",
    ]
    return {name: np.asarray(getattr(model, name)) for name in names}


def freeze(root):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != BASE:
        raise ValueError(f"wrong source base: {head}")
    root.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(APPROVAL, root / "approved-plan.json")
    shutil.copyfile(SUBJECTS, root / "subjects.json")
    sources = {}
    paths = source_files() + [
        ROOT / "pyproject.toml", ROOT / "uv.lock", ROOT / "scripts/behavior_v12.sh",
        ROOT / "scripts/plot_behavior_v12.py", ROOT / "tests/test_behavior_v12.py",
    ]
    for index, path in enumerate(sorted(set(paths))):
        dest = root / "sources" / f"{index:04d}-{path.name}"
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, dest)
        sources[str(path)] = {"sha256": file_sha(path), "archive": str(dest.relative_to(root))}
    write_json(root / "sources.json", sources)
    subjects = json.loads(SUBJECTS.read_text())
    artifacts = {}
    for subject in subjects:
        path = ORIGINAL / "var/artifacts" / subject["artifact_id"]
        artifacts[subject["id"]] = {str(f): file_sha(f) for f in sorted(path.iterdir()) if f.is_file()}
    graph = {str(p): file_sha(p) for p in sorted((ORIGINAL / "data/connectome").glob("*")) if p.is_file()}
    graph.update({str(p): file_sha(p) for p in sorted((ORIGINAL / "data/connectome/research-v2").glob("*")) if p.is_file()})
    body = new_body(42, PROFILE)
    model = body.model
    mj.mj_saveModel(model, str(root / "model.mjb"))
    foot = foot_ids(model)
    if len(set(foot.tolist())) != 30 or np.any(foot < 0):
        raise ValueError("missing native foot collision geometries")
    native_order = body.sim.world.fly_lookup["fly-0"].get_actuated_jointdofs_order(ActuatorType.POSITION)
    if list(native_order) != get_default_locomotion_dof_order() or list(body.controllers[0].legs) != list(LEGS):
        raise ValueError("native controller order mismatch")
    arrays = {}
    for name, value in _compiled_arrays(model).items():
        path = root / f"model-{name}.npy"
        np.save(path, value, allow_pickle=False)
        arrays[name] = {"sha256": file_sha(path), "shape": list(value.shape), "dtype": str(value.dtype)}
    names = {kind: [mj.mj_id2name(model, obj, i) for i in range(count)] for kind, obj, count in [
        ("joint", mj.mjtObj.mjOBJ_JOINT, model.njnt),
        ("actuator", mj.mjtObj.mjOBJ_ACTUATOR, model.nu),
        ("geom", mj.mjtObj.mjOBJ_GEOM, model.ngeom),
        ("body", mj.mjtObj.mjOBJ_BODY, model.nbody),
    ]}
    write_json(root / "model-names.json", names)
    c = body.controllers[0]
    swing_periods = {leg: [float(c.preprogrammed_steps.swing_period[leg][0]),
                            float(c.preprogrammed_steps.swing_period[leg][1] + c.swing_extension)]
                     for leg in c.legs}
    registration = {
        "schema": "mechanical-registration/v12", "candidate": PROFILE,
        "approved_plan_sha256": file_sha(APPROVAL), "source_base": BASE,
        "sources_sha256": file_sha(root / "sources.json"), "model_sha256": file_sha(root / "model.mjb"),
        "subjects_sha256": file_sha(SUBJECTS), "artifacts": artifacts, "graph": graph,
        "compiled_arrays": arrays, "native_names_sha256": file_sha(root / "model-names.json"),
        "dependencies": {p: importlib.metadata.version(p) for p in ["numpy", "scipy", "mujoco", "flygym"]},
        "scene": SCENE, "dt": DT, "ticks": 40000, "active_input_ticks": [3000, 25000],
        "analysis_ticks": list(ANALYSIS_TICKS), "stop_state_ticks": [30000, 40000],
        "core_schema": CORE, "dense_schema": DENSE, "contact_schema": CONTACT,
        "core_stride": 1, "dense_stride": 1, "contact_stride": 1, "chunk_rows": 1000,
        "profiles": ["historical", PROFILE], "development_seeds": [42, 43],
        "evaluation_seeds": [31042, 31043], "cases": CASES,
        "repeat": [PROFILE, "straight-02", 31042],
        "controller": {
            "candidate_equation": "targets=1.0*[1-a]*3+1.0*[1+a]*3; phase frequency and coupling scale=c/0.6",
            "only_change_from_v10": "nominal active target amplitude scalar 0.6 to exactly 1.0",
            "convergence_per_s": 20.0, "silence_common_max": 1e-4,
            "domain": "finite nonnegative shape(2), c<=0.4, abs(a)<=0.8, tolerance 1e-12",
            "turn_target_max": 1.8, "frequency": c._base_intrinsic_freqs.tolist(),
            "coupling": c._base_coupling.tolist(), "swing_periods_strict_modulo": swing_periods,
        },
        "measurement": {
            "native_phase_alignment": "row0 is post-initial mj_forward and is excluded from quadrature; row k>0 is live MjData immediately after the kth mj_step. qpos/qvel, geom cache, contacts, efc-derived mj_contactForce and velocities share that post-step native state. These forces are the solver result for interval (k-1,k], so dt quadrature assigns them exactly once to that interval. No observer forward, warmstart edit or hidden integration.",
            "contact_velocity": "world material velocity at each actual contact point is computed directly as native mj_jac(point,body)@qvel for foot minus ground; tangent projection removes the native contact-frame row0 normal component",
            "contact_force": "all actual live foot-ground contacts retained including signed positive margins and zero/negative roundoff; finite wrench[0]>0 contributes native normal support",
            "geometry": "live post-step geom_xpos/xmat; all vertices of all five collision meshes per leg; tarsus5 material centroid; freely responding root and passives",
            "foot_geom_ids": foot.tolist(),
            "cycles": "maximal strict native commanded swing or complement stance runs, both bounding opposite-state samples inside inclusive ticks 6000..25000; stored half-open [start,end); phase is unwrapped and must increase; all complete runs retained, partials separate",
            "median": "centered 3ms discrete median is exactly 31 samples tick-15..tick+15 (3.0ms endpoint span), no padding; a value is used only when all 31 samples lie inside the same complete commanded swing; ordinary sorted-value median (16th value)",
            "actual_protraction": "within each complete swing filtered tarsus5 thorax-forward AP; PEP earliest exact global minimum; AEP earliest later occurrence of that same swing's exact global maximum; absent later maximum, flatness or nonpositive duration/excursion is inconclusive; excursion must be >0.02mm",
            "recovery": "inside every valid PEP-to-AEP interval, contiguous >=30 integration intervals (3ms) where all-five-mesh minimum height strictly >0.02mm and summed positive normal force equals zero",
            "support": "every complete stance has contiguous >=30 integration intervals (3ms) of summed finite positive native normal force",
            "slip": "S=dt*sum rows in complete stance of sum(Fn*|vrel_tangent|)/sum(Fn), zero when unloaded; each post-step loaded row exactly once, including single rows; require S<0.15mm",
            "unchanged_bounds": {"upright_z": 0.8, "speed": 0.2, "adjacent_speed_increment": 0.2,
                "straight_abs_yaw_rate": 0.15, "turn_abs_yaw": 0.1, "clearance": 0.02,
                "slip": 0.15, "stop_displacement": 0.25, "stop_speed": 0.1},
        },
        "restoration": {
            "checkpoint": [PROFILE, 42, "straight-02", CHECKPOINT_TICK],
            "destination": [PROFILE, 43, "straight-02", 40000],
            "continuation_ticks": [CHECKPOINT_TICK + 1, CHECKPOINT_TICK + CONTINUATION_TICKS],
            "additional_physical_seconds": CONTINUATION_TICKS * DT,
            "input": [0.2, 0.2],
            "contract": "after scheduled seed43 trial completes, corrupt destination then strict-bind and restore full mj_copyData cache/controller/RNG/tick/drives; bitwise compare integration, native cache digests, controller hashes, core, geometry and raw contacts",
        },
        "panel": {
            "development": "historical+candidate x seeds42/43 x 8 = 128s plus 0.01s restoration",
            "evaluation": "candidate x seeds31042/31043 x 8 = 64s, only after development pass",
            "repeat": "candidate straight-02 seed31042 exact 4s, only after development pass",
            "planned_mechanical_seconds": 196.01,
        },
        "decisions": "complete fixed development unless unsafe/cap/retention failure; any candidate false or inconclusive blocks untouched evaluation, neural and product; no second candidate or threshold change",
        "resource_caps": {"mechanical_seconds": 260, "neural_seconds": 259, "wall_seconds": 28800,
            "rss_bytes": 16 * 1024**3, "evidence_bytes": 8 * 1024**3, "workers": 1},
        "failure_retention": "v10 corrected independent core/dense/contact/resource finalization; abort before next trial on any incomplete retention",
    }
    write_json(root / "registration.json", registration)
    write_json(root / "preregistration.json", {
        "registered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registration_sha256": file_sha(root / "registration.json"),
        "sources_sha256": registration["sources_sha256"],
        "timing_discretization": registration["measurement"],
        "no_outcomes_observed": True,
    })
    return registration


def validate_freeze(root):
    reg = json.loads((root / "registration.json").read_text())
    if file_sha(root / "sources.json") != reg["sources_sha256"]:
        raise ValueError("source manifest changed")
    for name, entry in json.loads((root / "sources.json").read_text()).items():
        if file_sha(Path(name)) != entry["sha256"] or file_sha(root / entry["archive"]) != entry["sha256"]:
            raise ValueError(f"stage source changed: {name}")
    if file_sha(root / "model.mjb") != reg["model_sha256"]:
        raise ValueError("model changed")
    if file_sha(root / "approved-plan.json") != reg["approved_plan_sha256"]:
        raise ValueError("approved plan changed")
    return reg


class NativeRecorder:
    def __init__(self, body):
        self.body = body
        self.model, self.data = body.model, body.data
        self.foot = foot_ids(self.model)
        self.foot_leg = {int(g): i // 5 for i, g in enumerate(self.foot)}
        self.ground = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_GEOM, "ground_plane")
        self.centroids = []
        for geom in self.foot:
            mesh = int(self.model.geom_dataid[geom])
            begin, count = int(self.model.mesh_vertadr[mesh]), int(self.model.mesh_vertnum[mesh])
            vertices = np.asarray(self.model.mesh_vert[begin:begin + count], dtype=np.float64)
            self.centroids.append(vertices.mean(axis=0))

    def row(self, u):
        b, d, model, c = self.body, self.data, self.model, self.body.controllers[0]
        adhesion = np.asarray(d.ctrl[42:48], dtype=np.float64)
        core = np.concatenate([
            d.qpos, d.qvel, d.xpos[b.body_ids[0]], d.xmat[b.body_ids[0]], u, d.ctrl,
            d.actuator_force, c.cpg_network.curr_phases, c.cpg_network.curr_magnitudes,
            c.cpg_network.intrinsic_amps, adhesion, c.retraction_correction,
            c.stumbling_correction, c.retraction_persistence_counter,
            c.last_info.get("net_corrections", np.zeros(6)),
        ])
        heights = np.full(6, np.inf)
        centroids = np.empty((6, 3))
        for index, geom in enumerate(self.foot):
            mesh = int(model.geom_dataid[geom])
            begin, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
            vertices = np.asarray(model.mesh_vert[begin:begin + count], dtype=np.float64)
            rotation = d.geom_xmat[geom].reshape(3, 3)
            low = float((vertices @ rotation[2]).min() + d.geom_xpos[geom, 2])
            leg = index // 5
            heights[leg] = min(heights[leg], low)
            if index % 5 == 4:
                centroids[leg] = rotation @ self.centroids[index] + d.geom_xpos[geom]
        thorax = b.body_ids[0]
        forward = d.xmat[thorax].reshape(3, 3)[:, 0]
        ap = (centroids - d.xpos[thorax]) @ forward
        summed = np.zeros(6)
        weighted = np.zeros(6)
        peak = np.zeros(6)
        counts = np.zeros(6)
        positive = np.zeros(6)
        events = []
        wrench = np.empty(6)
        for contact_index in range(d.ncon):
            contact = d.contact[contact_index]
            g1, g2 = int(contact.geom1), int(contact.geom2)
            if g1 in self.foot_leg and g2 == self.ground:
                foot_geom, foot_is_g1 = g1, 1.0
            elif g2 in self.foot_leg and g1 == self.ground:
                foot_geom, foot_is_g1 = g2, 0.0
            else:
                continue
            mj.mj_contactForce(model, d, contact_index, wrench)
            foot_body = int(model.geom_bodyid[foot_geom])
            ground_body = int(model.geom_bodyid[self.ground])
            point = np.asarray(contact.pos, dtype=np.float64)
            foot_jac = np.zeros((3, model.nv))
            ground_jac = np.zeros((3, model.nv))
            mj.mj_jac(model, d, foot_jac, None, point, foot_body)
            mj.mj_jac(model, d, ground_jac, None, point, ground_body)
            relative = (foot_jac - ground_jac) @ d.qvel
            frame = np.asarray(contact.frame, dtype=np.float64).reshape(3, 3)
            normal = frame[0]
            tangent = relative - normal * float(np.dot(relative, normal))
            speed = float(np.linalg.norm(tangent))
            leg = self.foot_leg[foot_geom]
            fn = float(wrench[0])
            counts[leg] += 1
            peak[leg] = max(peak[leg], speed)
            if fn > 0:
                summed[leg] += fn
                weighted[leg] += fn * speed
                positive[leg] += 1
            events.append(np.concatenate([
                [contact_index, foot_geom, self.ground, foot_is_g1, float(contact.dist)],
                point, frame.ravel(), wrench.copy(), relative,
            ]))
        dense = np.concatenate([heights, centroids.ravel(), ap, summed, weighted, peak, counts, positive])
        return core, dense, events


def step(body, u):
    observation = HybridControllerObservation.from_sim(body.sim, "fly-0")
    action = body.controllers[0].step(u, observation)
    apply_locomotion_action(body.sim, "fly-0", action)
    body.drives[0] = u
    body.sim.step()
    body.tick += 1


def _binding(root, reg):
    return {
        "profile": PROFILE, "trial": "development/source-native-excursion-v12--42--straight-02",
        "seed": 42, "case": "straight-02", "checkpoint_tick": CHECKPOINT_TICK,
        "dt": DT, "grid": [0, 40000, 1], "model_sha256": reg["model_sha256"],
        "sources_sha256": reg["sources_sha256"], "registration_sha256": file_sha(root / "registration.json"),
        "generation": "v12-development-seed42-straight02-active-tick10000",
    }


def capture_active_checkpoint(root, body, reg):
    data = mj.MjData(body.model)
    mj.mj_copyData(data, body.model, body.data)
    controller_bytes = pickle.dumps(body.controllers[0].checkpoint(), protocol=5)
    return {
        "binding": _binding(root, reg), "data": data, "integration": integration(body),
        "cache": _numeric_cache(data), "controller_bytes": controller_bytes,
        "controller_sha256": hashlib.sha256(controller_bytes).hexdigest(),
        "controller_schema": _controller_schema(body.controllers[0]),
        "tick": body.tick, "drives": body.drives.copy(), "expected": [],
    }


def validate_active_checkpoint(root, body, checkpoint, reg):
    required = {"binding", "data", "integration", "cache", "controller_bytes", "controller_sha256",
                "controller_schema", "tick", "drives", "expected"}
    if set(checkpoint) != required or checkpoint["binding"] != _binding(root, reg):
        raise ValueError("active checkpoint identity/binding mismatch")
    size = mj.mj_stateSize(body.model, mj.mjtState.mjSTATE_INTEGRATION)
    state = checkpoint["integration"]
    if not isinstance(state, np.ndarray) or state.shape != (size,) or state.dtype != np.float64 or not np.isfinite(state).all():
        raise ValueError("invalid active integration state")
    drives = checkpoint["drives"]
    if not isinstance(drives, np.ndarray) or drives.shape != (1, 2) or drives.dtype != np.float64 or not np.isfinite(drives).all():
        raise ValueError("invalid active drives")
    if type(checkpoint["tick"]) is not int or checkpoint["tick"] != CHECKPOINT_TICK:
        raise ValueError("invalid active tick")
    if _numeric_cache(checkpoint["data"]) != checkpoint["cache"]:
        raise ValueError("active native cache manifest mismatch")
    raw = checkpoint["controller_bytes"]
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != checkpoint["controller_sha256"]:
        raise ValueError("active controller payload mismatch")
    candidate = pickle.loads(raw)
    if set(candidate) != {"version", "state"} or set(candidate["state"]) != set(body.controllers[0].__dict__):
        raise ValueError("active controller schema mismatch")
    shadow = deepcopy(body.controllers[0])
    shadow.restore(candidate)
    if _controller_schema(shadow) != checkpoint["controller_schema"]:
        raise ValueError("active controller numeric schema mismatch")


def restore_active_checkpoint(root, body, checkpoint, reg):
    validate_active_checkpoint(root, body, checkpoint, reg)
    controller = pickle.loads(checkpoint["controller_bytes"])
    mj.mj_copyData(body.data, body.model, checkpoint["data"])
    body.controllers[0].restore(controller)
    body.tick = checkpoint["tick"]
    body.drives[:] = checkpoint["drives"]
    if _numeric_cache(body.data) != checkpoint["cache"] or not np.array_equal(integration(body), checkpoint["integration"]):
        raise ValueError("active restore did not reproduce native cache")


def _continuation_sample(body, recorder, u):
    step(body, u)
    state_finite(body)
    core, dense, contacts = recorder.row(u)
    return {
        "core": core, "dense": dense, "contacts": np.asarray(contacts, dtype=np.float64).reshape(-1, _width(CONTACT)),
        "integration": integration(body), "cache": _numeric_cache(body.data),
        "controller_state_sha256": _controller_state_sha256(body.controllers[0]),
    }


def save_restoration(root, checkpoint, actual):
    expected = checkpoint["expected"]
    equal = len(expected) == len(actual) == CONTINUATION_TICKS
    for left, right in zip(expected, actual):
        equal &= all(np.array_equal(left[name], right[name]) for name in ["core", "dense", "contacts", "integration"])
        equal &= (left["cache"] == right["cache"] and
                  left["controller_state_sha256"] == right["controller_state_sha256"])
    dest = root / "restoration"
    dest.mkdir(exist_ok=False)
    for prefix, samples in [("expected", expected), ("actual", actual)]:
        offsets = [0]
        contact_rows = []
        for sample in samples:
            contact_rows.append(sample["contacts"])
            offsets.append(offsets[-1] + len(sample["contacts"]))
        with (dest / f"{prefix}.npz").open("xb") as handle:
            np.savez_compressed(handle,
                core=np.asarray([s["core"] for s in samples]), dense=np.asarray([s["dense"] for s in samples]),
                integration=np.asarray([s["integration"] for s in samples]),
                contacts=np.concatenate(contact_rows) if contact_rows else np.empty((0, _width(CONTACT))),
                contact_offsets=np.asarray(offsets, dtype=np.int64))
        write_json(dest / f"{prefix}-digests.json", {
            "cache": [s["cache"] for s in samples],
            "controller_state_sha256": [s["controller_state_sha256"] for s in samples],
        })
    write_json(dest / "checkpoint.json", {
        "binding": checkpoint["binding"], "integration_shape": list(checkpoint["integration"].shape),
        "integration_dtype": checkpoint["integration"].dtype.str,
        "controller_sha256": checkpoint["controller_sha256"],
        "controller_schema": checkpoint["controller_schema"], "cache": checkpoint["cache"],
    })
    write_json(dest / "result.json", {
        "passed": bool(equal), "corrupted_destination_before_restore": True,
        "ticks": [CHECKPOINT_TICK + 1, CHECKPOINT_TICK + CONTINUATION_TICKS],
        "additional_physical_seconds": CONTINUATION_TICKS * DT,
        "comparisons": ["core", "dense", "raw_contacts", "mjSTATE_INTEGRATION", "full_native_cache", "controller_rng"],
        "registration_sha256": checkpoint["binding"]["registration_sha256"],
    })
    if not equal:
        raise ValueError("active physical restoration mismatch")


def run_trial(root, stage, profile, seed, case, budget, restoration):
    name, common, asymmetry = case
    dest = root / stage / f"{profile}--{seed}--{name}"
    body = new_body(seed, profile)
    recorder = NativeRecorder(body)
    reg = json.loads((root / "registration.json").read_text())
    for key in reg["compiled_arrays"]:
        if not np.array_equal(getattr(body.model, key), np.load(root / f"model-{key}.npy", allow_pickle=False)):
            raise ValueError(f"compiled array changed: {key}")
    meta = {"stage": stage, "profile": profile, "seed": seed, "case": case,
            "registration_sha256": file_sha(root / "registration.json"), "sources_sha256": reg["sources_sha256"]}
    dest.mkdir(parents=True, exist_ok=False)
    writers = {"core": None, "dense": None, "contacts": None}
    error = failing = None
    failures = []
    try:
        writers["core"] = NumericEvidence(dest / "core", _width(CORE), metadata=meta)
        writers["dense"] = NumericEvidence(dest / "dense", _width(DENSE), metadata=meta)
        writers["contacts"] = NumericEvidence(dest / "contacts", _width(CONTACT), metadata=meta)
        core, dense, contacts = recorder.row(np.zeros(2))
        writers["core"].append(0, core)
        writers["dense"].append(0, dense)
        for event in contacts:
            writers["contacts"].append(0, event)
        for k in range(40000):
            u = np.array([common * (1 - asymmetry), common * (1 + asymmetry)]) if 3000 <= k < 25000 else np.zeros(2)
            budget.steps += 1
            step(body, u)
            state_finite(body)
            core, dense, contacts = recorder.row(u)
            writers["core"].append(k + 1, core)
            writers["dense"].append(k + 1, dense)
            for event in contacts:
                writers["contacts"].append(k + 1, event)
            if stage == "development" and profile == PROFILE and seed == 42 and name == "straight-02":
                if k + 1 == CHECKPOINT_TICK:
                    restoration["checkpoint"] = capture_active_checkpoint(root, body, reg)
                elif CHECKPOINT_TICK < k + 1 <= CHECKPOINT_TICK + CONTINUATION_TICKS:
                    restoration["checkpoint"]["expected"].append({
                        "core": core.copy(), "dense": dense.copy(),
                        "contacts": np.asarray(contacts, dtype=np.float64).reshape(-1, _width(CONTACT)),
                        "integration": integration(body), "cache": _numeric_cache(body.data),
                        "controller_state_sha256": _controller_state_sha256(body.controllers[0]),
                    })
            if (k + 1) % 1000 == 0:
                budget.check()
        if stage == "development" and profile == PROFILE and seed == 43 and name == "straight-02":
            checkpoint = restoration.get("checkpoint")
            if checkpoint is None or len(checkpoint["expected"]) != CONTINUATION_TICKS:
                raise ValueError("missing bound seed42 active checkpoint continuation")
            body.data.qpos[0] += 1.0
            body.data.qvel[0] += 1.0
            body.data.ctrl[0] += 1.0
            body.controllers[0].cpg_network.curr_phases[0] += 1.0
            body.tick += 7
            body.drives[:] = 0.0
            restore_active_checkpoint(root, body, checkpoint, reg)
            actual = []
            u = np.array([0.2, 0.2])
            for _ in range(CONTINUATION_TICKS):
                budget.steps += 1
                actual.append(_continuation_sample(body, recorder, u))
            save_restoration(root, checkpoint, actual)
            budget.check()
    except BaseException as exc:
        error = exc
        failing = retention_attempt("failing-state", lambda: np.concatenate([
            np.array([body.tick]), body.data.qpos, body.data.qvel, body.data.qacc, body.data.ctrl,
            body.data.actuator_force, body.controllers[0].cpg_network.curr_phases,
            body.controllers[0].cpg_network.curr_magnitudes,
        ]), failures)
    extra = {"scheduled_physics_tick": 40000 if error is None else min(body.tick, 40000),
             "native_data_time": float(body.data.time),
             "resources": retention_attempt("trial-resources", budget.report, failures)}
    terminals = {}
    for stream in ["core", "dense", "contacts"]:
        writer = writers[stream]
        if writer is None:
            continue
        options = {"failing_values": failing, "snapshot": lambda: integration(body)} if stream == "core" else {}
        terminals[stream] = retention_attempt(stream + "-finish",
            lambda stream=stream, writer=writer, options=options: finish_stream(
                stream, writer, error, failures, extra=extra, **options), failures)
    retention_attempt("trial-terminal", lambda: write_json(dest / "trial-terminal.json", {
        "complete": error is None and not failures, "primary_failure": failure_record(error),
        "retention_failures": failures, "streams": terminals, "extra": extra,
    }), failures)
    raise_failure(error, failures)
    print(json.dumps({"completed": str(dest.relative_to(root)),
                      "total_physical_seconds": budget.steps * DT}), flush=True)


def run(root):
    validate_freeze(root)
    if (root / "execution-start.json").exists():
        raise ValueError("exclusive experiment already started")
    budget = Budget(root)
    write_json(root / "execution-start.json", {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    error = decision = primary = None
    failures = []
    try:
        restoration = {}
        for profile in ["historical", PROFILE]:
            for seed in [42, 43]:
                for case in CASES:
                    run_trial(root, "development", profile, seed, case, budget, restoration)
        from .verify_v12 import verify_panel
        decision = verify_panel(root, "development")
        write_json(root / "development-decision.json", decision)
        if decision["candidate_passed"]:
            validate_freeze(root)
            for seed in [31042, 31043]:
                for case in CASES:
                    run_trial(root, "evaluation", PROFILE, seed, case, budget, restoration)
            run_trial(root, "repeat", PROFILE, 31042, CASES[2], budget, restoration)
            decision = verify_panel(root, "evaluation")
            write_json(root / "evaluation-decision.json", decision)
    except BaseException as exc:
        error = exc
        primary = getattr(exc, "primary_failure", failure_record(exc))
        failures.extend(getattr(exc, "retention_failures", []))
    resources = retention_attempt("execution-resources", budget.report, failures)
    registration_sha = retention_attempt("execution-registration", lambda: file_sha(root / "registration.json"), failures)
    retention_attempt("execution-terminal", lambda: write_json(root / "execution-terminal.json", {
        "outcome": "failed" if error is not None or failures else "completed",
        "error": failure_record(error), "primary_failure": primary, "retention_failures": failures,
        "decision": decision, "resources": resources, "registration_sha256": registration_sha,
    }), failures)
    raise_failure(error, failures)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["register", "run"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "register":
        freeze(args.output)
    else:
        run(args.output)


if __name__ == "__main__":
    main()
