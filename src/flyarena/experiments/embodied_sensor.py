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
    "visual": {"gain_mv": 12.0, "source": "raycast_engineered_observation_v1",
               "selector": "visual_projection, annotated side L/R; unknown side excluded"},
    "touch": {"gain_mv": 18.0, "source": "mujoco_food_contact_observation_v1",
              "selector": "class = mechanosensory_tactile; whole population"},
    "qualification": "engineered currents; no biological sensory validation",
}


def catalog():
    return [
        {"id": "odor-only-v1", "name": "Bilateral odor only", "ready": True},
        {"id": PROFILE["id"], "name": "Experimental vision + touch", "ready": True,
         "ranking_eligible": False, "bridge_profiles": ["legacy-v1"],
         "reason": "Engineered sensory currents; unranked sandbox runs only."},
    ]


def validate_profile(bridge_profile, sensory_profile):
    if sensory_profile not in ("odor-only-v1", PROFILE["id"]):
        raise ValueError("Unknown sensory profile")
    if sensory_profile == PROFILE["id"] and bridge_profile != "legacy-v1":
        raise ValueError("Experimental sensory input currently supports legacy-v1 only")


class EmbodiedSensor:
    def __init__(self, graph):
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
            "profile": PROFILE,
            "groups": {name: {"count": len(indices),
                               "neuron_ids_sha256": digest(graph.ids[indices].tolist())}
                       for name, indices in self.groups.items()},
        }
        self.sha256 = digest(self.manifest)

    def apply(self, brain, odor_left, odor_right, visual_left=0., visual_right=0., touch=0.):
        raw = np.asarray([odor_left, odor_right, visual_left, visual_right, touch], dtype=float)
        if not np.isfinite(raw).all() or np.any(raw < 0) or np.any(raw > 1):
            raise ValueError("Sensory values must be finite in [0,1]")
        for name, value in zip(PROFILE["channels"], raw):
            if value and not len(self.groups[name]):
                raise ValueError(f"{name} requires an annotated sensory group")
        # Reuse the unchanged odor encoder; zero extra inputs exactly preserve
        # its current, including on fixtures with overlapping circuit labels.
        brain.stimulate(float(odor_left), float(odor_right))
        for name, value, gain in (("visual_left", visual_left, 12.),
                                  ("visual_right", visual_right, 12.), ("touch", touch, 18.)):
            if value:
                brain.external[self.groups[name]] += gain * value
        return {"profile": PROFILE["id"], "values": dict(zip(PROFILE["channels"], raw.tolist())),
                "group_manifest_sha256": self.sha256}
