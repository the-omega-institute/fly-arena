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
# Opt-in candidate after a fixed-state full-graph response probe. This is
# an engineering input gain, not a fitted biological receptor model.
TOUCH_RESPONSE_PROFILE = {
    **ENVIRONMENT_PROFILE, "id": "engineered-touch-response-v1",
    "touch": {**ENVIRONMENT_PROFILE["touch"], "gain_mv": 8.0},
    "qualification": "experimental 8 mV tactile current; neural response observed in a fixed-state LIF probe; embodied performance not established",
}
CONTACT_CONTEXT_PROFILE = {
    **TOUCH_RESPONSE_PROFILE, "id": "engineered-contact-context-v1",
    "channels": ["odor_left", "odor_right", "visual_left", "visual_right", "taste", "touch_left", "touch_right"],
    "taste": {"gain_mv": 8.0, "source": "mouth contact with non-depleted food",
              "selector": "class = gustatory; whole annotated population"},
    "touch": {"gain_mv": 8.0, "source": "mujoco_lateral_anatomical_contact_v1",
              "selector": "class = mechanosensory_tactile, annotated side L/R; unknown side excluded",
              "aggregation": "contact points in thorax frame; local Y >0.05 mm left, <-0.05 mm right, center excites both; ground and food probes excluded"},
    "qualification": "experimental separated taste and bilateral tactile currents; frozen odor-trained motor readout has not learned contact responses",
}
SUPPORT_CONTACT_PROFILE = {
    **CONTACT_CONTEXT_PROFILE, "id": "engineered-contact-support-v1",
    "touch": {**CONTACT_CONTEXT_PROFILE["touch"],
              "source": "mujoco_lateral_anatomical_contact_support_v1",
              "aggregation": "Lateral anatomical contacts excluding upward terrain support at tarsal segments below thorax; world-up normal >= sqrt(0.5). Side/underside, non-tarsal and opponent contacts retained; support targets recorded separately."},
    "qualification": "experimental support-aware tactile mapping; no biological calibration or stable behavior claim",
}
SEPARATED_CONTACT_PROFILES = {CONTACT_CONTEXT_PROFILE["id"], SUPPORT_CONTACT_PROFILE["id"]}
PROFILES = {p["id"]: p for p in (PROFILE, ENVIRONMENT_PROFILE, TOUCH_RESPONSE_PROFILE, CONTACT_CONTEXT_PROFILE, SUPPORT_CONTACT_PROFILE)}
ENVIRONMENT_PROFILES = {ENVIRONMENT_PROFILE["id"], TOUCH_RESPONSE_PROFILE["id"], *SEPARATED_CONTACT_PROFILES}


def catalog():
    return [
        {"id": "odor-only-v1", "name": "Bilateral odor only", "ready": True},
        *[{"id": profile["id"], "name": name, "ready": True,
           "ranking_eligible": False, "bridge_profiles": ["legacy-v1"],
           "reason": "Engineered sensory currents; unranked sandbox runs only."}
          for profile, name in ((PROFILE, "Experimental vision + food touch"),
                                (ENVIRONMENT_PROFILE, "Experimental vision + food / obstacle / opponent touch"),
                                (TOUCH_RESPONSE_PROFILE, "Experimental touch response · 8 mV"),
                                (CONTACT_CONTEXT_PROFILE, "Experimental taste + left / right touch"),
                                (SUPPORT_CONTACT_PROFILE, "Experimental taste + lateral touch without foot support"))],
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
        if profile_id in SEPARATED_CONTACT_PROFILES:
            taste = ([i for i, row in enumerate(rows) if row.get("class") == "gustatory"]
                     if hasattr(graph, "path") else graph.groups.get("gustatory", []))
            tactile = self.groups["touch"]
            self.groups.update(taste=np.asarray(taste, dtype=np.int32),
                               touch_left=tactile[side[tactile] == 1],
                               touch_right=tactile[side[tactile] == -1])
        self.manifest = {
            "profile": self.profile,
            "groups": {name: {"count": len(indices),
                               "neuron_ids_sha256": digest(graph.ids[indices].tolist())}
                       for name, indices in self.groups.items()},
        }
        self.sha256 = digest(self.manifest)

    def apply(self, brain, odor_left, odor_right, visual_left=0., visual_right=0., touch=0., *, taste=0., touch_left=0., touch_right=0.):
        separated = self.profile["id"] in SEPARATED_CONTACT_PROFILES
        if separated and touch != 0:
            raise ValueError("Use taste and lateral touch for the separated contact profile")
        if not separated and any(v != 0 for v in (taste, touch_left, touch_right)):
            raise ValueError("Separate contact inputs require the contact context profile")
        values = [odor_left, odor_right, visual_left, visual_right]
        raw = np.asarray(values + ([taste, touch_left, touch_right] if separated else [touch]), dtype=float)
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
        if separated:
            gains.update(taste=self.profile["taste"]["gain_mv"],
                         touch_left=self.profile["touch"]["gain_mv"],
                         touch_right=self.profile["touch"]["gain_mv"])
        for name, value in zip(self.profile["channels"][2:], raw[2:]):
            if value:
                brain.external[self.groups[name]] += gains[name] * value
        return {"profile": self.profile["id"], "values": dict(zip(self.profile["channels"], raw.tolist())),
                "group_manifest_sha256": self.sha256}
