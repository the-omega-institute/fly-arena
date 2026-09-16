"""Prospective cadence-normalized-hybrid-v10; not a production admission profile.

Only the CPG phase derivative changes. The installed hybrid reflex and compatible
NeuroMechFly step asset remain authoritative, including the single right-axis
conversion performed by PreprogrammedSteps. No world/target input is introduced.
"""
from __future__ import annotations

from copy import deepcopy
import numpy as np
from flygym_demo.complex_terrain.common import LocomotionAction
from flygym_demo.complex_terrain.hybrid_controller import HybridController
from flygym_demo.complex_terrain.turning_controller import HybridTurningController

PROFILE = "cadence-normalized-hybrid-v10"
STATE_VERSION = "cadence-controller-state/v10"
NOMINAL = 0.6
SILENCE = 1e-4


class CadenceHybridController(HybridTurningController):
    def __post_init__(self):
        super().__post_init__()
        self._base_coupling = self.cpg_network.coupling_weights.copy()
        self.reset(seed=0)

    def reset(self, *, seed=None, init_phases=None, init_magnitudes=None):
        if init_magnitudes is not None and np.any(np.asarray(init_magnitudes) != 0):
            raise ValueError("v10 reset requires zero magnitudes")
        super().reset(seed=seed, init_phases=init_phases,
                      init_magnitudes=np.zeros(6))
        self.cpg_network.coupling_weights = self._base_coupling.copy()
        self._last_angles = self.preprogrammed_steps.get_joint_angles_by_dof_order(
            self.cpg_network.curr_phases, np.zeros(6), self.output_dof_order)
        # Use the installed HYBRID adhesion convention (including swing extension).
        self._last_adhesion = np.array([
            self.enable_adhesion and self._get_adhesion_onoff(leg, phase)
            for leg, phase in zip(self.legs, self.cpg_network.curr_phases)], dtype=bool)

    def step(self, descending_signal, obs):
        u = np.asarray(descending_signal, dtype=float)
        if u.shape != (2,) or not np.isfinite(u).all() or np.any(u < 0):
            raise ValueError("v10 requires two finite nonnegative v4 outputs")
        c = float(u.mean())
        a = float((u[1] - u[0]) / (2*c)) if c > 0 else 0.
        # Convex outer envelope of the unchanged v4 transfer's output state.
        if c > .4 + 1e-12 or abs(a) > .8 + 1e-12:
            raise ValueError("outside registered v4 output domain")
        if c > SILENCE:
            scale = c / NOMINAL
            self.cpg_network.intrinsic_freqs = self._base_intrinsic_freqs * scale
            self.cpg_network.coupling_weights = self._base_coupling * scale
            self.cpg_network.intrinsic_amps = np.repeat(NOMINAL * np.array([1-a, 1+a]), 3)
            # Deliberately bypass TurningController.step, which would overwrite
            # frequency/amplitude. Do not rescale timestep or convergence_coefs.
            action = HybridController.step(self, obs)
            self._last_angles = action.joint_angles.copy()
            self._last_adhesion = action.adhesion_onoff.copy()
        return LocomotionAction(self._last_angles.copy(), self._last_adhesion.copy())

    def checkpoint(self):
        # Includes mutable configuration, reset bases, RNG and diagnostic state,
        # not just oscillator coordinates. Independent copy forbids aliasing.
        return {"version": STATE_VERSION, "state": deepcopy(self.__dict__)}

    def restore(self, checkpoint):
        if set(checkpoint) != {"version", "state"} or checkpoint["version"] != STATE_VERSION:
            raise ValueError("unsupported v10 controller checkpoint")
        if set(checkpoint["state"]) != set(self.__dict__):
            raise ValueError("incomplete v10 controller checkpoint")
        self.__dict__ = deepcopy(checkpoint["state"])
