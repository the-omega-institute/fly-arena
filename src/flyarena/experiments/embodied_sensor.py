"""Opt-in engineered currents; group selection is prepared once per simulation.

Visual projection neurons receive direct current (no retina model). Feeding
contact drives the annotated tactile population (no receptor-specific model).
Neither mapping is a claim of biological calibration.
"""
from __future__ import annotations

import json
import numpy as np
from ..common import digest, file_sha

PROFILE = {
    "id": "engineered-multimodal-v1", "schema": "embodied-sensor/v1",
    "status": "experimental", "ranking_eligible": False,
    "channels": ["odor_left", "odor_right", "visual_left", "visual_right", "touch"],
    "odor": {"background_mv": 8.0, "gain_mv": 40.0},
    # These are deliberately small engineering currents.  The retained graph
    # and the frozen odor-to-motor readout were calibrated without visual or
    # tactile input; a large direct current overwhelms that bridge.  The gains
    # are versioned here so the receipt records the actual experiment, not a
    # hidden runtime knob.  They are not biological calibration constants.
    "visual": {"gain_mv": 0.1, "source": "raycast_engineered_observation_v1",
               "selector": "visual_projection, annotated side L/R; unknown side excluded"},
    "touch": {"gain_mv": 0.1, "source": "mujoco_food_contact_observation_v1",
              "selector": "class = mechanosensory_tactile; whole population"},
    "qualification": "engineered currents; no biological sensory validation",
}


ENVIRONMENT_PROFILE = {
    **PROFILE, "id": "engineered-multimodal-v2",
    "touch": {**PROFILE["touch"],
              "source": "mujoco_food_and_environment_contact_v2",
              "aggregation": "binary OR of mouth-food, anatomical obstacle and opponent contact; ground support excluded"},
}
PROFILES = {p["id"]: p for p in (PROFILE, ENVIRONMENT_PROFILE)}


def catalog():
    return [
        {"id": "odor-only-v1", "name": "Bilateral odor only", "ready": True},
        *[{"id": profile["id"], "name": name, "ready": True,
           "ranking_eligible": False, "bridge_profiles": ["legacy-v1"],
           "reason": "Engineered sensory currents; unranked sandbox runs only."}
          for profile, name in ((PROFILE, "Experimental vision + food touch"),
                                (ENVIRONMENT_PROFILE, "Experimental vision + food / obstacle / opponent touch"))],
    ]


def validate_profile(bridge_profile, sensory_profile):
    if sensory_profile not in ("odor-only-v1", *PROFILES):
        raise ValueError("Unknown sensory profile")
    if sensory_profile in PROFILES and bridge_profile != "legacy-v1":
        raise ValueError("Experimental sensory input currently supports legacy-v1 only")


class EmbodiedSensor:
    def __init__(self, graph, profile_id=PROFILE["id"]):
        self.profile = PROFILES[profile_id]
        self.groups = {"odor_" + side: np.asarray(graph.groups["olfactory_" + side], dtype=np.int32)
                       for side in ("left", "right")}
        visual = np.asarray(graph.groups.get("visual", []), dtype=np.int32)
        # Never infer anatomical laterality from array order.
        side = np.asarray(graph.side)
        self.groups.update(visual_left=visual[side[visual] == 1],
                           visual_right=visual[side[visual] == -1])
        if hasattr(graph, "path"):
            path = graph.path / "neurons.json"
            expected = graph.manifest["files"].get("neurons.json")
            if not expected or file_sha(path) != expected:
                raise ValueError("Sensory neuron annotation digest mismatch")
            rows = json.loads(path.read_text())
            if len(rows) != graph.n or any(str(row["id"]) != str(ident)
                                          for row, ident in zip(rows, graph.ids)):
                raise ValueError("Sensory annotations do not match canonical neuron IDs")
            tactile = [i for i, row in enumerate(rows) if row.get("class") == "mechanosensory_tactile"]
        else:
            # Explicit groups support deliberately small unit-test fixtures.
            tactile = graph.groups.get("mechanosensory_tactile", [])
        self.groups["touch"] = np.asarray(tactile, dtype=np.int32)
        self.manifest = {
            "profile": self.profile,
            "groups": {name: {"count": len(indices),
                               "neuron_ids_sha256": digest(graph.ids[indices].tolist())}
                       for name, indices in self.groups.items()},
        }
        self.sha256 = digest(self.manifest)

    def apply(self, brain, odor_left, odor_right, visual_left=0., visual_right=0., touch=0.):
        raw = np.asarray([odor_left, odor_right, visual_left, visual_right, touch], dtype=float)
        if not np.isfinite(raw).all() or np.any(raw < 0) or np.any(raw > 1):
            raise ValueError("Sensory values must be finite in [0,1]")
        for name, value in zip(self.profile["channels"], raw):
            if value and not len(self.groups[name]):
                raise ValueError(f"{name} requires an annotated sensory group")
        # Reuse the unchanged odor encoder; zero extra inputs exactly preserve
        # its current, including on fixtures with overlapping circuit labels.
        brain.stimulate(float(odor_left), float(odor_right))
        gains = {"visual_left": self.profile["visual"]["gain_mv"],
                 "visual_right": self.profile["visual"]["gain_mv"],
                 "touch": self.profile["touch"]["gain_mv"]}
        for name, value in (("visual_left", visual_left),
                            ("visual_right", visual_right), ("touch", touch)):
            if value:
                brain.external[self.groups[name]] += gains[name] * value
        return {"profile": self.profile["id"], "values": dict(zip(self.profile["channels"], raw.tolist())),
                "group_manifest_sha256": self.sha256}
