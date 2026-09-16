import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

import mujoco as mj
import numpy as np
import pytest

from flyarena.common import file_sha
from flyarena.experiments.behavior_v12_correction import (
    IMMUTABLE_SOURCE_HASHES,
    TOLERANCE,
    VALIDATION_PAYLOAD,
    _cycle_metrics,
    _inventory_payload,
    _integration_state,
    _int_column,
    _phase_increment_failures,
    _phase_window_contract,
    _partition_true_runs,
    _validate_validation_registration,
    _validate_restoration_arrays,
    _validate_restoration_digest_sequences,
    capture_native_step,
    finalize_validation,
    record_validation_test,
)
from flyarena.experiments.verify_behavior_v12_correction import _runs, _validate_digest_document


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


def test_partition_distinguishes_boundary_partial_and_complete_run():
    state = np.zeros(20, dtype=bool)
    state[0:3] = True
    state[5:9] = True
    state[12:16] = True
    phase = np.arange(20, dtype=np.float64)
    result = _partition_true_runs(state, phase, 0, 19)
    assert result["complete"] == [(5, 9), (12, 16)]
    assert result["boundary_partials"] == [{
        "start_tick": 0, "end_tick_exclusive": 3, "reason": "analysis-window boundary"
    }]
    assert result["invalid_interior"] == []


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
    assert producer["complete"] == []
    assert producer["invalid_interior"][0]["from_tick"] == 7
    rows = 25001
    phases = np.repeat(np.arange(rows, dtype=np.float64)[:, None], 6, axis=1)
    phases[8000:, 0] -= 3.0
    zeros = np.zeros((rows, 6), dtype=np.float64)
    periods = {leg: [0.5, 2.5] for leg in ("lf", "lm", "lh", "rf", "rm", "rh")}
    assert _cycle_metrics(phases, zeros, zeros, zeros, zeros, zeros, periods)[
        "invalid_interior_phase_episodes"
    ] > 0


@pytest.mark.parametrize("bad_tick", [5, 7])
def test_direct_helpers_reject_transition_plateau_and_between_run_reversal(bad_tick):
    phase = np.arange(20, dtype=np.float64)
    state = np.zeros(20, dtype=bool)
    state[2:5] = True
    state[7:10] = True
    phase[bad_tick] = phase[bad_tick - 1]
    producer = _partition_true_runs(state, phase, 0, 19)
    assert producer["complete"] == producer["boundary_partials"] == []
    assert producer["invalid_interior"]

    full_phase = np.arange(25001, dtype=np.float64)
    full_state = np.zeros(25001, dtype=bool)
    full_state[6002:6005] = True
    full_state[6007:6010] = True
    full_phase[6000:6020] = phase + 6000
    complete, partial, invalid = _runs(full_state, full_phase)
    assert complete == partial == []
    assert invalid


def test_bad_increment_in_boundary_partial_is_invalid_not_partial():
    state = np.zeros(20, dtype=bool)
    state[:5] = True
    phase = np.arange(20, dtype=np.float64)
    phase[3] = phase[2]
    result = _partition_true_runs(state, phase, 0, 19)
    assert result["boundary_partials"] == []
    assert result["invalid_interior"][0]["from_tick"] == 2


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
    complete, partial, invalid = _runs(padded_state, padded_phase)
    assert complete == partial == []
    assert invalid


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


def _array_digest():
    return {"dtype": "<f8", "shape": [3], "finite": True, "sha256": "a" * 64}


