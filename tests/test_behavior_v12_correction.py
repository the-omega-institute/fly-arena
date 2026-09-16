from pathlib import Path
from unittest.mock import patch

import mujoco as mj
import numpy as np
import pytest

from flyarena.common import file_sha
from flyarena.experiments.behavior_v12_correction import (
    IMMUTABLE_SOURCE_HASHES,
    TOLERANCE,
    _cycle_metrics,
    _inventory_payload,
    _integration_state,
    _int_column,
    _phase_increment_failures,
    _phase_window_contract,
    _partition_true_runs,
    _validate_restoration_arrays,
    _validate_restoration_digest_sequences,
    capture_native_step,
    record_validation_test,
)
from flyarena.experiments.verify_behavior_v12_correction import _runs


ROOT = Path(__file__).resolve().parents[1]


def _contact_model():
    xml = """
    <mujoco>
      <option timestep="0.001" gravity="0 0 -9.81" integrator="Euler"/>
      <worldbody>
        <geom name="ground" type="plane" size="2 2 .1"/>
        <body name="slider" pos="0 0 .049">
          <freejoint/>
          <geom name="box" type="box" size=".05 .05 .05" mass="1"/>
        </body>
      </worldbody>
    </mujoco>
    """
    model = mj.MjModel.from_xml_string(xml)
    data = mj.MjData(model)
    data.qvel[0] = 0.2
    data.qvel[2] = -0.1
    mj.mj_forward(model, data)
    return model, data


def test_paired_capture_is_noninterfering_and_does_not_observer_forward():
    model, source = _contact_model()
    captured = mj.MjData(model)
    plain = mj.MjData(model)
    mj.mj_copyData(captured, model, source)
    mj.mj_copyData(plain, model, source)
    original_forward = mj.mj_forward
    with patch.object(mj, "mj_forward", side_effect=AssertionError("observer forward called")):
        paired = capture_native_step(model, captured)
    original_forward  # make the Python binding lifetime explicit for PyPy/static checkers
    mj.mj_step(model, plain)
    assert np.array_equal(_integration_state(model, captured), _integration_state(model, plain))
    assert np.array_equal(captured.geom_xpos, plain.geom_xpos)
    assert np.array_equal(captured.geom_xmat, plain.geom_xmat)
    assert len(paired.contact_rows) > 0
    detached = mj.MjData(model)
    detached.qpos[:] = paired.state_start_qpos
    detached.qvel[:] = paired.state_start_qvel
    mj.mj_forward(model, detached)
    assert np.max(np.abs(detached.geom_xpos - paired.cache_geom_xpos)) <= TOLERANCE
    detached.qpos[:] = paired.state_end_qpos
    detached.qvel[:] = paired.state_end_qvel
    mj.mj_forward(model, detached)
    assert np.max(np.abs(detached.geom_xpos - paired.cache_geom_xpos)) > TOLERANCE


def test_float64_cast_must_precede_mesh_mean():
    values = np.array([[1.0e-4, 0, 0], [1.0e-4 + 2.0e-11, 0, 0], [1.0e-4 + 4.0e-11, 0, 0]], dtype=np.float32)
    correct = np.asarray(values, dtype=np.float64).mean(axis=0, dtype=np.float64)
    rejected = np.asarray(values).mean(axis=0).astype(np.float64)
    assert not np.array_equal(correct, rejected)


def test_partition_distinguishes_boundary_partial_and_invalid_interior():
    state = np.zeros(20, dtype=bool)
    state[0:3] = True
    state[5:9] = True
    state[12:16] = True
    phase = np.arange(20, dtype=np.float64)
    phase[12:16] = 7.0
    result = _partition_true_runs(state, phase, 0, 19)
    assert result["complete"] == [(5, 9)]
    assert result["boundary_partials"] == [{
        "start_tick": 0, "end_tick_exclusive": 3, "reason": "analysis-window boundary"
    }]
    assert result["invalid_interior"][0]["reason"] == "nonincreasing phase within run"


def test_invalid_interior_phase_fails_cycle_gates_closed():
    rows = 25001
    phases = np.zeros((rows, 6), dtype=np.float64)
    phases[7000:8000] = 1.0
    ap = np.zeros((rows, 6), dtype=np.float64)
    heights = np.ones((rows, 6), dtype=np.float64)
    normal = np.ones((rows, 6), dtype=np.float64)
    weighted = np.zeros((rows, 6), dtype=np.float64)
    peak = np.zeros((rows, 6), dtype=np.float64)
    periods = {leg: [0.5, 2.5] for leg in ("lf", "lm", "lh", "rf", "rm", "rh")}
    result = _cycle_metrics(phases, ap, heights, normal, weighted, peak, periods)
    assert result["invalid_interior_phase_episodes"] > 0
    assert result["recovery_passed"] is False
    assert result["support_slip_passed"] is False


@pytest.mark.parametrize("relative,expected", sorted(IMMUTABLE_SOURCE_HASHES.items()))
def test_historical_v12_source_hashes_remain_exact(relative, expected):
    assert file_sha(ROOT / relative) == expected


