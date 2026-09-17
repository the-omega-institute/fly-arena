"""Safety and neural authority of the separately versioned approach transfer."""
import numpy as np
import pytest
from flyarena.experiments.motor import MotorTransfer, MOTOR


def steady(command):
    motor = MotorTransfer()
    for _ in range(400):
        output = motor.advance(command)
    return output


def test_high_neural_drive_slows_propulsion_without_reversing_turn():
    assert MOTOR['id'].endswith('-v4')
    assert steady([.7,.7]).mean() < .6*steady([.5,.5]).mean()
    left = steady([.63,.67])
    right = steady([.67,.63])
    np.testing.assert_allclose(left, right[::-1])
    assert left[1] > left[0] >= 0


def test_zero_authority_and_finite_bounded_response_after_cue_offset():
    motor = MotorTransfer()
    for _ in range(50):
        np.testing.assert_array_equal(motor.advance([0,0]), [0,0])
    for command in ([.1,1.2], [1.2,.1], [.65,.65], [100,1]):
        for _ in range(100):
            value = motor.advance(command)
            assert np.isfinite(value).all() and np.all((0<=value)&(value<=1.5))
    for _ in range(400):
        value = motor.advance([0,0])
    assert value.max()<1e-7


@pytest.mark.parametrize('command', [[-1,0], [np.nan,0], [np.inf,0], [1], [[1,2]]])
def test_rejects_invalid_neural_inputs_without_state_mutation(command):
    motor = MotorTransfer()
    before = motor.advance([.4,.6])
    with pytest.raises(ValueError):
        motor.advance(command)
    np.testing.assert_array_equal(motor.state, before)
