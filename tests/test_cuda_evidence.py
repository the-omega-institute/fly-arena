"""Evidence verifier must reject corrupted raw observations and provenance."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_cuda_differential import verify


@pytest.fixture(scope='module')
def evidence(tmp_path_factory):
    folder = tmp_path_factory.mktemp('cuda-evidence')
    path = folder / 'evidence.json'
    subprocess.run([sys.executable, 'scripts/run_cuda_differential.py', '--backend', 'cpu', '--output', str(path)], check=True, capture_output=True)
    assert verify(path)['verdict'] == 'tiny-neural-contracts-pass'
    return json.loads(path.read_text()), folder


TAMPER_TARGETS = ['candidate', 'repeat', 'restored_suffix', 'chunks', 'binding',
    'sources', 'policy', 'hardware', 'runtime', 'omitted_fixture', 'oracle',
    'schema', 'python', 'platform', 'numpy', 'numba', 'device', 'backend',
    'series_length', 'suffix_length', 'chunk_schedule', 'float_counts',
    'row_keys', 'row_shape', 'nonfinite', 'simulator_metadata']


def tampered_path(evidence, target):
    original, folder = evidence
    bad = copy.deepcopy(original)
    entry = bad['fixtures']['silent']
    if target in ('candidate','repeat','oracle'):
        entry[target][0]['counts'][0] = 1
    elif target == 'restored_suffix': entry[target][0]['delay'][0][0] = 1
    elif target == 'chunks': entry['chunks'][0]['observation']['v'][0] += 1e-12
    elif target == 'binding': entry['binding']['threshold_mv'] = -44
    elif target == 'sources': bad['sources']['src/flyarena/neural.py'] = '0'*64
    elif target == 'policy': bad['policy']['atol'] = 1
    elif target == 'hardware': bad['hardware_status'] = 'QUALIFIED'
    elif target == 'runtime': bad['runtime_id'] = 'actual-cuda'
    elif target == 'omitted_fixture': del bad['fixtures']['silent']
    elif target == 'schema': bad['schema'] = 'forged'
    elif target in ('python', 'platform', 'numpy', 'numba'): bad['runtime'][target] = 'forged'
    elif target == 'device': bad['runtime']['device'] = {'name': 'forged'}
    elif target == 'backend': bad['backend'] = 'forged'
    elif target == 'series_length': entry['repeat'].pop()
    elif target == 'suffix_length': entry['restored_suffix'].pop()
    elif target == 'chunk_schedule': entry['chunks'][0]['steps'] = 6
    elif target == 'float_counts': entry['candidate'][0]['counts'] = [0.] * 4
    elif target == 'row_keys': del entry['candidate'][0]['rates']
    elif target == 'row_shape': entry['candidate'][0]['rates'] = [0.] * 3
    elif target == 'nonfinite': entry['candidate'][0]['rates'][0] = float('nan')
    elif target == 'simulator_metadata':
        bad['backend'] = 'cuda-simulator-diagnostic'
        bad['runtime_id'] = 'ordered-numba-cuda-simulator-diagnostic-v1'
        bad['runtime']['simulator'] = False
    path = folder / (target + '.json')
    path.write_text(json.dumps(bad))
    return path


@pytest.mark.parametrize('target', TAMPER_TARGETS)
def test_verifier_rejects_tampering(evidence, target):
    with pytest.raises((ValueError, AssertionError)):
        verify(tampered_path(evidence, target))


@pytest.mark.parametrize('target', TAMPER_TARGETS)
def test_optimized_verifier_rejects_tampering(evidence, target):
    result = subprocess.run([sys.executable, '-O', 'scripts/verify_cuda_differential.py',
        str(tampered_path(evidence, target))], capture_output=True, text=True)
    assert result.returncode != 0, result.stdout
    assert 'tiny-neural-contracts-pass' not in result.stdout
    assert 'ValueError' in result.stderr or 'AssertionError' in result.stderr, result.stderr


def test_optimized_verifier_accepts_valid_evidence(evidence):
    _, folder = evidence
    result = subprocess.run([sys.executable, '-O', 'scripts/verify_cuda_differential.py',
        str(folder / 'evidence.json')], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == {'verdict': 'tiny-neural-contracts-pass',
        'backend': 'cpu', 'hardware_status': 'NOT RUN/UNQUALIFIED', 'fixtures': 7}


def test_optimized_analytical_checks_reject_wrong_semantics(evidence):
    _, folder = evidence
    # Exercise analytical refusal directly: differential comparisons could otherwise
    # mask a stripped analytical gate by rejecting the same corrupted observations.
    code = '''
import json, sys
sys.path.insert(0, 'scripts')
from cuda_fixtures import analytical
rows_by_name = json.load(open(sys.argv[1]))['fixtures']
for name, field, tick, value in (
    ('silent', 'total_spikes', 0, 1),
    ('threshold_above_rest', 'total_spikes', 0, 1),
    ('threshold_exact', 'counts', 0, [0, 0, 0, 0]),
    ('delay_self_inhibitory', 'current', 18, [0., 0., 0., 0.]),
    ('ordered_cancellation', 'current', 18, [0., 0., 0., 0.]),
    ('stimulus_replacement', 'external', 24, [48., 24., 0., 0.]),
    ('mutant_intrinsics', 'external', 24, [48., 24., 0., 0.]),
):
    rows = rows_by_name[name]['oracle']
    analytical(name, rows)
    rows[tick][field] = value
    try:
        analytical(name, rows)
    except ValueError:
        continue
    raise SystemExit('analytical check accepted corruption: ' + name)
print('seven analytical refusals under -O')
'''
    result = subprocess.run([sys.executable, '-O', '-c', code, str(folder / 'evidence.json')],
        check=True, capture_output=True, text=True)
    assert result.stdout.strip() == 'seven analytical refusals under -O'
