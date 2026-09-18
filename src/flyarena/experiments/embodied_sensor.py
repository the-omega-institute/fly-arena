"""Versioned bridge from embodied observations to canonical sensory groups.

The arena already records visual raycasts and MuJoCo food contacts.  This
module is the explicit, opt-in bridge that can turn those observations into
external currents on the retained MaleCNS graph.  It is intentionally marked
experimental: the current gains are engineering parameters and are not a
claim that the biological visual or tactile encoding has been calibrated.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from ..common import digest


PROFILE = {
    "id": "engineered-multimodal-v1",
    "schema": "embodied-sensor/v1",
    "status": "experimental",
    "channels": ["odor_left", "odor_right", "visual_left", "visual_right", "touch"],
    "odor": {"background_mv": 8.0, "gain_mv": 40.0},
    "visual": {"gain_mv": 12.0, "source": "raycast_engineered_observation_v1"},
    "touch": {"gain_mv": 18.0, "source": "mujoco_food_contact_observation_v1"},
    "qualification": "not-biologically-calibrated",
}


def catalog() -> list[dict]:
    return [
        {"id": "odor-only-v1", "name": "Bilateral odor only", "ready": True,
         "qualification": "current calibrated arena baseline"},
        {"id": PROFILE["id"], "name": "Experimental multimodal bridge", "ready": False,
         "reason": "Visual and tactile gains are explicit engineering parameters; biological encoding is not yet qualified.",
         "profile": PROFILE},
    ]


def _value(value: float, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite in [0,1]")
    return result


def _side_split(graph, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split a canonical group by annotated side with a deterministic fallback."""
    indices = np.asarray(indices, dtype=np.int32)
    side = np.asarray(getattr(graph, "side", np.zeros(getattr(graph, "n", 0), dtype=np.int8)))
    left = indices[side[indices] > 0] if len(side) else np.empty(0, dtype=np.int32)
    right = indices[side[indices] < 0] if len(side) else np.empty(0, dtype=np.int32)
    if len(left) and len(right):
        return left, right
    # Fixtures and future imports may not carry side annotations.  Splitting
    # by canonical index keeps the bridge deterministic without inventing a
    # biological laterality claim.
    midpoint = len(indices) // 2
    return indices[:midpoint], indices[midpoint:]


def _group(graph, *names: str) -> np.ndarray:
    for name in names:
        values = graph.groups.get(name)
        if values is not None and len(values):
            return np.asarray(values, dtype=np.int32)
    return np.empty(0, dtype=np.int32)


def sensory_groups(graph) -> dict[str, np.ndarray]:
    """Return the canonical neuron IDs used by the multimodal encoder.

    ``Connectome`` derives the class-labelled mechanosensory groups from the
    official ``neurons.json`` metadata when importing a full artifact.  The
    explicit empty fallback keeps small test graphs and old artifacts honest:
    a missing tactile annotation cannot silently become an all-neuron input.
    """
    odor = _group(graph, "olfactory")
    odor_left = _group(graph, "olfactory_left")
    odor_right = _group(graph, "olfactory_right")
    if not len(odor_left) and not len(odor_right):
        odor_left, odor_right = _side_split(graph, odor)
    visual = _group(graph, "visual")
    visual_left = _group(graph, "visual_left")
    visual_right = _group(graph, "visual_right")
    if not len(visual_left) and not len(visual_right):
        visual_left, visual_right = _side_split(graph, visual)
    tactile = _group(graph, "mechanosensory_tactile", "mechanosensory")
    return {
        "odor_left": odor_left,
        "odor_right": odor_right,
        "visual_left": visual_left,
        "visual_right": visual_right,
        "touch": tactile,
    }


def manifest(graph) -> dict:
    groups = sensory_groups(graph)
    ids = np.asarray(getattr(graph, "ids", np.arange(graph.n)))
    return {
        "profile": PROFILE,
        "groups": {name: {"count": int(len(values)),
                           "neuron_ids_sha256": digest(ids[values].tolist())}
                    for name, values in groups.items()},
    }


def apply(external: np.ndarray, graph, *, odor_left: float, odor_right: float,
          visual_left: float = 0.0, visual_right: float = 0.0,
          touch: float = 0.0, odor_background: float | None = None,
          odor_gain: float | None = None) -> dict:
    """Write one deterministic multimodal current frame into ``external``.

    The returned metadata is stored alongside replay frames.  Visual and
    tactile values only address their declared canonical groups.  If a graph
    has no tactile annotation, nonzero touch fails closed instead of applying
    current to an arbitrary population.
    """
    values = {"odor_left": _value(odor_left, "odor_left"),
              "odor_right": _value(odor_right, "odor_right"),
              "visual_left": _value(visual_left, "visual_left"),
              "visual_right": _value(visual_right, "visual_right"),
              "touch": _value(touch, "touch")}
    groups = sensory_groups(graph)
    if values["touch"] and not len(groups["touch"]):
        raise ValueError("touch input requires an annotated mechanosensory group")
    external.fill(0.0)
    background = PROFILE["odor"]["background_mv"] if odor_background is None else float(odor_background)
    gain = PROFILE["odor"]["gain_mv"] if odor_gain is None else float(odor_gain)
    external[groups["odor_left"]] = background + gain * values["odor_left"]
    external[groups["odor_right"]] = background + gain * values["odor_right"]
    # Sensory populations can overlap in small fixtures or in a future
    # imported annotation.  Add the non-odor channels and skip zero writes so
    # the default multimodal call is exactly the historical odor baseline.
    if values["visual_left"]:
        external[groups["visual_left"]] += PROFILE["visual"]["gain_mv"] * values["visual_left"]
    if values["visual_right"]:
        external[groups["visual_right"]] += PROFILE["visual"]["gain_mv"] * values["visual_right"]
    if values["touch"]:
        external[groups["touch"]] += PROFILE["touch"]["gain_mv"] * values["touch"]
    return {"profile": PROFILE["id"], "values": values,
            "group_counts": {key: int(len(value)) for key, value in groups.items()},
            "group_manifest_sha256": digest(manifest(graph))}


def zero_multimodal(external: np.ndarray, graph, *, odor_left: float, odor_right: float) -> dict:
    """Convenience assertion path used by backend parity tests."""
    return apply(external, graph, odor_left=odor_left, odor_right=odor_right)
