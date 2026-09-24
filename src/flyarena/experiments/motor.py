"""Versioned engineering transfer from frozen DN decoder output to CPG amplitudes.

Input is neural decoder output only; state is a fixed motor low-pass filter.
Dose calibration measured ~0.55/1.09/1.66 rad at differential .2/.4/.6
(common .6, .8 s); common .3 halves translation while retaining yaw response.
High decoded common drive additionally scales both motor channels down, preserving
their normalized asymmetry without amplifying curvature. This addresses overshoot
without access to food, sensory channels, body pose, reward or target geometry.
The transfer is an engineering hypothesis requiring held-out body qualification.
"""
from __future__ import annotations
import numpy as np
from ..common import digest, file_sha
from pathlib import Path

MOTOR = {"id": "dn-cpg-approach-v4", "asymmetry_gain": 6., "max_asymmetry": .8,
         "turn_slowing": .5, "previous_fraction": .65, "max_common": .4, "decoded_previous_fraction": .9,
         "high_drive_start": .54, "high_drive_full": .64, "minimum_speed_fraction": .4,
         "dose_evidence_sha256": "b490342a2bad32ce3a1351627e88ffbcbe3755d49dabf7b4156f038ff15646b3", "actions": 2,
         "input": "frozen descending-kernel-v2 neural output; no sensory or world state"}

# This profile is deliberately kept out of the deployment bridge and the
# qualification manifest.  It is an observation-only research candidate: the
# extra inputs are measurements of the embodied body state, not target, food,
# route or time signals.  The response is a bounded change in bilateral leg
# drive.  It never edits pose, resets the body, or commands a heading.
RECOVERY_MOTOR = {
    "id": "dn-cpg-recovery-v5-candidate",
    "base_profile": MOTOR["id"],
    "admission": "sandbox-observation-only",
    "body_state_inputs": ["upright_z", "roll_rate", "pitch_rate", "support_left", "support_right"],
    "upright_threshold": .35,
    "tilt_gain": .35,
    "angular_gain": .08,
    "support_gain": .06,
    "max_correction": .18,
    "minimum_propulsion_fraction": .2,
    "input": "frozen descending-kernel-v2 neural output plus measured body support/orientation state",
}


def identity():
    return {"configuration": digest(MOTOR), "source": file_sha(Path(__file__))}


def profile_identity(profile_id: str = MOTOR["id"]):
    """Return an immutable identity for an explicitly selected motor profile."""
    if profile_id == MOTOR["id"]:
        return identity()
    if profile_id == RECOVERY_MOTOR["id"]:
        return {"configuration": digest(RECOVERY_MOTOR), "source": file_sha(Path(__file__))}
    raise ValueError(f"Unknown motor profile: {profile_id}")


class MotorTransfer:
    def __init__(self):
        self.state = np.zeros(2)
        self.decoded_state = np.zeros(2)

    def advance(self, decoded):
        command = np.asarray(decoded, dtype=float)
        if command.shape != (2,) or not np.isfinite(command).all() or np.any(command < 0):
            raise ValueError("motor transfer requires two finite nonnegative neural outputs")
        beta = MOTOR["decoded_previous_fraction"]
        self.decoded_state = beta*self.decoded_state+(1-beta)*command
        command = self.decoded_state
        common = float(command.mean())
        asymmetry = (command[1]-command[0]) / (2*common) if common > 1e-12 else 0.
        turn = MOTOR["max_asymmetry"] * np.tanh(MOTOR["asymmetry_gain"] * asymmetry / MOTOR["max_asymmetry"])
        speed = min(common, MOTOR["max_common"]) * (1-MOTOR["turn_slowing"]*abs(turn))
        high_drive = float(np.clip((common-MOTOR["high_drive_start"]) /
                                   (MOTOR["high_drive_full"]-MOTOR["high_drive_start"]), 0., 1.))
        # Smooth transition avoids a hard stop threshold in noisy decoded drive.
        high_drive = high_drive*high_drive*(3-2*high_drive)
        propulsion = speed * (1-(1-MOTOR["minimum_speed_fraction"])*high_drive)
        differential = propulsion*turn
        target = np.array([propulsion-differential, propulsion+differential])
        alpha = MOTOR["previous_fraction"]
        self.state = alpha*self.state+(1-alpha)*target
        return self.state.copy()


