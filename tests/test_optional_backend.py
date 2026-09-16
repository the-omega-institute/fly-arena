import copy
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest
from flyarena.optional_backend import CheckedCPUBackend, NeuralBackend, create_backend
from flyarena.backend import backend_catalog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cuda_fixtures import fixture as make_fixture
from numba import config


def fixture(name):
    factory = (lambda graph, **kwargs: create_backend('cuda-simulator-diagnostic', graph, **kwargs)) if config.ENABLE_CUDASIM else CheckedCPUBackend
    return make_fixture(name, factory)


def state_equal(a, b):
    assert a['binding'] == b['binding']
    for k in a['state']:
        np.testing.assert_array_equal(a['state'][k], b['state'][k])


def test_prepare_is_validation_not_reset_and_owns_inputs():
    b = fixture('mutant_intrinsics')
    assert isinstance(b, NeuralBackend)
    b.stimulate(1., .5)
    b.advance(30)
    before = b.checkpoint()
    b.prepare(b.binding)
    b.prepare(b.binding)
    state_equal(before, b.checkpoint())
    with pytest.raises(ValueError): b.prepare(replace(b.binding, sensor_id='other'))
    state_equal(before, b.checkpoint())
    with pytest.raises(ValueError): b.brain.weights[0] = 7


@pytest.mark.parametrize('value', [True, np.bool_(False), 1.0, -1, [1], np.array(1), 2**31])
def test_strict_steps(value):
    b = fixture('silent')
    with pytest.raises(ValueError): b.advance(value)
    assert b.brain.tick == 0


@pytest.mark.parametrize('value', [True, '1', [1], np.array(1), float('nan'), float('inf'), -.1, 1.1])
def test_strict_stimulus_atomic(value):
    b = fixture('silent')
    b.stimulate(.5, .25)
    before = b.checkpoint()
    with pytest.raises(ValueError): b.stimulate(1, value)
    state_equal(before, b.checkpoint())


@pytest.mark.parametrize('indices', [[-1], [4], [True], [1.0], [[1]], 1, '1'])
def test_strict_indices(indices):
    with pytest.raises(ValueError): fixture('silent').neural_output(indices)


@pytest.mark.parametrize('mutation', ['float_tick','bool_tick','negative_tick','negative_total','fractional_refractory','negative_refractory','large_refractory','negative_rates','nan','missing','extra','binding','shape'])
def test_restore_rejects_without_any_mutation(mutation):
    b = fixture('mutant_intrinsics'); b.stimulate(1,.5); b.advance(31)
    before = b.checkpoint(); bad = copy.deepcopy(before)
    bad['state']['v'][:] = 123
    if mutation == 'float_tick': bad['state']['tick'] = np.array(31.)
    elif mutation == 'bool_tick': bad['state']['tick'] = np.array(True)
    elif mutation == 'negative_tick': bad['state']['tick'] = np.array(-1, dtype=np.int64)
    elif mutation == 'negative_total': bad['state']['total_spikes'] = np.array(-1, dtype=np.int64)
    elif mutation == 'fractional_refractory': bad['state']['refractory'] = np.full(4, .5)
    elif mutation == 'negative_refractory': bad['state']['refractory'][0] = -1
    elif mutation == 'large_refractory': bad['state']['refractory'][0] = 23
    elif mutation == 'negative_rates': bad['state']['rates'][0] = -1
    elif mutation == 'nan': bad['state']['rates'][0] = np.nan
    elif mutation == 'missing': del bad['state']['rates']
    elif mutation == 'extra': bad['state']['arbitrary'] = np.array(0)
    elif mutation == 'binding': bad['binding']['tau_ms'] = 19.
    elif mutation == 'shape': bad['state']['rates'] = np.zeros(5)
    with pytest.raises(ValueError): b.restore(bad)
    state_equal(before, b.checkpoint())


def test_indices_copy_zero_steps_overflow_and_seed():
    b = fixture('silent')
    np.testing.assert_array_equal(b.advance(0), np.zeros(4, dtype=np.int32))
    out = b.neural_output([0,2]); out[:] = 42
    assert not b.neural_output().any()
    with pytest.raises(ValueError): b.reset(True)
    state=b.checkpoint(); state['state']['tick'] = np.array(2**63-1,dtype=np.int64)
    b.restore(state)
    with pytest.raises(ValueError): b.advance(1)


def test_graph_and_weight_binding_mismatch():
    a,b = fixture('silent'),fixture('mutant_intrinsics')
    with pytest.raises(ValueError): b.restore(a.checkpoint())


@pytest.mark.parametrize('steps', [1, 2])
def test_last_safe_delay_offset_matches_small_tick_oracle(steps):
    maximum = int(np.iinfo(np.int64).max)
    tick = maximum - 18 - (steps - 1)
    b = fixture('delay_self_inhibitory')
    oracle = make_fixture('delay_self_inhibitory')
    for backend, start in ((b, tick), (oracle, tick % 19)):
        state = backend.checkpoint()
        state['state']['tick'] = np.array(start, dtype=np.int64)
        # Spike on the final iteration so the largest future-slot sum is used.
        state['state']['refractory'][0] = steps - 1
        backend.restore(state)
    np.testing.assert_array_equal(b.advance(steps), oracle.advance(steps))
    actual, expected = b.checkpoint(), oracle.checkpoint()
    assert actual['state']['tick'].item() == tick + steps
    assert actual['state']['total_spikes'].item() == 1
    np.testing.assert_array_equal(actual['state']['delay'][maximum % 19, :2], [2., -3.])
    actual['state']['tick'] = expected['state']['tick']
    state_equal(actual, expected)


@pytest.mark.parametrize('distance,steps', [(17, 1), (18, 2), (1, 1), (0, 1)])
def test_unsafe_delay_offset_rejected_atomically(distance, steps):
    b = fixture('delay_self_inhibitory')
    state = b.checkpoint()
    state['state']['tick'] = np.array(int(np.iinfo(np.int64).max) - distance, dtype=np.int64)
    b.restore(state)
    before = b.checkpoint()
    with pytest.raises(ValueError, match='overflow'):
        b.advance(steps)
    state_equal(before, b.checkpoint())


def test_zero_steps_at_maximum_counters_preserves_all_state():
    b = fixture('delay_self_inhibitory')
    state = b.checkpoint()
    for name in ('tick', 'total_spikes'):
        state['state'][name] = np.array(np.iinfo(np.int64).max, dtype=np.int64)
    b.restore(state)
    before = b.checkpoint()
    counts = b.advance(0)
    assert counts.dtype == np.int32
    np.testing.assert_array_equal(counts, np.zeros(4, dtype=np.int32))
    state_equal(before, b.checkpoint())


def test_real_cuda_refuses_simulator_or_missing_device():
    from numba import config, cuda
    b = fixture('silent')
    if config.ENABLE_CUDASIM or not cuda.is_available():
        with pytest.raises(RuntimeError): create_backend('cuda', b.brain.graph, weights=b.brain.weights)
    if not config.ENABLE_CUDASIM:
        with pytest.raises(RuntimeError): create_backend('cuda-simulator-diagnostic', b.brain.graph, weights=b.brain.weights)
    assert next(row for row in backend_catalog() if row['id']=='cuda')['available'] is False
