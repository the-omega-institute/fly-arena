"""Frozen tiny semantic cases; deliberately independent analytical expectations."""
from types import SimpleNamespace
import numpy as np
from flyarena.optional_backend import CheckedCPUBackend

NAMES = ('silent', 'delay_self_inhibitory', 'ordered_cancellation', 'threshold_exact',
         'threshold_above_rest', 'stimulus_replacement', 'mutant_intrinsics')


def fixture(name, factory=CheckedCPUBackend):
    if name not in NAMES:
        raise ValueError(name)
    n, sources, posts, weights = 4, [], [], []
    kwargs = {}
    if name == 'delay_self_inhibitory':
        sources, posts, weights = [0, 0], [0, 1], [2., -3.]
    elif name == 'ordered_cancellation':
        sources, posts, weights = [0, 1, 2], [3, 3, 3], [2.**54, -2.**54, 1.]
    elif name in ('threshold_exact', 'threshold_above_rest'):
        kwargs['threshold_shift'] = -7. if name == 'threshold_exact' else float(np.nextafter(-52., np.inf) + 45.)
    elif name == 'mutant_intrinsics':
        sources, posts, weights = [0, 1, 2], [1, 2, 0], [.5, -1., .75]
        kwargs.update(tau_scale=.75, threshold_shift=.125)
    groups = {key: np.arange(n, dtype=np.int32) for key in
              ('olfactory', 'projection', 'local', 'memory', 'readout', 'descending', 'visual', 'motor')}
    groups.update(olfactory_left=np.array([0], dtype=np.int32), olfactory_right=np.array([1], dtype=np.int32))
    graph = SimpleNamespace(n=n, ids=np.arange(n, dtype=np.int64),
        indptr=np.r_[0, np.cumsum(np.bincount(sources, minlength=n))].astype(np.int64),
        post=np.array(posts, dtype=np.int32), groups=groups,
        baseline_weights=lambda: np.array(weights, dtype=np.float32))
    backend = factory(graph, **kwargs)
    state = backend.checkpoint()
    if name == 'delay_self_inhibitory':
        state['state']['v'][0] = -44.9
    elif name == 'ordered_cancellation':
        state['state']['v'][:3] = -44.9
    backend.restore(state)
    return backend


def stimulus(name, tick):
    if name in ('stimulus_replacement', 'mutant_intrinsics'):
        return (1., .5) if tick < 24 else (0., .25)
    return (0., 0.)


def snapshot(backend, counts):
    state = backend.checkpoint()['state']
    return {**{k: v.tolist() for k, v in state.items()}, 'counts': counts.tolist()}


def require(condition, message):
    """Validation remains active under python -O and PYTHONOPTIMIZE."""
    if not condition:
        raise ValueError(message)


def analytical(name, rows):
    """Checks derive from event semantics, not candidate pass flags."""
    if name in ('silent', 'threshold_above_rest'):
        require(all(r['total_spikes'] == 0 for r in rows),
                'expected no spikes')
    if name == 'threshold_exact':
        for k, row in enumerate(rows):
            require(row['counts'] == ([1] * 4 if k % 23 == 0 else [0] * 4),
                    'threshold spike timing changed')
            require(row['refractory'] == [22 - k % 23] * 4,
                    'refractory countdown changed')
    if name == 'delay_self_inhibitory':
        require(rows[0]['counts'] == [1, 0, 0, 0],
                'initial spike changed')
        require(rows[0]['delay'][18][:2] == [2., -3.],
                'initial delayed weights changed')
        require(all(r['current'][:2] == [0., 0.] for r in rows[:18]),
                'current arrived before tick 18')
        require(rows[18]['current'][:2] == [2., -3.],
                'tick-18 arrival changed')
        require(all(r['v'][0] == -52. for r in rows[:23]),
                'refractory voltage changed')
        require(rows[18]['refractory'][0] == 4,
                'tick-18 refractory count changed')
        require(rows[22]['refractory'][0] == 0,
                '22 skipped refractory ticks changed')
        require(rows[23]['v'][0] > -52.,
                'voltage did not resume after refractory period')
        require(rows[18]['v'][1] < -52.,
                'inhibitory arrival did not lower voltage')
    if name == 'ordered_cancellation':
        require(rows[0]['counts'] == [1, 1, 1, 0],
                'cancellation source spikes changed')
        require(rows[0]['delay'][18][3] == 1.,
                'canonical delayed accumulation changed')
        require(rows[18]['current'][3] == 1.,
                'canonical arrival accumulation changed')
    if name in ('stimulus_replacement', 'mutant_intrinsics'):
        require(rows[0]['external'] == [48., 24., 0., 0.],
                'initial stimulus changed')
        require(rows[24]['external'] == [0., 12., 0., 0.],
                'replacement stimulus changed')
