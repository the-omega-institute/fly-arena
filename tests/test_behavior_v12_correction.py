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
    _integration_state,
    _int_column,
    _partition_true_runs,
    capture_native_step,
)


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
    assert result["invalid_interior"][0]["reason"] == "nonincreasing interior phase"


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
