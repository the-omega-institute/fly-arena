"""Executable deterministic CPU port; CUDA is unavailable until device qualification."""
from __future__ import annotations
from typing import Any
import numpy as np
from .neural import Brain
from .research import BackendProfile

V2_IDS = dict(backend_id="cpu-numba", model_id="malecns-lif-cpu-v1",
              embodiment_id="neurofly-mujoco-v1", sensor_id="bilateral-current-v2",
              readout_id="descending-kernel-v2")
CAPABILITIES = frozenset({"stimulate", "advance", "neural_output", "checkpoint", "restore", "metrics"})

class CPUBrainBackend:
    def __init__(self, brain: Brain):
        self.brain = brain
        self.profile = BackendProfile(id="cpu-neural-port-v2", **V2_IDS, ready=True, hashes={}, capabilities=sorted(CAPABILITIES))

    def prepare(self, spec) -> None:
        requested = spec.backend if hasattr(spec, "backend") else spec
        if hasattr(requested, "model_dump"):
            requested = requested.model_dump()
        for key, value in V2_IDS.items():
            if requested.get(key) != value:
                raise ValueError(f"backend profile mismatch: {key}")
        if not set(requested.get("capabilities", ())).issubset(CAPABILITIES):
            raise ValueError("unsupported backend capability")
        if requested.get("schema_version", "backend/v1") != "backend/v1":
            raise ValueError("unsupported backend schema")

    def reset(self, seed: int) -> None:
        # Neural integration is deterministic; seed belongs to the body/scenario.
        self.brain.reset()

    def stimulate(self, left: float, right: float, visual_left: float = 0.0,
                  visual_right: float = 0.0, touch: float = 0.0) -> None:
        values = np.asarray([left, right, visual_left, visual_right, touch], dtype=float)
        if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
            raise ValueError("encoded sensory values must be finite in [0,1]")
        # Versioned wrapper: v1 Brain.stimulate and its tonic current are untouched.
        self.brain.external.fill(0)
        for side, value in zip(("left", "right"), values):
            if side in ("left", "right"):
                self.brain.external[self.brain.graph.groups[f"olfactory_{side}"]] = 48.0 * value
        visual = float((values[2] + values[3]) * .5)
        if visual and len(self.brain.graph.groups.get("visual", [])):
            self.brain.external[self.brain.graph.groups["visual"]] += 12.0 * visual
        if values[4] and len(self.brain.graph.groups.get("local", [])):
            self.brain.external[self.brain.graph.groups["local"]] += 8.0 * values[4]

    def advance(self, steps: int) -> np.ndarray:
        if not isinstance(steps, (int, np.integer)) or steps < 0:
            raise ValueError("steps must be a nonnegative integer")
        return self.brain.advance(int(steps))

    def neural_output(self, neurons=None) -> np.ndarray:
        return self.brain.rates.copy() if neurons is None else self.brain.rates[neurons].copy()

    def checkpoint(self) -> dict[str, Any]:
        return self.brain.checkpoint()

    def restore(self, state: dict[str, Any]) -> None:
        # Validate the complete state before allowing Brain.restore to mutate it.
        template = self.brain.checkpoint()
        if set(state) != set(template):
            raise ValueError("incomplete checkpoint")
        for name, original in template.items():
            value = np.asarray(state[name])
            if value.shape != original.shape or not np.isfinite(value).all():
                raise ValueError(f"invalid checkpoint {name}")
        for name in ("tick", "total_spikes"):
            if int(state[name]) != state[name] or int(state[name]) < 0:
                raise ValueError(f"invalid checkpoint {name}")
        self.brain.restore(state)

    def metrics(self) -> dict[str, float]:
        return self.brain.trace() | {"total_spikes": float(self.brain.total_spikes)}


def backend_catalog() -> list[dict]:
    return [{"id": "cpu-numba", "available": True, "capabilities": sorted(CAPABILITIES)},
            {"id": "cuda", "available": False, "capabilities": [],
             "reason": "No device-qualified CUDA adapter; remote node unavailable."}]