def test_tick_zero_interval_index_is_unowned():
    rows = 40001
    start_rows = np.r_[-1, np.arange(rows - 1, dtype=np.int64)]
    assert start_rows.dtype == np.int64
    assert start_rows[0] == -1
    assert np.array_equal(start_rows[1:], np.arange(rows - 1))


def test_one_column_contact_schema_slice_is_row_vector():
    values = np.arange(30, dtype=np.float64).reshape(3, 10)
    result = _int_column(values, slice(4, 5))
    assert result.shape == (3,)
    assert np.array_equal(result, [4, 14, 24])


@pytest.mark.parametrize("bad_index,bad_value", [
    (1, 0.0),
    (4, -0.5),
    (7, 0.0),
    (9, float("nan")),
    (10, float("inf")),
])
def test_full_window_phase_check_rejects_plateaus_reversals_and_nonfinite(bad_index, bad_value):
    phase = np.arange(20, dtype=np.float64)
    phase[bad_index] = phase[bad_index - 1] + bad_value
    failures = _phase_increment_failures(phase, 0, 19)
    assert failures
    assert failures[0]["from_tick"] in {bad_index - 1, bad_index}


def test_full_window_phase_check_catches_cross_membership_backjump():
    phase = np.arange(20, dtype=np.float64)
    state = np.mod(phase, 4) < 2
    phase[8:] -= 3.0
    assert _phase_increment_failures(phase, 0, 19)[0]["from_tick"] == 7
    producer = _partition_true_runs(state, phase, 0, 19)
    assert producer["complete"]
    rows = 25001
    phases = np.repeat(np.arange(rows, dtype=np.float64)[:, None], 6, axis=1)
    phases[8000:, 0] -= 3.0
    zeros = np.zeros((rows, 6), dtype=np.float64)
    periods = {leg: [0.5, 2.5] for leg in ("lf", "lm", "lh", "rf", "rm", "rh")}
    assert _cycle_metrics(phases, zeros, zeros, zeros, zeros, zeros, periods)[
        "invalid_interior_phase_episodes"
    ] > 0


def test_bad_increment_in_boundary_partial_is_invalid_not_partial():
    state = np.zeros(20, dtype=bool)
    state[:5] = True
    phase = np.arange(20, dtype=np.float64)
    phase[3] = phase[2]
    result = _partition_true_runs(state, phase, 0, 19)
    assert result["boundary_partials"] == []
    assert result["invalid_interior"][0]["invalid_from_tick"] == 2


def test_genuinely_increasing_boundary_partial_remains_separate():
    state = np.zeros(20, dtype=bool)
    state[:5] = True
    phase = np.arange(20, dtype=np.float64)
    result = _partition_true_runs(state, phase, 0, 19)
    assert result["invalid_interior"] == []
    assert result["boundary_partials"][0]["reason"] == "analysis-window boundary"


def test_registered_zero_control_keeps_phase_semantics_separate():
    phases = np.zeros((25001, 6), dtype=np.float64)
    control = _phase_window_contract(phases, active=False)
    assert control == {
        "classification": "registered zero/silence control",
        "strict_increment_rule_applied": False,
        "increments_checked": 0,
        "failures": [],
    }
    assert _phase_window_contract(phases, active=True)["failures"]


def test_direct_partition_helpers_reject_recovered_reversal():
    phase = np.array([2, 3, 4, 2.5, 6, 7, 8, 9], dtype=np.float64)
    state = np.r_[False, np.ones(6, dtype=bool), False]
    assert _partition_true_runs(state, phase, 0, 7)["invalid_interior"]
    padded_phase = np.arange(25001, dtype=np.float64)
    padded_state = np.zeros(25001, dtype=bool)
    padded_phase[7000:7008] = phase
    padded_state[7001:7007] = True
    assert _runs(padded_state, padded_phase)[2] == [(7001, 7007)]


def _restoration_arrays():
    return {
        "core": np.zeros((100, 303), dtype=np.float64),
        "dense": np.zeros((100, 60), dtype=np.float64),
        "integration": np.zeros((100, 752), dtype=np.float64),
        "contacts": np.zeros((3, 26), dtype=np.float64),
        "contact_offsets": np.array([0, 1, 1, *([3] * 98)], dtype=np.int64),
    }


def test_restoration_exact_contract_accepts_legal_repeated_offsets():
    result = _validate_restoration_arrays(_restoration_arrays(), 752)
    assert result["contact_rows"] == 3
    assert result["legal_repeated_offsets"] > 0


