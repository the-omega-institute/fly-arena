"""Independent gate: verify raw arrays, frozen policy, source and scientific IDs."""
import json
from dataclasses import asdict
from pathlib import Path
import sys
import platform
import numba
import numpy as np
from cuda_fixtures import NAMES, analytical, fixture, require
from run_cuda_differential import ROOT, identities, observations


def compare(expected, actual, exact=False):
    require(set(expected) == set(actual),
            'observation fields differ')
    for key in expected:
        a, b = np.asarray(expected[key]), np.asarray(actual[key])
        require(a.shape == b.shape, key)
        require(np.isfinite(b).all(), key)
        if key in ('counts', 'refractory', 'tick', 'total_spikes'):
            require(b.dtype.kind in 'iu', key)
        if exact or key in ('counts', 'refractory', 'tick', 'total_spikes'):
            np.testing.assert_array_equal(a, b, err_msg=key)
        else:
            np.testing.assert_allclose(a, b, atol=1e-10, rtol=1e-12, err_msg=key)


def verify(path):
    evidence = json.loads(Path(path).read_text())
    require(evidence['schema'] == 'cuda-differential-evidence/v1',
            'unsupported evidence schema')
    require(evidence['sources'] == identities(), 'source identity changed')
    require(evidence['policy'] == json.loads((ROOT / 'scripts/cuda_policy.json').read_text()),
            'frozen policy changed')
    backend = evidence['backend']
    require(evidence['hardware_status'] == ('EXECUTED/UNQUALIFIED' if backend == 'cuda' else 'NOT RUN/UNQUALIFIED'),
            'hardware status does not match backend')
    runtime = evidence['runtime']
    require(runtime['python'] == sys.version,
            'Python identity changed')
    require(runtime['platform'] == platform.platform(),
            'platform identity changed')
    require(runtime['numpy'] == np.__version__ and runtime['numba'] == numba.__version__,
            'package identity changed')
    require(backend in ('cpu', 'cuda', 'cuda-simulator-diagnostic'),
            'unknown evidence backend')
    expected_ids = {'cpu': 'checked-cpu-numba-v1', 'cuda': 'ordered-numba-cuda-v1-unqualified',
                    'cuda-simulator-diagnostic': 'ordered-numba-cuda-simulator-diagnostic-v1'}
    require(evidence['runtime_id'] == expected_ids[backend],
            'runtime identity does not match backend')
    if backend == 'cuda':
        require(runtime['device'] is not None and runtime['simulator'] is False,
                'real CUDA evidence requires a device and forbids simulator mode')
    elif backend == 'cuda-simulator-diagnostic':
        require(runtime['device'] is None and runtime['simulator'] is True,
                'simulator evidence requires simulator mode and no device')
    else:
        require(runtime['device'] is None,
                'CPU evidence must not claim a CUDA device')
    require(set(evidence['fixtures']) == set(NAMES),
            'fixture set is incomplete or unexpected')
    for name in NAMES:
        entry = evidence['fixtures'][name]
        oracle = fixture(name)
        require(entry['binding'] == asdict(oracle.binding),
                'scientific binding changed')
        recomputed = observations(name, oracle)
        analytical(name, recomputed)
        for series in ('oracle', 'candidate', 'repeat'):
            rows = entry[series]
            require(len(rows) == 48,
                    'series must contain 48 observations')
            analytical(name, rows)
            for i in range(48):
                compare(recomputed[i], rows[i])
        for a,b in zip(entry['candidate'], entry['repeat']):
            compare(a, b, exact=True)
        require(len(entry['restored_suffix']) == 29,
                'restored suffix must contain 29 observations')
        for a,b in zip(entry['candidate'][19:], entry['restored_suffix']):
            compare(a, b, exact=True)
        require([(c['start'], c['steps']) for c in entry['chunks']] == [(0,7),(7,17),(24,11),(35,13)],
                'uneven chunk schedule changed')
        for chunk in entry['chunks']:
            start, steps = chunk['start'], chunk['steps']
            expected = dict(entry['candidate'][start + steps - 1])
            expected['counts'] = np.sum([r['counts'] for r in entry['candidate'][start:start+steps]], axis=0).tolist()
            compare(expected, chunk['observation'], exact=True)
    return {'verdict': 'tiny-neural-contracts-pass', 'backend': backend,
            'hardware_status': evidence['hardware_status'], 'fixtures': len(NAMES)}


if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1])))
