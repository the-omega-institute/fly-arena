"""Experimental ordered FP64 CUDA; hardware qualification is intentionally absent."""
import numpy as np
from numba import cuda, config
from .optional_backend import ARRAYS, CheckedCPUBackend

# Explicit round-to-nearest operations prevent multiply/add contraction on CUDA.
# The simulator executes equivalent separate Python/NumPy operations, not PTX.
if config.ENABLE_CUDASIM:
    def _add(a, b): return a + b
    def _mul(a, b): return a * b
else:
    from numba.cuda import libdevice
    @cuda.jit(device=True, inline=True, fastmath=False)
    def _add(a, b): return libdevice.dadd_rn(a, b)
    @cuda.jit(device=True, inline=True, fastmath=False)
    def _mul(a, b): return libdevice.dmul_rn(a, b)


@cuda.jit(fastmath=False)
def _neurons(v, current, refractory, delay, external, rates, events, counts,
             slot, threshold, syn_decay, mem_decay, rate_decay):
    i = cuda.grid(1)
    if i < v.size:
        events[i] = 0
        rates[i] = _mul(rates[i], rate_decay)
        current[i] = _add(_mul(current[i], syn_decay), delay[slot, i])
        delay[slot, i] = 0.0
        if refractory[i] > 0:
            refractory[i] -= 1
        else:
            v[i] = _add(_add(-52.0, _mul(_add(v[i], 52.0), mem_decay)),
                        _mul(_add(current[i], external[i]), 1.0 - mem_decay))
            if v[i] >= threshold:
                v[i] = -52.0
                current[i] = 0.0
                refractory[i] = 22
                events[i] = 1
                counts[i] += 1
                rates[i] = _add(rates[i], _mul(1.0 - rate_decay, 10000.0))


@cuda.jit(fastmath=False)
def _arrivals(in_ptr, in_pre, in_weights, events, delay, future):
    destination = cuda.grid(1)
    if destination < events.size:
        # Stable destination grouping preserves the CPU's source/edge order.
        value = delay[future, destination]
        for edge in range(in_ptr[destination], in_ptr[destination + 1]):
            if events[in_pre[edge]]:
                value = _add(value, np.float64(in_weights[edge]))
        delay[future, destination] = value


class OrderedCUDABackend(CheckedCPUBackend):
    runtime_id = 'ordered-numba-cuda-v1-unqualified'

    def __init__(self, graph, *, simulator_diagnostic=False, **kwargs):
        if bool(config.ENABLE_CUDASIM) != bool(simulator_diagnostic):
            raise RuntimeError('CUDA simulator requires explicit cuda-simulator-diagnostic selection; real CUDA forbids it')
        if not cuda.is_available():
            raise RuntimeError('CUDA device unavailable; no CPU fallback')
        if simulator_diagnostic and (graph.n > 64 or len(graph.post) > 4096):
            raise ValueError('simulator diagnostic is limited to tiny fixtures')
        super().__init__(graph, **kwargs)
        if simulator_diagnostic:
            self.runtime_id = 'ordered-numba-cuda-simulator-diagnostic-v1'
        g = self.brain.graph
        order = np.argsort(g.post, kind='stable')
        pre = np.repeat(np.arange(g.n, dtype=np.int32), np.diff(g.indptr))
        ptr = np.r_[0, np.cumsum(np.bincount(g.post, minlength=g.n))].astype(np.int64)
        self.stream = cuda.stream()
        self.in_ptr = cuda.to_device(ptr, stream=self.stream)
        self.in_pre = cuda.to_device(pre[order], stream=self.stream)
        self.in_weights = cuda.to_device(self.brain.weights[order], stream=self.stream)
        self.device_state = self._upload(self.brain.checkpoint())
        self.events = cuda.to_device(np.zeros(g.n, dtype=np.int32), stream=self.stream)
        self.syn_decay = np.float64(np.exp(-0.1 / 5.0))
        self.mem_decay = np.float64(np.exp(-0.1 / self.brain.tau))
        self.rate_decay = np.float64(np.exp(-0.1 / 50.0))
        self.stream.synchronize()

    def _upload(self, state):
        result = {name: cuda.to_device(state[name], stream=self.stream) for name in ARRAYS}
        self.stream.synchronize()
        return result

    def _download(self):
        for name, device in self.device_state.items():
            device.copy_to_host(getattr(self.brain, name), stream=self.stream)
        self.stream.synchronize()

    def reset(self, seed=0):
        super().reset(seed)
        self.device_state = self._upload(self.brain.checkpoint())

    def stimulate(self, left, right):
        super().stimulate(left, right)
        self.device_state['external'].copy_to_device(self.brain.external, stream=self.stream)
        self.stream.synchronize()

    def advance(self, steps):
        steps = self._steps(steps)
        n = self.brain.graph.n
        counts = cuda.to_device(np.zeros(n, dtype=np.int32), stream=self.stream)
        blocks = (n + 63) // 64
        d = self.device_state
        for k in range(steps):
            tick = self.brain.tick + k
            _neurons[blocks, 64, self.stream](d['v'], d['current'], d['refractory'], d['delay'], d['external'], d['rates'], self.events, counts,
                np.int64(tick % 19), self.brain.threshold, self.syn_decay, self.mem_decay, self.rate_decay)
            # Same stream launch order provides the whole-grid dependency.
            _arrivals[blocks, 64, self.stream](self.in_ptr, self.in_pre, self.in_weights, self.events, d['delay'], np.int64((tick + 18) % 19))
        result = counts.copy_to_host(stream=self.stream)
        self.stream.synchronize()
        self.brain.tick += steps
        self.brain.total_spikes += int(result.sum(dtype=np.int64))
        self._download()
        if not np.isfinite(self.brain.v).all() or not np.isfinite(self.brain.current).all():
            raise FloatingPointError('Non-finite neural state')
        return result

    def restore(self, checkpoint):
        staged = self._stage(checkpoint)
        devices = self._upload(staged)
        self.brain.restore(staged)
        self.device_state = devices

    def static_device_bytes(self):
        n, e = self.brain.graph.n, len(self.brain.weights)
        # Six state arrays: 23 FP64 vectors + refractory; events + counts;
        # destination pointers; incoming int32 source + FP32 weight per edge.
        return 196 * n + 8 * (n + 1) + 8 * e
