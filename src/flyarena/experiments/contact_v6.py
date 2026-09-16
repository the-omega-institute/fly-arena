"""Research-only annotated contact → Ti antagonist bridge; no runtime admission.

The local contact encoder is a lumped engineering hypothesis, not identified
segment-specific bristle physiology. Graph, signs, LIF and old bridges are intact.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pyarrow.feather as feather

LEGS = ("LF", "LM", "LH", "RF", "RM", "RH")
NERVES = {"F": "ProLN", "M": "MesoLN", "H": "MetaLN"}
NEUROMERES = {"F": "T1", "M": "T2", "H": "T3"}
PROFILE = {
    "schema": "annotated-contact-tibia/v6", "legs": list(LEGS),
    "input": "sum of tibia/tarsus1/tarsus2 net-contact-force norms / body weight",
    "current_mv": 48.0, "odor_current_mv": 0.0,
    "sensor_selector": "Traced, class=mechanosensory_tactile, entryNerve, rootSide",
    "motor_selector": "Traced, superclass=vnc_motor, exact Ti flexor/extensor MN type, somaSide, somaNeuromere, exitNerve",
    "rate_pool": "arithmetic mean of all neurons in each antagonist group",
    "command": "0.10 * clip((mean flexor Hz - mean extensor Hz)/100, -1, 1)",
    "command_frame": "positive flexion intent; physical joint coordinate sign not yet registered",
    "max_rad": 0.10, "rate_scale_hz": 100.0,
    "cpg": False, "hybrid_reflex": False, "production_admitted": False,
}
PROTOCOL = {
    "schema": "contact-neural-assay/v6", "profile": PROFILE,
    "runs": ["blank", *LEGS, "LF-repeat"], "repeat_of": "LF",
    "dt_seconds": 0.0001, "sample_steps": 100, "samples": 60,
    "pulse_start_tick": 2000, "pulse_end_tick": 4000, "end_tick": 6000,
    "pulse_force_over_weight": 1.0, "initial": "identical complete zero-input Brain rest state and zero held command",
    "checkpoints_ticks": [0, 2000, 4000, 6000],
    "gate": {"minimum_increment_rad_exclusive": 0.001, "consecutive_samples": 5,
             "window": "pulse-endpoint samples 0.21 through 0.40 seconds",
             "decay_final_fraction_inclusive": 0.2,
             "saturation": "reject any abs(unclipped rate difference/100) >= 1 in any run or channel",
             "bilateral_body_requires": ["LF", "RF"],
             "repeat": "bitwise arrays and complete checkpoints; wall time excluded"},
    "body": "conditional, NOT RUN unless neural prerequisite passes",
    "design_panel": "conditional on body qualification, NOT RUN",
}


def bind_annotations(graph, path: Path):
    """Return deterministic graph indices and raw annotation records, fail closed."""
    rows = feather.read_table(path).to_pylist()
    traced = {r["bodyId"]: r for r in rows if r["status"] == "Traced"}
    if len(traced) != graph.n or set(traced) != set(map(int, graph.ids)):
        raise ValueError("Raw annotations and retained graph IDs differ")
    aligned = [traced[int(i)] for i in graph.ids]
    groups = {}
    for leg in LEGS:
        side, segment = leg
        groups[f"afferent_{leg}"] = np.array([
            i for i, r in enumerate(aligned)
            if r.get("class") == "mechanosensory_tactile"
            and r.get("entryNerve") == NERVES[segment] and r.get("rootSide") == side
        ], dtype=np.int32)
        for antagonist in ("flexor", "extensor"):
            groups[f"{antagonist}_{leg}"] = np.array([
                i for i, r in enumerate(aligned)
                if r.get("superclass") == "vnc_motor"
                and r.get("type") == f"Ti {antagonist} MN"
                and r.get("somaSide") == side
                and r.get("somaNeuromere") == NEUROMERES[segment]
                and r.get("exitNerve") == NERVES[segment]
            ], dtype=np.int32)
    if any(len(g) == 0 for g in groups.values()):
        raise ValueError("Empty annotated contact or motor group")
    flat = np.concatenate(list(groups.values()))
    if len(np.unique(flat)) != len(flat):
        raise ValueError("Overlapping input or antagonist groups")
    # Observe every structural two-hop VNC interneuron, without sign/weight search.
    aff = np.concatenate([groups[f"afferent_{l}"] for l in LEGS])
    mn = np.concatenate([groups[f"{a}_{l}"] for l in LEGS for a in ("flexor", "extensor")])
    successors = np.unique(np.concatenate([graph.post[graph.indptr[i]:graph.indptr[i+1]] for i in aff]))
    predecessors = np.unique(graph.pre[np.isin(graph.post, mn)])
    intermediate = np.intersect1d(successors, predecessors)
    groups["intermediary"] = np.array([i for i in intermediate if aligned[i].get("superclass") == "vnc_intrinsic"], dtype=np.int32)
    groups["descending"] = graph.groups["descending"].copy()
    selected = np.unique(np.concatenate(list(groups.values())))
    fields = ("bodyId", "status", "class", "superclass", "type", "entryNerve", "exitNerve", "rootSide", "somaSide", "somaNeuromere")
    records = [{k: aligned[i].get(k) for k in fields} | {"graph_index": int(i)} for i in selected]
    return groups, records


def contact_ratios(segment_net_forces, body_weight: float) -> np.ndarray:
    forces = np.asarray(segment_net_forces, dtype=float)
    if forces.shape != (6, 3, 3) or not np.isfinite(forces).all():
        raise ValueError("Expected six legs by three segment world force vectors")
    if not np.isfinite(body_weight) or body_weight <= 0:
        raise ValueError("Body weight must be positive in the same native force units")
    return np.linalg.norm(forces, axis=2).sum(axis=1) / body_weight


def observe_flygym_contact(sim, fly_name: str) -> np.ndarray:
    """Read actual FlyGym 2.1 net forces, including obstacle contacts.

    MuJoCo contact forces and mass*norm(gravity) share native M*L/T² units.
    Only the named fly's bodies contribute mass; no mm→m conversion is applied.
    This adapter does not step physics or supply motor commands.
    """
    import mujoco as mj
    names = [f"{leg.lower()}_{segment}" for leg in LEGS for segment in ("tibia", "tarsus1", "tarsus2")]
    forces = sim.get_bodysegment_contact_forces(fly_name, names, ground_only=False)
    model = sim.mj_model
    body_ids = [i for i in range(model.nbody)
                if (mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, i) or "").startswith(fly_name + "/")]
    if not body_ids:
        raise ValueError("Named fly has no compiled bodies")
    weight = float(model.body_mass[body_ids].sum() * np.linalg.norm(model.opt.gravity))
    return contact_ratios(forces.reshape(6, 3, 3), weight)


class ContactTibiaBridge:
    def __init__(self, backend, groups):
        self.backend, self.groups = backend, groups
        self.held_command = np.zeros(6)

    def stimulate(self, force_over_weight):
        values = np.asarray(force_over_weight, dtype=float)
        if values.shape != (6,) or not np.isfinite(values).all() or np.any(values < 0):
            raise ValueError("Expected six finite nonnegative contact ratios")
        # Clearing the complete array guarantees chemical and all other inputs OFF.
        self.backend.brain.external.fill(0)
        currents = PROFILE["current_mv"] * np.clip(values, 0, 1)
        for leg, current in zip(LEGS, currents):
            self.backend.brain.external[self.groups[f"afferent_{leg}"]] = current
        return currents

    def readout(self):
        rates = self.backend.neural_output()
        pools = np.array([[rates[self.groups[f"{a}_{l}"]].mean()
                           for a in ("flexor", "extensor")] for l in LEGS])
        if not np.isfinite(pools).all() or np.any(pools < 0):
            raise ValueError("Invalid neural motor rates")
        raw = (pools[:, 0] - pools[:, 1]) / PROFILE["rate_scale_hz"]
        self.held_command = PROFILE["max_rad"] * np.clip(raw, -1, 1)
        return pools, raw, self.held_command.copy()

    def checkpoint(self):
        return self.backend.checkpoint() | {"held_command": self.held_command.copy()}

    def restore(self, state):
        held = np.asarray(state["held_command"])
        if held.shape != (6,) or not np.isfinite(held).all() or np.any(np.abs(held) > PROFILE["max_rad"]):
            raise ValueError("Invalid held joint command")
        self.backend.restore({k: v for k, v in state.items() if k != "held_command"})
        self.held_command[:] = held
