"""Single source-native excursion candidate for the prospective v12 trial."""
from __future__ import annotations

from copy import deepcopy
import numpy as np
from flygym_demo.complex_terrain.common import LocomotionAction
from flygym_demo.complex_terrain.hybrid_controller import HybridController
from .cadence_v10 import CadenceHybridController, SILENCE

PROFILE = "source-native-excursion-v12"
STATE_VERSION = "cadence-controller-state/v12"
PHASE_NOMINAL = 0.6
TARGET_NOMINAL = 1.0


class ExcursionHybridController(CadenceHybridController):
    """V10 cadence law with only its nominal active trajectory scalar changed."""

    def step(self, descending_signal, obs):
        u = np.asarray(descending_signal, dtype=float)
        if u.shape != (2,) or not np.isfinite(u).all() or np.any(u < 0):
            raise ValueError("v12 requires two finite nonnegative v4 outputs")
        c = float(u.mean())
        a = float((u[1] - u[0]) / (2 * c)) if c > 0 else 0.0
        if c > 0.4 + 1e-12 or abs(a) > 0.8 + 1e-12:
            raise ValueError("outside registered v4 output domain")
        if c > SILENCE:
            scale = c / PHASE_NOMINAL
            self.cpg_network.intrinsic_freqs = self._base_intrinsic_freqs * scale
            self.cpg_network.coupling_weights = self._base_coupling * scale
            self.cpg_network.intrinsic_amps = np.repeat(
                TARGET_NOMINAL * np.array([1 - a, 1 + a]), 3
            )
            action = HybridController.step(self, obs)
            self._last_angles = action.joint_angles.copy()
            self._last_adhesion = action.adhesion_onoff.copy()
        return LocomotionAction(self._last_angles.copy(), self._last_adhesion.copy())

    def checkpoint(self):
        return {"version": STATE_VERSION, "state": deepcopy(self.__dict__)}

    def restore(self, checkpoint):
        if set(checkpoint) != {"version", "state"} or checkpoint["version"] != STATE_VERSION:
            raise ValueError("unsupported v12 controller checkpoint")
        if set(checkpoint["state"]) != set(self.__dict__):
            raise ValueError("incomplete v12 controller checkpoint")
        self.__dict__ = deepcopy(checkpoint["state"])