@pytest.mark.parametrize("mutation", [
    "missing", "extra", "core-dtype", "core-width", "dense-width", "integration-int8",
    "integration-width", "contacts-width", "offsets-int32", "offsets-102", "offsets-start",
    "offsets-end", "offsets-decrease", "offsets-negative", "offsets-out-of-range", "nonfinite",
])
def test_restoration_exact_contract_rejects_malformed_substitutions(mutation):
    values = _restoration_arrays()
    if mutation == "missing":
        values.pop("integration")
    elif mutation == "extra":
        values["extra"] = np.zeros(1)
    elif mutation == "core-dtype":
        values["core"] = values["core"].astype(np.float32)
    elif mutation == "core-width":
        values["core"] = np.zeros((100, 302), dtype=np.float64)
    elif mutation == "dense-width":
        values["dense"] = np.zeros((100, 59), dtype=np.float64)
    elif mutation == "integration-int8":
        values["integration"] = np.zeros(1, dtype=np.int8)
    elif mutation == "integration-width":
        values["integration"] = np.zeros((100, 751), dtype=np.float64)
    elif mutation == "contacts-width":
        values["contacts"] = np.zeros((3, 25), dtype=np.float64)
    elif mutation == "offsets-int32":
        values["contact_offsets"] = values["contact_offsets"].astype(np.int32)
    elif mutation == "offsets-102":
        values["contact_offsets"] = np.r_[values["contact_offsets"], 3]
    elif mutation == "offsets-start":
        values["contact_offsets"][0] = 1
    elif mutation == "offsets-end":
        values["contact_offsets"][-1] = 2
    elif mutation == "offsets-decrease":
        values["contact_offsets"][50] = 2
        values["contact_offsets"][51] = 1
    elif mutation == "offsets-negative":
        values["contact_offsets"][50] = -1
    elif mutation == "offsets-out-of-range":
        values["contact_offsets"][50] = 4
    elif mutation == "nonfinite":
        values["core"][0, 0] = np.nan
    with pytest.raises(ValueError):
        _validate_restoration_arrays(values, 752)


def test_restoration_rejection_does_not_mutate_arrays():
    values = _restoration_arrays()
    values["contact_offsets"][50] = -1
    before = {name: value.copy() for name, value in values.items()}
    with pytest.raises(ValueError):
        _validate_restoration_arrays(values, 752)
    assert all(np.array_equal(values[name], before[name], equal_nan=True) for name in values)


@pytest.mark.parametrize("mutation", ["actual", "cache-length", "cache-schema", "controller-length", "controller-digest"])
def test_restoration_digest_sequences_are_exact_and_horizon_bound(mutation):
    checkpoint = {"cache": {"qpos": {}, "qvel": {}}}
    expected = {
        "cache": [{"qpos": {}, "qvel": {}} for _ in range(100)],
        "controller_state_sha256": ["a" * 64 for _ in range(100)],
    }
    actual = {
        "cache": [{"qpos": {}, "qvel": {}} for _ in range(100)],
        "controller_state_sha256": ["a" * 64 for _ in range(100)],
    }
    if mutation == "actual":
        actual["controller_state_sha256"][0] = "b" * 64
    elif mutation == "cache-length":
        expected["cache"].pop()
        actual["cache"].pop()
    elif mutation == "cache-schema":
        expected["cache"][0].pop("qvel")
        actual["cache"][0].pop("qvel")
    elif mutation == "controller-length":
        expected["controller_state_sha256"].pop()
        actual["controller_state_sha256"].pop()
    elif mutation == "controller-digest":
        expected["controller_state_sha256"][0] = "short"
        actual["controller_state_sha256"][0] = "short"
    with pytest.raises(ValueError):
        _validate_restoration_digest_sequences(expected, actual, checkpoint)


def test_cycle_contract_rejects_shape_and_dtype_mismatch():
    rows = 25001
    base = np.zeros((rows, 6), dtype=np.float64)
    periods = {leg: [0.5, 2.5] for leg in ("lf", "lm", "lh", "rf", "rm", "rh")}
    with pytest.raises(ValueError, match="cycle input"):
        _cycle_metrics(base.astype(np.float32), base, base, base, base, base, periods)
    with pytest.raises(ValueError, match="cycle input"):
        _cycle_metrics(base, base[:, :5], base, base, base, base, periods)


def test_record_validation_test_refuses_duplicate_execution_claim(tmp_path):
    output = tmp_path / "out"
    junit = output / "tests/test-invocation-01.junit.xml"
    junit.parent.mkdir(parents=True)
    junit.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"/>')
    (output / "registration.json").write_text("{}")
    with patch("flyarena.experiments.behavior_v12_correction._validate_validation_registration", return_value={"validation_source_seal": {"x": "y"}}):
        record_validation_test(output, ROOT, junit, "pytest focused", invocation=1)
        with pytest.raises(ValueError, match="duplicate"):
            record_validation_test(output, ROOT, junit, "pytest focused", invocation=1)


def test_inventory_requires_exact_regular_sorted_payload(tmp_path):
    (tmp_path / "a").write_text("a")
    assert _inventory_payload(tmp_path, ("a",))["a"]["bytes"] == 1
    (tmp_path / "extra").write_text("x")
    with pytest.raises(ValueError, match="payload mismatch"):
        _inventory_payload(tmp_path, ("a",))


def test_inventory_rejects_duplicate_unsorted_and_symlink(tmp_path):
    (tmp_path / "a").write_text("a")
    with pytest.raises(ValueError, match="sorted and unique"):
        _inventory_payload(tmp_path, ("a", "a"))
    (tmp_path / "link").symlink_to(tmp_path / "a")
    with pytest.raises(ValueError, match="nonregular"):
        _inventory_payload(tmp_path, ("a", "link"))
