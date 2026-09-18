"""Independent sparse LIF implementation from the documented model equations.

Units: ms and mV. Anatomical topology is never rewired. All neurons retain
membrane, synaptic, refractory, and delayed-event state across advance calls.
Numba compiles the numerical loop to native CPU code; there is no Python edge loop.
"""
from __future__ import annotations

import numpy as np
from numba import njit

from .connectome import Connectome

PROFILE = {
    "id": "malecns-lif-cpu-v1", "dt_ms": 0.1, "tau_mem_ms": 20.0,
    "tau_syn_ms": 5.0, "rest_mv": -52.0, "reset_mv": -52.0,
    "threshold_mv": -45.0, "refractory_ms": 2.2, "delay_ms": 1.8,
    "base_weight_mv": 0.275, "integration": "exponential-Euler, delayed current pulses; synaptic current reset on spike",
    "scope": "Full retained MaleCNS graph; simplified current-based LIF, engineered sensory/motor bridge",
}


@njit(cache=True)
def _advance(indptr, post, weights, v, current, refractory, delay, external, rates,
             tau, threshold, tick, steps, counts):
    n = len(v)
    syn_decay = np.exp(-0.1 / 5.0)
    mem_decay = np.exp(-0.1 / tau)
    rate_decay = np.exp(-0.1 / 50.0)
    spike_ids = np.empty(n, dtype=np.int32)
    for k in range(steps):
        slot = (tick + k) % 19
        future = (tick + k + 18) % 19
        ns = 0
        for i in range(n):
            rates[i] *= rate_decay
            current[i] = current[i] * syn_decay + delay[slot, i]
            delay[slot, i] = 0.0
            if refractory[i] > 0:
                refractory[i] -= 1
                continue
            v[i] = -52.0 + (v[i] + 52.0) * mem_decay + (current[i] + external[i]) * (1.0 - mem_decay)
            if v[i] >= threshold:
                v[i] = -52.0
                current[i] = 0.0
                refractory[i] = 22
                spike_ids[ns] = i
                ns += 1
                counts[i] += 1
                rates[i] += (1.0 - rate_decay) * 10000.0
        for s in range(ns):
            i = spike_ids[s]
            for edge in range(indptr[i], indptr[i + 1]):
                delay[future, post[edge]] += weights[edge]
    return tick + steps


class Brain:
    def __init__(self, graph: Connectome, weights: np.ndarray | None = None,
                 tau_scale: float = 1.0, threshold_shift: float = 0.0):
        self.graph = graph
        self.weights = graph.baseline_weights() if weights is None else weights
        self.tau = 20.0 * tau_scale
        self.threshold = -45.0 + threshold_shift
        self.reset()

    def reset(self):
        n = self.graph.n
        self.v = np.full(n, -52.0, dtype=np.float64)
        self.current = np.zeros(n, dtype=np.float64)
        self.refractory = np.zeros(n, dtype=np.int32)
        self.delay = np.zeros((19, n), dtype=np.float64)
        self.external = np.zeros(n, dtype=np.float64)
        self.rates = np.zeros(n, dtype=np.float64)
        self.total_spikes = 0
        self.tick = 0

    def stimulate(self, left: float, right: float, visual_left: float = 0.0,
                  visual_right: float = 0.0, touch: float = 0.0):
        self.external.fill(0)
        # A bilateral odor-current encoder into anatomically annotated ORNs.
        # The constant background is a declared sensory baseline, not a motor action.
        for side, concentration in [("left", left), ("right", right)]:
            self.external[self.graph.groups[f"olfactory_{side}"]] = 8.0 + 40.0 * np.clip(concentration, 0, 1)
        visual = float(np.clip((visual_left + visual_right) * .5, 0, 1))
        if visual and len(self.graph.groups.get("visual", [])):
            self.external[self.graph.groups["visual"]] += 12.0 * visual
        if touch and len(self.graph.groups.get("local", [])):
            self.external[self.graph.groups["local"]] += 8.0 * np.clip(touch, 0, 1)

    def advance(self, steps: int = 100) -> np.ndarray:
        counts = np.zeros(self.graph.n, dtype=np.int32)
        self.tick = _advance(self.graph.indptr, self.graph.post, self.weights,
                             self.v, self.current, self.refractory, self.delay, self.external, self.rates,
                             self.tau, self.threshold, self.tick, steps, counts)
        self.total_spikes += int(counts.sum())
        if not np.isfinite(self.v).all() or not np.isfinite(self.current).all():
            raise FloatingPointError("Non-finite neural state")
        return counts

    def trace(self) -> dict:
        return {key: float(self.rates[self.graph.groups[key]].mean()) if len(self.graph.groups[key]) else 0.0
                for key in ["olfactory", "projection", "local", "memory", "readout", "descending", "visual", "motor"]}

    def checkpoint(self) -> dict[str, np.ndarray]:
        return {**{name: getattr(self, name).copy() for name in
                  ["v", "current", "refractory", "delay", "external", "rates"]},
                "tick": np.array(self.tick), "total_spikes": np.array(self.total_spikes)}

    def restore(self, state: dict[str, np.ndarray]):
        for name in ["v", "current", "refractory", "delay", "external", "rates"]:
            if state[name].shape != getattr(self, name).shape or not np.isfinite(state[name]).all():
                raise ValueError(f"Invalid checkpoint {name}")
            getattr(self, name)[:] = state[name]
        self.tick, self.total_spikes = int(state["tick"]), int(state["total_spikes"])
