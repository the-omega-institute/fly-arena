"""Opt-in neural contracts; does not change the public backend catalog."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, runtime_checkable

import numpy as np
from .neural import Brain, PROFILE

ARRAYS = ('v', 'current', 'refractory', 'delay', 'external', 'rates')
STATE_KEYS = {*ARRAYS, 'tick', 'total_spikes'}
I64 = np.iinfo(np.int64).max


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def array_identity(a):
    return {'dtype': a.dtype.str, 'shape': list(a.shape), 'sha256': hashlib.sha256(a.tobytes()).hexdigest()}


def integer(value, name, maximum=I64):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be a nonnegative integer <= {maximum}')
    return int(value)


def scalar(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (float, int, np.floating, np.integer)) :
        raise ValueError(f'{name} must be a finite real scalar')
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f'{name} must be a finite real scalar') from exc
    if not np.isfinite(result):
        raise ValueError(f'{name} must be a finite real scalar')
    return result


@dataclass(frozen=True)
class ScientificBinding:
    schema: str
    graph_sha256: str
    weights_sha256: str
    model_sha256: str
    oracle_sha256: str
    tau_ms: float
    threshold_mv: float
    sensor_id: str = 'bilateral-current-v2'

    @property
    def sha256(self):
        return digest(asdict(self))


@runtime_checkable
class NeuralBackend(Protocol):
    binding: ScientificBinding
    def prepare(self, binding: ScientificBinding) -> None: ...
    def reset(self, seed: int) -> None: ...
    def stimulate(self, left: float, right: float) -> None: ...
    def advance(self, steps: int) -> np.ndarray: ...
    def neural_output(self, neurons=None) -> np.ndarray: ...
    def checkpoint(self) -> dict: ...
    def restore(self, checkpoint: dict) -> None: ...
    def metrics(self) -> dict: ...


class CheckedCPUBackend:
    runtime_id = 'checked-cpu-numba-v1'

    def __init__(self, graph, weights=None, tau_scale=1.0, threshold_shift=0.0):
        n = integer(graph.n, 'neuron count', np.iinfo(np.int32).max)
        if n == 0:
            raise ValueError('empty graph')
        tau = 20.0 * scalar(tau_scale, 'tau_scale')
        threshold = -45.0 + scalar(threshold_shift, 'threshold_shift')
        if not np.isfinite(tau) or tau <= 0 or not np.isfinite(threshold):
            raise ValueError('invalid intrinsic parameters')
        indptr, post = np.asarray(graph.indptr), np.asarray(graph.post)
        weights = np.asarray(graph.baseline_weights() if weights is None else weights)
        if indptr.dtype != np.int64 or indptr.shape != (n + 1,) or indptr[0] != 0 or np.any(indptr[1:] < indptr[:-1]):
            raise ValueError('invalid canonical CSR indptr')
        if post.dtype != np.int32 or post.ndim != 1 or indptr[-1] != len(post) or np.any(post < 0) or np.any(post >= n):
            raise ValueError('invalid canonical CSR destinations')
        if weights.dtype != np.float32 or weights.shape != post.shape or not np.isfinite(weights).all():
            raise ValueError('weights must be finite compiled FP32')
        groups = {}
        for key, raw in graph.groups.items():
            value = np.asarray(raw)
            if value.ndim != 1 or value.dtype.kind not in 'iu' or np.any(value < 0) or np.any(value >= n):
                raise ValueError(f'invalid group {key}')
            groups[key] = value.copy()
        if not {'olfactory_left', 'olfactory_right'} <= groups.keys():
            raise ValueError('missing sensory groups')
        ids = np.asarray(getattr(graph, 'ids', np.arange(n, dtype=np.int64)))
        if ids.shape != (n,) or ids.dtype.kind not in 'iu' or len(np.unique(ids)) != n:
            raise ValueError('invalid canonical neuron IDs')
        graph_identity = {'n': n, 'ids': array_identity(ids), 'indptr': array_identity(indptr),
                          'post': array_identity(post), 'groups': {k: array_identity(v) for k,v in groups.items()}}
        self.binding = ScientificBinding('neural-binding/v1', digest(graph_identity),
            array_identity(weights)['sha256'], digest(PROFILE),
            hashlib.sha256(Path(__file__).with_name('neural.py').read_bytes()).hexdigest(), tau, threshold)
        copied = SimpleNamespace(n=n, indptr=indptr.copy(), post=post.copy(), groups=groups)
        owned_weights = weights.copy()
        for a in [copied.indptr, copied.post, owned_weights, *groups.values()]:
            a.flags.writeable = False
        self.brain = Brain(copied, owned_weights, tau_scale=float(tau_scale), threshold_shift=float(threshold_shift))

    def prepare(self, binding):
        if not isinstance(binding, ScientificBinding) or binding != self.binding:
            raise ValueError('scientific binding mismatch')

    def reset(self, seed=0):
        integer(seed, 'seed')
        self.brain.reset()

    def stimulate(self, left, right):
        values = [scalar(left, 'left'), scalar(right, 'right')]
        if any(not 0 <= v <= 1 for v in values):
            raise ValueError('stimulus outside [0,1]')
        self.brain.external.fill(0)
        for side, value in zip(('left', 'right'), values):
            self.brain.external[self.brain.graph.groups['olfactory_' + side]] = 48.0 * value

    def _steps(self, steps):
        steps = integer(steps, 'steps', np.iinfo(np.int32).max)
        if self.brain.tick > I64 - steps or self.brain.total_spikes > I64 - self.brain.graph.n * steps:
            raise ValueError('counter overflow')
        # The last iteration also evaluates tick + (steps - 1) + 18 in
        # signed int64 inside the unchanged CPU oracle. Zero steps is a no-op.
        if steps and self.brain.tick > I64 - (steps - 1) - 18:
            raise ValueError('delay-offset overflow')
        return steps

    def advance(self, steps):
        return self.brain.advance(self._steps(steps))

    def neural_output(self, neurons=None):
        if neurons is None:
            return self.brain.rates.copy()
        indices = np.asarray(neurons)
        if indices.ndim != 1 or indices.dtype.kind not in 'iu' or np.any(indices < 0) or np.any(indices >= self.brain.graph.n):
            raise ValueError('neurons must be a vector of valid integer indices')
        return self.brain.rates[indices].copy()

    def checkpoint(self):
        return {'schema': 'neural-checkpoint/v1', 'binding': asdict(self.binding),
                'state': self.brain.checkpoint()}

    def _stage(self, checkpoint):
        if not isinstance(checkpoint, dict) or set(checkpoint) != {'schema', 'binding', 'state'} or checkpoint['schema'] != 'neural-checkpoint/v1' or checkpoint['binding'] != asdict(self.binding):
            raise ValueError('checkpoint binding/schema mismatch')
        state = checkpoint['state']
        if not isinstance(state, dict) or set(state) != STATE_KEYS:
            raise ValueError('checkpoint requires exactly eight arrays')
        staged = {}
        for name, expected in self.brain.checkpoint().items():
            value = state[name]
            if not isinstance(value, np.ndarray) or value.dtype != expected.dtype or value.shape != expected.shape or not np.isfinite(value).all():
                raise ValueError(f'invalid checkpoint {name}')
            staged[name] = value.copy()
        if np.any(staged['refractory'] < 0) or np.any(staged['refractory'] > 22) or np.any(staged['rates'] < 0):
            raise ValueError('invalid refractory/rate state')
        for name in ('tick', 'total_spikes'):
            integer(staged[name].item(), name)
        return staged

    def restore(self, checkpoint):
        staged = self._stage(checkpoint)
        self.brain.restore(staged)

    def metrics(self):
        return {'tick': self.brain.tick, 'total_spikes': self.brain.total_spikes,
                'runtime_id': self.runtime_id, 'qualified': False}


def create_backend(kind, graph, **kwargs):
    if kind == 'cpu':
        return CheckedCPUBackend(graph, **kwargs)
    if kind not in ('cuda', 'cuda-simulator-diagnostic'):
        raise ValueError('unknown optional backend')
    from .cuda_ordered import OrderedCUDABackend
    return OrderedCUDABackend(graph, simulator_diagnostic=kind == 'cuda-simulator-diagnostic', **kwargs)
