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


def identity():
    return {"configuration": digest(MOTOR), "source": file_sha(Path(__file__))}


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
