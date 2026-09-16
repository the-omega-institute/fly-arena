"""Prospective v12 implementation contracts; fixtures are not qualification."""
from copy import deepcopy
import json
import pickle
from types import SimpleNamespace

import mujoco as mj
import numpy as np
import pytest

from flyarena.experiments.cadence_v12 import ExcursionHybridController, PROFILE
from flyarena.experiments import mechanical_v12 as runner
from flyarena.experiments.verify_v12 import _median31, complete_runs


def observation():
    from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
    return HybridControllerObservation(1.0, np.zeros(6), np.zeros((6, 3, 3)), np.array([1.0, 0.0, 0.0]))


def test_only_nominal_target_scalar_changes():
    controller = ExcursionHybridController(timestep=runner.DT)
    controller.reset(seed=42)
    base_frequency = controller._base_intrinsic_freqs.copy()
    base_coupling = controller._base_coupling.copy()
    controller.step([0.04, 0.36], observation())
    np.testing.assert_allclose(controller.cpg_network.intrinsic_amps, np.repeat([0.2, 1.8], 3), rtol=0, atol=1e-15)
    np.testing.assert_allclose(controller.cpg_network.intrinsic_freqs, base_frequency * (0.2 / 0.6), rtol=0, atol=1e-15)
    np.testing.assert_allclose(controller.cpg_network.coupling_weights, base_coupling * (0.2 / 0.6), rtol=0, atol=1e-15)
    np.testing.assert_array_equal(controller.cpg_network.convergence_coefs, np.full(6, 20.0))


@pytest.mark.parametrize("bad", [[1, 1], [0, 0.2], [-0.1, 0.2], [np.nan, 0], [0.2]])
def test_invalid_candidate_input_is_atomic(bad):
    controller = ExcursionHybridController(timestep=runner.DT)
    before = pickle.dumps(controller.checkpoint(), protocol=5)
    with pytest.raises(ValueError):
        controller.step(bad, None)
    assert pickle.dumps(controller.checkpoint(), protocol=5) == before


def test_discrete_median_and_complete_run_endpoints():
    values = np.arange(40.0)
    filtered = _median31(values)
    np.testing.assert_array_equal(filtered, np.arange(15.0, 25.0))
    state = np.array([1, 1, 0, 0, 1, 1, 1, 0, 0, 1], dtype=bool)
    phase = np.arange(len(state), dtype=float)
    runs, partial = complete_runs(state, phase, 0, 9)
    assert runs == [(4, 7)] and partial == 2


def test_native_contact_relative_velocity_matches_point_jacobian():
    body = runner.new_body(42, PROFILE)
    recorder = runner.NativeRecorder(body)
    # Initial forward normally contains foot-ground margin contacts. Advance if needed.
    events = []
    for _ in range(100):
        _, _, events = recorder.row(np.zeros(2))
        if events:
            break
        runner.step(body, np.zeros(2))
    assert events
    data, model = body.data, body.model
    slices = runner._slices(runner.CONTACT)
    for row in events:
        foot = int(row[slices["foot_geom"]][0])
        ground = int(row[slices["ground_geom"]][0])
        point = row[slices["position"]]
        jf = np.zeros((3, model.nv))
        jg = np.zeros((3, model.nv))
        mj.mj_jac(model, data, jf, None, point, int(model.geom_bodyid[foot]))
        mj.mj_jac(model, data, jg, None, point, int(model.geom_bodyid[ground]))
        np.testing.assert_allclose((jf - jg) @ data.qvel,
                                   row[slices["relative_velocity_world"]], rtol=0, atol=2e-12)


def test_active_restore_binding_and_bitwise_continuation(tmp_path):
    root = tmp_path / "experiment"
    root.mkdir()
    (root / "registration.json").write_text("{}")
    body = runner.new_body(42, PROFILE)
    recorder = runner.NativeRecorder(body)
    for _ in range(25):
        runner.step(body, np.array([0.2, 0.2]))
    body.tick = runner.CHECKPOINT_TICK
    reg = {"model_sha256": "model", "sources_sha256": "sources"}
    checkpoint = runner.capture_active_checkpoint(root, body, reg)
    expected = [runner._continuation_sample(body, recorder, np.array([0.2, 0.2])) for _ in range(3)]
    body.data.qpos[0] += 1
    body.controllers[0].cpg_network.curr_phases[0] += 1
    body.tick += 7
    runner.restore_active_checkpoint(root, body, checkpoint, reg)
    actual = [runner._continuation_sample(body, recorder, np.array([0.2, 0.2])) for _ in range(3)]
    for left, right in zip(expected, actual):
        for field in ["core", "dense", "contacts", "integration"]:
            np.testing.assert_array_equal(left[field], right[field])
        assert left["cache"] == right["cache"]
        assert left["controller_state_sha256"] == right["controller_state_sha256"]
    before = (runner.integration(body).copy(), pickle.dumps(body.controllers[0].checkpoint(), protocol=5), body.tick)
    invalid = deepcopy(checkpoint)
    invalid["binding"]["seed"] = 43
    with pytest.raises(ValueError, match="binding"):
        runner.restore_active_checkpoint(root, body, invalid, reg)
    np.testing.assert_array_equal(runner.integration(body), before[0])
    assert pickle.dumps(body.controllers[0].checkpoint(), protocol=5) == before[1]
    assert body.tick == before[2]


def test_v12_physical_failure_finalizes_all_initialized_streams(tmp_path, monkeypatch):
    root = tmp_path / "experiment"
    root.mkdir()
    runner.write_json(root / "registration.json", {"compiled_arrays": {}, "sources_sha256": "synthetic"})
    physical = FloatingPointError("synthetic active physics failure")
    controller = SimpleNamespace(cpg_network=SimpleNamespace(curr_phases=np.zeros(6), curr_magnitudes=np.zeros(6)))
    body = SimpleNamespace(model=None, tick=0, controllers=[controller], drives=np.zeros((1, 2)),
        data=SimpleNamespace(qpos=np.zeros(2), qvel=np.zeros(2), qacc=np.zeros(2), ctrl=np.zeros(2),
            actuator_force=np.zeros(2), time=0.0))
    monkeypatch.setattr(runner, "new_body", lambda seed, profile: body)
    monkeypatch.setattr(runner, "NativeRecorder", lambda body: SimpleNamespace(
        row=lambda u: (np.zeros(runner._width(runner.CORE)), np.zeros(runner._width(runner.DENSE)), [])))
    monkeypatch.setattr(runner, "step", lambda body, u: (_ for _ in ()).throw(physical))
    monkeypatch.setattr(runner, "integration", lambda body: np.zeros(3))
    budget = SimpleNamespace(steps=0, report=lambda: {"mechanical_seconds": 0}, check=lambda: None)
    with pytest.raises(FloatingPointError) as caught:
        runner.run_trial(root, "development", "historical", 42, runner.CASES[0], budget, {})
    assert caught.value is physical
    trial = root / "development/historical--42--zero"
    for stream in ["core", "dense", "contacts"]:
        terminal = json.loads((trial / stream / "terminal.json").read_text())
        assert terminal["primary_failure"]["message"] == str(physical)
    terminal = json.loads((trial / "trial-terminal.json").read_text())
    assert terminal["complete"] is False
    assert terminal["primary_failure"]["message"] == str(physical)