class RecoveryMotorTransfer:
    """Experimental leg-drive correction for measured low-stability states.

    ``body_state`` is intentionally explicit and small.  ``upright_z`` is the
    recorded thorax local-Z projection in world-Z; rates are measured body
    angular rates; support values are binary/continuous measured tarsal
    support fractions.  The underlying v4 transfer remains authoritative for
    neural drive, while this candidate adds a smooth bounded bilateral
    correction.  A caller must opt into the sandbox admission scope.
    """

    def __init__(self, *, admission: str = "sandbox"):
        if admission not in {"sandbox", "observation"}:
            raise ValueError("dn-cpg-recovery-v5-candidate is restricted to sandbox observation")
        self.admission = admission
        self.base = MotorTransfer()
        self.state = np.zeros(2)

    @staticmethod
    def _state(body_state):
        if not isinstance(body_state, dict):
            raise ValueError("recovery motor requires a measured body-state mapping")
        required = tuple(RECOVERY_MOTOR["body_state_inputs"])
        if any(key not in body_state for key in required):
            raise ValueError("recovery motor body state is missing a required measurement")
        values = np.asarray([body_state[key] for key in required], dtype=float)
        if values.shape != (len(required),) or not np.isfinite(values).all():
            raise ValueError("recovery motor body state must be finite")
        if not -1 <= values[0] <= 1:
            raise ValueError("upright_z must be a measured projection in [-1, 1]")
        if np.any(values[3:] < 0) or np.any(values[3:] > 1):
            raise ValueError("support measurements must be in [0, 1]")
        return values

    def advance(self, decoded, body_state):
        values = self._state(body_state)
        base = self.base.advance(decoded)
        upright_z, roll_rate, pitch_rate, support_left, support_right = values
        tilt = np.clip(RECOVERY_MOTOR["upright_threshold"] - upright_z, 0., 1.)
        support_imbalance = support_left - support_right
        # Angular and support terms alter the two leg channels in opposite
        # directions, allowing physical ground contact to generate a restoring
        # moment.  Pitch only reduces propulsion; it does not steer to a goal.
        correction = np.clip(
            -RECOVERY_MOTOR["angular_gain"] * roll_rate
            + RECOVERY_MOTOR["support_gain"] * support_imbalance,
            -RECOVERY_MOTOR["max_correction"], RECOVERY_MOTOR["max_correction"])
        correction *= np.clip(tilt / max(RECOVERY_MOTOR["upright_threshold"], 1e-9), 0., 1.)
        propulsion = np.clip(1. - RECOVERY_MOTOR["tilt_gain"] * tilt
                             - .02 * abs(pitch_rate),
                             RECOVERY_MOTOR["minimum_propulsion_fraction"], 1.)
        target = np.clip(base * propulsion + np.array([-correction, correction]), 0., 1.5)
        self.state = .8 * self.state + .2 * target
        return self.state.copy()


def motor_for_profile(profile_id: str, *, admission: str = "sandbox"):
    """Construct an explicitly selected motor, enforcing candidate admission."""
    if profile_id == MOTOR["id"]:
        if admission not in {"deployment", "training", "sandbox", "observation"}:
            raise ValueError(f"Unknown admission scope: {admission}")
        return MotorTransfer()
    if profile_id == RECOVERY_MOTOR["id"]:
        return RecoveryMotorTransfer(admission=admission)
    raise ValueError(f"Unknown motor profile: {profile_id}")
