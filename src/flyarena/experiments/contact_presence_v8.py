"""Single registered engineering contact switch; no physical-to-motor shortcut."""
import numpy as np
from .embodied_v7 import EmbodiedBridge
from .contact_v6 import LEGS
from .sensor import encode_odor

RMAX = 444.41470981063657

class ContactPresenceBridge(EmbodiedBridge):
    def stimulate(self, ratios, odor=(0., 0.), tactile_clamp=False):
        ratios = np.asarray(ratios, dtype=float)
        odor = np.asarray(odor, dtype=float)
        if ratios.shape != (6,) or odor.shape != (2,) or not np.isfinite(ratios).all() or np.any(ratios < 0):
            raise ValueError('invalid sensory input')
        encoded = encode_odor(*odor)
        external = np.zeros_like(self.backend.brain.external)
        for leg, value in zip(LEGS, ratios):
            external[self.groups['afferent_'+leg]] = 48. if value > 0 and not tactile_clamp else 0.
        for side, value in zip(('left','right'), encoded):
            external[self.groups['olfactory_'+side]] = 48.*value
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
