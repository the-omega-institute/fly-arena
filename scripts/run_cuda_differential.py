"""Bounded evidence writer. CUDA selection never silently becomes a simulator."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import numba
import numpy as np
from flyarena.optional_backend import CheckedCPUBackend, create_backend
from cuda_fixtures import NAMES, fixture, snapshot, stimulus

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('src/flyarena/neural.py', 'src/flyarena/optional_backend.py', 'src/flyarena/cuda_ordered.py',
           'scripts/cuda_fixtures.py', 'scripts/cuda_policy.json', 'scripts/run_cuda_differential.py',
           'scripts/verify_cuda_differential.py')


def identities():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def observations(name, backend):
    rows = []
    for tick in range(48):
        backend.stimulate(*stimulus(name, tick))
        rows.append(snapshot(backend, backend.advance(1)))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=('cpu', 'cuda', 'cuda-simulator-diagnostic'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads((ROOT / 'scripts/cuda_policy.json').read_text())
    candidate = lambda graph, **kw: create_backend(args.backend, graph, **kw)
    first = fixture(NAMES[0], candidate)  # fail closed before writing an evidence artifact
    device = None
    if args.backend == 'cuda':
        from numba import cuda
        d = cuda.get_current_device()
        device = {'name': str(d.name), 'compute_capability': list(d.compute_capability),
                  'device_id': d.id, 'uuid': str(getattr(d, 'uuid', 'unavailable'))}
    report = {'schema': 'cuda-differential-evidence/v1', 'backend': args.backend,
              'runtime_id': first.runtime_id, 'sources': identities(), 'policy': policy,
              'runtime': {'python': sys.version, 'platform': platform.platform(),
                          'numpy': np.__version__, 'numba': numba.__version__,
                          'simulator': bool(numba.config.ENABLE_CUDASIM), 'device': device},
              'hardware_status': 'EXECUTED/UNQUALIFIED' if args.backend == 'cuda' else 'NOT RUN/UNQUALIFIED', 'fixtures': {}}
    started = time.perf_counter()
    for name in NAMES:
        oracle, actual = fixture(name), fixture(name, candidate)
        entry = {'binding': asdict(actual.binding), 'oracle': observations(name, oracle),
                 'candidate': observations(name, actual)}
        entry['repeat'] = observations(name, fixture(name, candidate))
        chunked = fixture(name, candidate)
        chunks = []
        for start, steps in ((0, 7), (7, 17), (24, 11), (35, 13)):
            chunked.stimulate(*stimulus(name, start))
            chunks.append({'start': start, 'steps': steps, 'observation': snapshot(chunked, chunked.advance(steps))})
        entry['chunks'] = chunks
        restored = fixture(name, candidate)
        for tick in range(19):
            restored.stimulate(*stimulus(name, tick))
            restored.advance(1)
        saved = restored.checkpoint()
        restored.advance(3)
        restored.restore(saved)
        suffix = []
        for tick in range(19, 48):
            restored.stimulate(*stimulus(name, tick))
            suffix.append(snapshot(restored, restored.advance(1)))
        entry['restored_suffix'] = suffix
        report['fixtures'][name] = entry
    report['elapsed_seconds_diagnostic_only'] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, allow_nan=False))
    print(json.dumps({'evidence': str(args.output), 'backend': args.backend,
                      'hardware_status': report['hardware_status']}))


if __name__ == '__main__':
    main()
