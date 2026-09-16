"""Frozen, research-only contact + chemical input and rate-only tibia authority."""
from types import MappingProxyType
import numpy as np
from .contact_v6 import LEGS
from .sensor import encode_odor

RMAX = (1-np.exp(-.1/50))*10000/(1-np.exp(-.1/50)**23)

class EmbodiedBridge:
    def __init__(self, backend, groups):
        self.backend = backend
        n = backend.brain.graph.n
        keys = [f'{a}_{l}' for a in ('afferent','flexor','extensor') for l in LEGS]
        raw = {k: groups[k] for k in keys}
        raw.update({f'olfactory_{s}': backend.brain.graph.groups[f'olfactory_{s}'] for s in ('left','right')})
        checked = {}
        for k, v in raw.items():
            v = np.asarray(v)
            if v.ndim != 1 or v.dtype.kind not in 'iu' or not len(v) or np.any(v < 0) or np.any(v >= n):
                raise ValueError('invalid group '+k)
            v = v.copy(); v.flags.writeable = False; checked[k] = v
        flat = np.concatenate(list(checked.values()))
        if len(np.unique(flat)) != len(flat): raise ValueError('overlapping groups')
        self.groups = MappingProxyType(checked)
        self.held_command = np.zeros(6)

    def stimulate(self, ratios, odor=(0.,0.), tactile_clamp=False):
        ratios = np.asarray(ratios, dtype=float)
        odor = np.asarray(odor, dtype=float)
        if ratios.shape != (6,) or odor.shape != (2,) or not np.isfinite(ratios).all() or np.any(ratios < 0):
            raise ValueError('invalid sensory input')
        encoded = encode_odor(*odor)
        external = np.zeros_like(self.backend.brain.external)
        for l, value in zip(LEGS, ratios):
            external[self.groups['afferent_'+l]] = 0 if tactile_clamp else 48*min(value,1.)
        for s, value in zip(('left','right'), encoded): external[self.groups['olfactory_'+s]] = 48*value
        self.backend.brain.external[:] = external
        return encoded

    def readout(self, motor_clamp=False):
        rates = self.backend.neural_output()
        if not np.isfinite(rates).all() or np.any(rates < 0) or np.any(rates > RMAX+1e-9):
            raise ValueError('individual rate outside exact model ceiling')
        pools = np.array([[rates[self.groups[a+'_'+l]].mean() for a in ('flexor','extensor')] for l in LEGS])
        command = .1*(pools[:,0]-pools[:,1])/RMAX
        self.held_command = np.zeros(6) if motor_clamp else command
        return pools, self.held_command.copy()

    def checkpoint(self):
        return self.backend.checkpoint() | {'held_command': self.held_command.copy()}

    def restore(self, state):
        template = self.checkpoint()
        if set(state) != set(template): raise ValueError('checkpoint fields')
        for k, v in template.items():
            a = np.asarray(state[k])
            if a.shape != v.shape or a.dtype != v.dtype or not np.isfinite(a).all(): raise ValueError('checkpoint '+k)
        if (np.any(state['refractory'] < 0) or np.any(state['refractory'] > 22)
            or np.any(state['rates'] < 0) or np.any(state['rates'] > RMAX+1e-9)
            or np.any(state['external'] < 0) or np.any(state['external'] > 48)
            or state['tick'] < 0 or state['total_spikes'] < 0 or np.max(np.abs(state['held_command'])) > .1):
            raise ValueError('checkpoint range')
        self.backend.restore({k:v for k,v in state.items() if k != 'held_command'})
        self.held_command[:] = state['held_command']
