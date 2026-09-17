"""Prospective native-swing/slow-stance engineering intervention; no admission."""
from copy import deepcopy
import numpy as np
from flygym_demo.complex_terrain.common import LocomotionAction
from flygym_demo.complex_terrain.hybrid_controller import HybridController
from .cadence_v12 import ExcursionHybridController
from .cadence_v10 import SILENCE

PROFILE = 'native-swing-slow-stance-v13'
CONTROL = 'source-native-excursion-v12'
NATIVE = 'literal-native-reference'
STATE_VERSION = 'cadence-controller-state/v13'


def phase_gains(phases, release_end, scale):
    phases = np.asarray(phases, dtype=np.float64)
    release_end = np.asarray(release_end, dtype=np.float64)
    if (phases.shape != (6,) or release_end.shape != (6,) or not np.isfinite(phases).all()
            or not np.isfinite(release_end).all() or np.any(release_end <= 0)
            or np.any(release_end >= 2*np.pi) or not np.isfinite(scale) or not 0 < scale <= 1):
        raise ValueError('invalid native phase/release/scale contract')
    wrapped = phases % (2*np.pi)
    swing = (wrapped > 0) & (wrapped < release_end)
    stance_gain = (2*np.pi-release_end)/(2*np.pi/scale-release_end)
    return np.where(swing, 1.0, stance_gain)


class StanceTimingHybridController(ExcursionHybridController):
    def __post_init__(self):
        super().__post_init__()
        self.release_end = np.array([self.preprogrammed_steps.swing_period[leg][1] + self.swing_extension for leg in self.legs])
        starts = np.array([self.preprogrammed_steps.swing_period[leg][0] for leg in self.legs])
        if (not np.array_equal(starts, np.zeros(6)) or self.swing_extension != np.pi/4
                or not np.array_equal(self._base_intrinsic_freqs, np.full(6, 12.0))
                or not np.array_equal(self.cpg_network.convergence_coefs, np.full(6, 20.0))
                or not np.array_equal(self._base_coupling, (self.cpg_network.phase_biases > 0)*10.0)):
            raise ValueError('installed native controller constants differ from approved source')
        phase_gains(np.zeros(6), self.release_end, 1.0)

    def step(self, descending_signal, obs):
        u = np.asarray(descending_signal, dtype=float)
        if u.shape != (2,) or not np.isfinite(u).all() or np.any(u < 0):
            raise ValueError('v13 requires two finite nonnegative v4 outputs')
        common = float(u.mean())
        asymmetry = float((u[1]-u[0])/(2*common)) if common else 0.0
        if common > .4+1e-12 or abs(asymmetry) > .8+1e-12:
            raise ValueError('outside registered v4 output domain')
        if common > SILENCE:
            gain = phase_gains(self.cpg_network.curr_phases, self.release_end, common/.6)
            self.cpg_network.intrinsic_freqs = self._base_intrinsic_freqs*gain
            self.cpg_network.coupling_weights = self._base_coupling*gain[:, None]
            self.cpg_network.intrinsic_amps = np.repeat([1-asymmetry, 1+asymmetry], 3)
            action = HybridController.step(self, obs)
            self._last_angles = action.joint_angles.copy()
            self._last_adhesion = action.adhesion_onoff.copy()
        return LocomotionAction(self._last_angles.copy(), self._last_adhesion.copy())

    def checkpoint(self):
        return {'version': STATE_VERSION, 'state': deepcopy(self.__dict__)}

    def restore(self, checkpoint):
        if (set(checkpoint) != {'version', 'state'} or checkpoint['version'] != STATE_VERSION
                or set(checkpoint['state']) != set(self.__dict__)):
            raise ValueError('unsupported/incomplete v13 controller checkpoint')
        self.__dict__ = deepcopy(checkpoint['state'])