@pytest.mark.parametrize("mutation", [
    "actual", "cache-length", "cache-schema", "controller-length", "controller-digest",
    "paired-null", "paired-object", "paired-nonhex", "paired-uppercase", "paired-bad-dtype",
    "paired-negative-shape", "paired-nonfinite-flag", "paired-scalar-object",
])
def test_restoration_digest_sequences_are_exact_and_horizon_bound(mutation):
    checkpoint = {"cache": {"qpos": _array_digest(), "scalar.time": {"value": 1.0}}}
    expected = {
        "cache": [{"qpos": _array_digest(), "scalar.time": {"value": 1.0}} for _ in range(100)],
        "controller_state_sha256": ["a" * 64 for _ in range(100)],
    }
    actual = copy.deepcopy(expected)
    if mutation == "actual":
        actual["controller_state_sha256"][0] = "b" * 64
    elif mutation == "cache-length":
        expected["cache"].pop()
        actual["cache"].pop()
    elif mutation == "cache-schema":
        expected["cache"][0].pop("qpos")
        actual["cache"][0].pop("qpos")
    elif mutation == "controller-length":
        expected["controller_state_sha256"].pop()
        actual["controller_state_sha256"].pop()
    elif mutation == "controller-digest":
        expected["controller_state_sha256"][0] = "short"
        actual["controller_state_sha256"][0] = "short"
    elif mutation == "paired-null":
        expected["cache"][0]["qpos"] = None
        actual["cache"][0]["qpos"] = None
    elif mutation == "paired-object":
        expected["cache"][0]["qpos"] = {}
        actual["cache"][0]["qpos"] = {}
    elif mutation == "paired-nonhex":
        expected["controller_state_sha256"][0] = "z" * 64
        actual["controller_state_sha256"][0] = "z" * 64
    elif mutation == "paired-uppercase":
        expected["cache"][0]["qpos"]["sha256"] = "A" * 64
        actual["cache"][0]["qpos"]["sha256"] = "A" * 64
    elif mutation == "paired-bad-dtype":
        expected["cache"][0]["qpos"]["dtype"] = "not-a-dtype"
        actual["cache"][0]["qpos"]["dtype"] = "not-a-dtype"
    elif mutation == "paired-negative-shape":
        expected["cache"][0]["qpos"]["shape"] = [-1]
        actual["cache"][0]["qpos"]["shape"] = [-1]
    elif mutation == "paired-nonfinite-flag":
        expected["cache"][0]["qpos"]["finite"] = False
        actual["cache"][0]["qpos"]["finite"] = False
    elif mutation == "paired-scalar-object":
        expected["cache"][0]["scalar.time"] = {"value": {}}
        actual["cache"][0]["scalar.time"] = {"value": {}}
    with pytest.raises(ValueError):
        _validate_restoration_digest_sequences(expected, actual, checkpoint)
    if mutation == "actual":
        _validate_digest_document(expected, checkpoint["cache"], "expected")
        _validate_digest_document(actual, checkpoint["cache"], "actual")
        assert expected != actual
    else:
        with pytest.raises(ValueError):
            _validate_digest_document(expected, checkpoint["cache"], "expected")


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
    registration = {"validation_source_seal": {"x": "y"}, "source_identity_sha256": "a" * 64}
    with patch("flyarena.experiments.behavior_v12_correction._validate_validation_registration", return_value=registration):
        record_validation_test(output, ROOT, junit, "pytest focused", "b" * 64, invocation=1)
        with pytest.raises(ValueError, match="duplicate"):
            record_validation_test(output, ROOT, junit, "pytest focused", "b" * 64, invocation=1)


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


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _finalizer_fixture(root):
    root.mkdir()
    (root / "sealed-sources").mkdir()
    (root / "tests").mkdir()
    source_seal = {"source": {"bytes": 1, "sha256": "1" * 64}}
    registration = {
        "source_identity_sha256": "2" * 64,
        "validation_source_seal": source_seal,
        "scope_stop": "no walking, held-out, neural, phenotype, ablation, Lab/API/replay, or product admission",
        "legacy_v1_analysis_sha256": "3" * 64,
        "limits": {
            "workers": 1, "wall_seconds": 2700, "peak_rss_bytes": 2147483648,
            "new_output_scratch_bytes": 104857600, "physics_seconds": 0, "neural_seconds": 0,
            "network": False, "installs": False, "gpu": False, "remote_operations": False,
        },
    }
    trusted = "4" * 64
    _write_json(root / "registration.json", {"synthetic": True})
    chronology = {
        "schema": "behavior-v12-correction-validation-chronology/v3",
        "initial": {"completed_trials": 0, "status": "failed before outcome", "cause": "one-column contact schema was not flattened"},
        "revision_01": {"completed_trials": 16, "status": "partial outcomes observed before interruption"},
        "revision_02": {"completed_trials": 32, "status": "unchanged-seal restart after revision-01 partial outcomes"},
        "contract_01": {"known_outcomes_before_repair": 32, "status": "rejected; immutable identity retained separately"},
        "contract_02": {"known_outcomes_before_repair": 32, "status": "targeted post-outcome boundary correction"},
        "contract_02_attempt_01": {
            "status": "failed focused test invocation preserved under its own registration/source identity",
            "tests": 76, "passed": 75, "failed": 1, "data_or_gate_inconsistency": False,
        },
        "historical_test_claim": {
            "self_reported_runs": 3, "distinct_retained_execution_receipts": 1,
            "supported_distinct_run_count": 1, "historical_tiny_physics_seconds_reported": 0.0068,
            "status": "unsupported as three distinct executions; not reused as v3 evidence",
        },
        "blind_preregistration": False,
        "scientific_admission": False,
    }
    _write_json(root / "chronology.json", chronology)
    for name in ("behavior_v12_correction.py", "verify_behavior_v12_correction.py", "test_behavior_v12_correction.py"):
        (root / "sealed-sources" / name).write_text("x")
    resources = {
        "wall_seconds": 1.0, "user_cpu_seconds": 0.5, "system_cpu_seconds": 0.1,
        "peak_rss_bytes": 1024, "physics_seconds": 0, "neural_seconds": 0, "workers": 1,
    }
    producer_trial = {
        "eligible_active": True, "zero_control": False, "identity_sha256": "5" * 64,
        "derived_sha256": "6" * 64, "raw_contact_rows": 1,
        "active_phase_increments_checked": 114000, "phase_failures": [],
        "phase_contract": {}, "endpoint_next_cache_rows": 40000,
        "final_endpoint_policy": "core row 40000 has no next cache row and is explicitly excluded",
        "stance_slips_checked": 1, "max_endpoint_next_cache_error": 0.0,
        "max_slip_formula_error": 0.0, "raw_positive_normal_force_closed": True, "gates": {},
    }
    producer_trials = {f"trial-{index:02d}": copy.deepcopy(producer_trial) for index in range(32)}
    for index in range(28, 32):
        producer_trials[f"trial-{index:02d}"].update(
            eligible_active=False, zero_control=True, active_phase_increments_checked=0,
        )
    producer = {
        "schema": "behavior-v12-correction-retained-validation/v3", "passed": True,
        "terminal_state": "completed", "process_exit": 0, "scientific_admission": False,
        "legacy_v1_status": "rejected", "future_positive_experiments": "require fresh repaired seals",
        "registration_sha256": trusted, "trusted_registration_sha256": trusted,
        "source_identity_sha256": registration["source_identity_sha256"],
        "legacy_analysis_sha256": registration["legacy_v1_analysis_sha256"],
        "trial_count": 32, "active_trial_count": 28, "zero_control_count": 4,
        "active_phase_increments_checked": 3192000, "complete_phase_runs_recalculated": 5008,
        "endpoint_next_cache_rows_checked": 1280000, "final_endpoints_without_next_cache": 32,
        "stance_slip_formulas_checked": 2768, "raw_contact_rows_closed": 9095759,
        "index_closure": {"files": 12338, "bytes": 3217398285, "index_sha256": "2feab6649e24a2b8d3dde616cdfd4ef0db13d723bd1b232aa7d631ecb7aeae1f"},
        "restoration": {"passed": True, "integration_width_from_pinned_model": 752, "native_horizon_ticks": 100},
        "aggregate_gates": {"active_restoration_raw_join": True}, "trials": producer_trials,
        "scope": "retained byte/array/contract validation only; no Jacobian or wrench reconstruction",
        "scope_stop": registration["scope_stop"], "resources": resources,
    }
    _write_json(root / "retained-validation.json", producer)
    verifier_trial = {
        "eligible_active": True, "zero_control": False, "identity_sha256": "7" * 64,
        "raw_contact_rows": 1, "active_phase_increments_checked": 114000,
        "endpoint_next_cache_rows": 40000, "final_endpoint_without_next_cache": 1,
        "stance_slips_checked": 1, "max_endpoint_next_cache_error": 0.0,
        "max_slip_formula_error": 0.0, "raw_positive_normal_force_closed": True,
        "gates": {}, "cycle_status": [],
    }
    verifier_trials = {f"trial-{index:02d}": copy.deepcopy(verifier_trial) for index in range(32)}
    for index in range(28, 32):
        verifier_trials[f"trial-{index:02d}"].update(
            eligible_active=False, zero_control=True, active_phase_increments_checked=0,
        )
    coverage = {
        "trials": 32, "active_trials": 28, "zero_controls": 4,
        "active_phase_increments": 3192000, "complete_phase_runs": 5008,
        "endpoint_next_cache_rows": 1280000, "final_endpoints_without_next_cache": 32,
        "stance_slip_formulas": 2768, "raw_positive_normal_force_rows": 9095759,
    }
    verifier = {
        "schema": "behavior-v12-correction-independent-verification/v3", "passed": True,
        "terminal_state": "completed", "process_exit": 0, "scientific_admission": False,
        "registration_sha256": trusted, "trusted_registration_sha256": trusted,
        "source_identity_sha256": registration["source_identity_sha256"],
        "producer_receipt_sha256": file_sha(root / "retained-validation.json"),
        "legacy_v1_status": "rejected", "coverage": coverage,
        "aggregate_gates": producer["aggregate_gates"],
        "restoration": {"passed": True, "integration_width_from_pinned_model": 752, "ticks_checked": 100},
        "trials": verifier_trials,
        "scope": "full retained normal-force/cache/slip/phase/gate validation; no exhaustive Jacobian velocity or six-component wrench reconstruction",
        "scope_stop": registration["scope_stop"], "resources": resources,
    }
    _write_json(root / "independent-verification.json", verifier)
    for invocation in (1, 2):
        junit_relative = f"tests/test-invocation-{invocation:02d}.junit.xml"
        junit = root / junit_relative
        junit.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"/>')
        receipt = {
            "schema": "behavior-v12-correction-validation-test-run/v3", "invocation": invocation,
            "status": "passed", "terminal_state": "completed", "process_exit": 0,
            "command": f"pytest selection {invocation}", "tests": 2, "passed": 2,
            "failed": 0, "errors": 0, "skipped": 0, "junit": junit_relative,
            "junit_sha256": file_sha(junit), "registration_sha256": trusted,
            "trusted_registration_sha256": trusted,
            "source_identity_sha256": registration["source_identity_sha256"],
            "executed_source_seal": source_seal, "physics_seconds": 0, "neural_seconds": 0,
        }
        _write_json(root / f"tests/test-invocation-{invocation:02d}.json", receipt)
    for relative in VALIDATION_PAYLOAD:
        path = root / relative
        if relative.startswith("attempts/") and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("preserved")
    return registration, trusted


