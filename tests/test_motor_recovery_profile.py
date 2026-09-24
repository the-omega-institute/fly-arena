import numpy as np
import pytest

from flyarena.experiments.motor import (MOTOR, RECOVERY_MOTOR, MotorTransfer,
                                         RecoveryMotorTransfer, motor_for_profile,
                                         profile_identity)


def test_candidate_identity_is_versioned_and_old_identity_is_unchanged():
    assert MOTOR["id"] == "dn-cpg-approach-v4"
    assert RECOVERY_MOTOR["id"] == "dn-cpg-recovery-v5-candidate"
    assert profile_identity(MOTOR["id"])["configuration"] != profile_identity(RECOVERY_MOTOR["id"])["configuration"]
    assert isinstance(motor_for_profile(MOTOR["id"], admission="deployment"), MotorTransfer)


def test_old_profile_behavior_is_unchanged_by_candidate_construction():
    old = MotorTransfer()
    selected = motor_for_profile(MOTOR["id"], admission="training")
    candidate = RecoveryMotorTransfer()
    for _ in range(20):
        expected = old.advance([.3, .5])
        actual = selected.advance([.3, .5])
        np.testing.assert_allclose(actual, expected)
        candidate.advance([.3, .5], {"upright_z": 1., "roll_rate": 0., "pitch_rate": 0.,
                                     "support_left": .5, "support_right": .5})


def test_candidate_is_admission_restricted_and_uses_measured_state():
    with pytest.raises(ValueError, match="restricted"):
        motor_for_profile(RECOVERY_MOTOR["id"], admission="deployment")
    candidate = motor_for_profile(RECOVERY_MOTOR["id"], admission="sandbox")
    upright = candidate.advance([.5, .5], {"upright_z": 1., "roll_rate": 0., "pitch_rate": 0.,
                                           "support_left": .5, "support_right": .5})
    tilted = candidate.advance([.5, .5], {"upright_z": -.1, "roll_rate": 1., "pitch_rate": 0.,
                                          "support_left": 1., "support_right": 0.})
    assert np.isfinite(tilted).all() and np.all((tilted >= 0) & (tilted <= 1.5))
    assert not np.array_equal(upright, tilted)
    with pytest.raises(ValueError):
        candidate.advance([.5, .5], {"upright_z": .1})
