"""Boundary and causal-state tests; no graph fixtures or scientific tuning."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from flyarena.backend import CPUBrainBackend
from flyarena.neural import Brain
from flyarena.experiments.contact_v6 import LEGS, ContactTibiaBridge, contact_ratios


def bridge():
    # Distinct single-neuron groups on a real tiny Brain with no edges.
    groups = {f"{kind}_{leg}": np.array([j*6+i]) for j, kind in enumerate(("afferent", "flexor", "extensor")) for i, leg in enumerate(LEGS)}
    graph = SimpleNamespace(n=18, indptr=np.zeros(19, dtype=np.int64), post=np.array([], dtype=np.int32),
                            baseline_weights=lambda: np.array([], dtype=np.float32))
    return ContactTibiaBridge(CPUBrainBackend(Brain(graph)), groups)


def test_force_norm_before_sum_and_native_scale_invariance():
    force = np.zeros((6, 3, 3))
    force[0] = [[3, 4, 0], [-3, -4, 0], [0, 0, 2]]
    np.testing.assert_array_equal(contact_ratios(force, 12), [1, 0, 0, 0, 0, 0])
    np.testing.assert_allclose(contact_ratios(force*1000, 12000), contact_ratios(force, 12))
    for bad in (0, -1, np.nan):
        with pytest.raises(ValueError):
            contact_ratios(force, bad)
    with pytest.raises(ValueError):
        contact_ratios(force[:, :2], 1)


def test_neural_only_commands_and_complete_restore():
    b = bridge()
    b.backend.brain.external[:] = 8  # Old odor/tonic current cannot survive.
    b.stimulate([2, 0, 0, 0, 0, 0])
    np.testing.assert_array_equal(b.backend.brain.external, [48]+[0]*17)
    # Stimulus cannot directly change action before motor neurons respond.
    np.testing.assert_array_equal(b.readout()[2], np.zeros(6))
    b.backend.brain.rates[6] = 25
    b.backend.brain.rates[15] = 50
    np.testing.assert_allclose(b.readout()[2], [.025, 0, 0, -.05, 0, 0])
    b.backend.brain.delay[7, 3] = 2.5
    b.backend.brain.tick = 39
    saved = b.checkpoint()
    b.backend.brain.reset()
    b.held_command[:] = 0
    b.restore(saved)
    for k, v in saved.items():
        np.testing.assert_array_equal(b.checkpoint()[k], v)
    with pytest.raises(ValueError):
        b.restore({**saved, "held_command": np.full(6, np.nan)})
    for value in ([1], [0, 0, 0, -1, 0, 0], [np.nan]*6):
        with pytest.raises(ValueError):
            b.stimulate(value)


def test_complete_delay_state_reproduces_real_integrator():
    b = bridge()
    b.stimulate([1, 0, 0, 0, 0, 0])
    b.backend.advance(123)
    state = b.checkpoint()
    expected_counts = b.backend.advance(100)
    expected = b.checkpoint()
    b.restore(state)
    np.testing.assert_array_equal(b.backend.advance(100), expected_counts)
    for k, v in expected.items():
        np.testing.assert_array_equal(b.checkpoint()[k], v)


def test_gate_rejects_silent_persistent_unilateral_saturated_and_nonrepeat():
    spec = importlib.util.spec_from_file_location("independent_verifier", Path(__file__).resolve().parents[1]/"scripts/verify_contact_tibia_v6.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    commands = {r: np.zeros((61, 6)) for r in verifier.RUNS}
    raw = {r: np.zeros((61, 6)) for r in verifier.RUNS}
    assert not verifier.evaluate(commands, raw, True)["neural_prerequisite_pass"]
    commands["LF"][21:26, 0] = .002
    assert not verifier.evaluate(commands, raw, True)["neural_prerequisite_pass"]
    commands["RF"][21:26, 3] = .002
    assert verifier.evaluate(commands, raw, True)["neural_prerequisite_pass"]
    commands["LF"][60, 0] = .000401
    assert not verifier.evaluate(commands, raw, True)["neural_prerequisite_pass"]
    commands["LF"][60, 0] = .0004
    assert verifier.evaluate(commands, raw, True)["neural_prerequisite_pass"]
    raw["LH"][35, 2] = 1
    assert not verifier.evaluate(commands, raw, True)["neural_prerequisite_pass"]
    raw["LH"][:] = 0
    assert not verifier.evaluate(commands, raw, False)["neural_prerequisite_pass"]