def test_finalizer_valid_serialized_control_passes(tmp_path):
    output = tmp_path / "valid"
    registration, trusted = _finalizer_fixture(output)
    with patch("flyarena.experiments.behavior_v12_correction._validate_validation_registration", return_value=registration):
        result = finalize_validation(output, ROOT, trusted)
    assert result["payload_files"] == len(VALIDATION_PAYLOAD)


@pytest.mark.parametrize("mutation", [
    "omitted-verifier-identity", "minimal-verifier", "forged-zero-junit", "empty-source-seal",
    "wrong-registration-digest", "wrong-producer-link", "changed-junit-bytes", "missing-output",
    "extra-output", "symlink-output",
])
def test_finalizer_rejects_serialized_boundary_attacks(tmp_path, mutation):
    output = tmp_path / mutation
    registration, trusted = _finalizer_fixture(output)
    if mutation in {"omitted-verifier-identity", "minimal-verifier", "wrong-producer-link"}:
        path = output / "independent-verification.json"
        value = json.loads(path.read_text())
        if mutation == "omitted-verifier-identity":
            value.pop("source_identity_sha256")
        elif mutation == "minimal-verifier":
            value = {"passed": True, "resources": value["resources"]}
        else:
            value["producer_receipt_sha256"] = "0" * 64
        _write_json(path, value)
    elif mutation in {"forged-zero-junit", "empty-source-seal", "wrong-registration-digest"}:
        receipt_path = output / "tests/test-invocation-02.json"
        receipt = json.loads(receipt_path.read_text())
        if mutation == "forged-zero-junit":
            junit = output / receipt["junit"]
            junit.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>')
            receipt.update(tests=0, passed=0, junit_sha256=file_sha(junit))
        elif mutation == "empty-source-seal":
            receipt["executed_source_seal"] = {}
        else:
            receipt["registration_sha256"] = "0" * 64
        _write_json(receipt_path, receipt)
    elif mutation == "changed-junit-bytes":
        (output / "tests/test-invocation-02.junit.xml").write_text(
            '<testsuite tests="3" failures="0" errors="0" skipped="0"/>'
        )
    elif mutation == "missing-output":
        (output / "sealed-sources/test_behavior_v12_correction.py").unlink()
    elif mutation == "extra-output":
        (output / "extra.json").write_text("{}")
    elif mutation == "symlink-output":
        target = output / "sealed-sources/test_behavior_v12_correction.py"
        target.unlink()
        target.symlink_to(output / "registration.json")
    with patch("flyarena.experiments.behavior_v12_correction._validate_validation_registration", return_value=registration):
        with pytest.raises((ValueError, FileNotFoundError)):
            finalize_validation(output, ROOT, trusted)


@pytest.mark.parametrize("mutation", ["policy", "limits", "legacy", "source-set", "output-path"])
def test_real_registration_rejects_mutation_under_stale_trusted_root(tmp_path, mutation):
    contract = os.environ.get("FLY_V12_CONTRACT_OUTPUT")
    trusted = os.environ.get("FLY_V12_TRUSTED_REGISTRATION_SHA256")
    if not contract or not trusted:
        pytest.skip("sealed contract environment is required")
    source = Path(contract) / "registration.json"
    value = json.loads(source.read_text())
    if mutation == "policy":
        value["scientific_admission"] = True
    elif mutation == "limits":
        value["limits"]["network"] = True
    elif mutation == "legacy":
        value["legacy_v1_registration_sha256"] = "0" * 64
    elif mutation == "source-set":
        value["validation_source_seal"].pop(next(iter(value["validation_source_seal"])))
    else:
        value["output"] = str(tmp_path / "elsewhere")
    output = tmp_path / "mutated"
    output.mkdir()
    _write_json(output / "registration.json", value)
    with pytest.raises(ValueError, match="trusted registration digest"):
        _validate_validation_registration(ROOT, output, trusted)
