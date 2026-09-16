"""Tampering occurs only in disposable links/copies under this owned directory."""
import ast
import json
from pathlib import Path

import numpy as np
import pytest

import verify_v1 as verifier

EVIDENCE = verifier.ROOT / 'var/nonlinear-v5'


@pytest.fixture
def evidence(tmp_path):
    for name in ('protocol.json', 'protocol.sha256', 'candidate.npz', 'run-receipt.json',
                 'predictions.npz', 'summary.json'):
        (tmp_path / name).symlink_to(EVIDENCE / name)
    raw = tmp_path / 'raw'
    raw.mkdir()
    for source in (EVIDENCE / 'raw').iterdir():
        if source.suffix == '.npz':
            (raw / source.name).symlink_to(source)
    return tmp_path


def replace_json(path, value):
    path.unlink()
    path.write_text(json.dumps(value))


def replace_npz(path, value):
    path.unlink()
    np.savez_compressed(path, **value)


def saved_arrays(evidence):
    with np.load(evidence / 'predictions.npz', allow_pickle=False) as arrays:
        return dict(arrays)


def test_actual_truth_and_negative_metrics(evidence):
    protocol, truth, metrics = verifier.check_bindings(evidence)
    verifier.require(truth.shape == (24, 60, 3), 'Must derive every sequence and head')
    gate = metrics['gate_result']
    verifier.require(gate['pooled_sign'] == 75 / 128, 'Actual negative sign result changed')
    verifier.require(gate['neutral_max_absolute_mean'] == 0.03127321918706112,
                     'Actual neutral result changed')
    verifier.require(gate['passed'] is False, 'Candidate must remain stopped')


@pytest.mark.parametrize('sequence,head', [(0, 0), (0, 1), (12, 2), (23, 1)])
def test_corrupt_truth_and_consistently_regenerated_summary_reject(evidence, sequence, head):
    arrays = saved_arrays(evidence)
    arrays['truth'][sequence, :, head] += 1
    protocol = verifier.read_json(evidence / 'protocol.json')
    forged_metrics = verifier.frozen.metrics(arrays['prediction'], arrays['truth'], arrays['silence'], protocol)
    summary = verifier.read_json(evidence / 'summary.json')
    summary.update(forged_metrics)
    replace_npz(evidence / 'predictions.npz', arrays)
    replace_json(evidence / 'summary.json', summary)
    # Demonstrate the old saved-truth metric comparison accepts the forged pair.
    for key, value in forged_metrics.items():
        verifier.require(summary[key] == value, 'Attack fixture must satisfy old metric comparison')
    with pytest.raises(verifier.VerificationError, match='Saved truth differs'):
        verifier.verify(evidence)


def test_missing_truth_reject(evidence):
    arrays = saved_arrays(evidence)
    del arrays['truth']
    replace_npz(evidence / 'predictions.npz', arrays)
    with pytest.raises(verifier.VerificationError, match='Missing prediction/truth/silence'):
        verifier.verify(evidence)


@pytest.mark.parametrize('name', ['predictions.npz', 'summary.json', 'run-receipt.json',
                                  'raw/seq-23-samples.npz', 'raw/seq-07-middle.npz'])
def test_missing_evidence_reject(evidence, name):
    (evidence / name).unlink()
    with pytest.raises(verifier.VerificationError, match='Missing, malformed or inconsistent evidence'):
        verifier.verify(evidence)


@pytest.mark.parametrize('field', ['protocol_sha256', 'candidate_sha256'])
@pytest.mark.parametrize('missing', [False, True])
def test_receipt_identity_mismatch_or_missing_reject(evidence, field, missing):
    receipt = verifier.read_json(evidence / 'run-receipt.json')
    if missing:
        del receipt[field]
    else:
        receipt[field] = '0' * 64
    replace_json(evidence / 'run-receipt.json', receipt)
    with pytest.raises(verifier.VerificationError, match='Receipt .* identity mismatch'):
        verifier.verify(evidence)


@pytest.mark.parametrize('change', ['omit_sequence', 'duplicate_sequence', 'omit_sample_hash'])
def test_incomplete_receipt_coverage_reject(evidence, change):
    receipt = verifier.read_json(evidence / 'run-receipt.json')
    if change == 'omit_sequence':
        receipt['sequences'].pop()
    elif change == 'duplicate_sequence':
        receipt['sequences'][-1] = receipt['sequences'][0]
    else:
        del receipt['sequences'][23]['files']['seq-23-samples.npz']
    replace_json(evidence / 'run-receipt.json', receipt)
    with pytest.raises(verifier.VerificationError, match='24 sequences|coverage'):
        verifier.verify(evidence)


def test_corrupt_raw_even_with_updated_receipt_hash_reject(evidence):
    path = evidence / 'raw/seq-23-samples.npz'
    with np.load(path, allow_pickle=False) as saved:
        arrays = dict(saved)
    arrays['raw'][0, 0] += 1
    replace_npz(path, arrays)
    receipt = verifier.read_json(evidence / 'run-receipt.json')
    receipt['sequences'][23]['files'][path.name] = verifier.sha256(path)
    replace_json(evidence / 'run-receipt.json', receipt)
    with pytest.raises(verifier.VerificationError, match='raw/protocol mismatch'):
        verifier.verify(evidence)


def test_inherited_assertion_conversion_survives_optimization():
    tree = ast.parse('def check():\n    assert False, "must reject"\n')
    tree = ast.fix_missing_locations(verifier.ExplicitChecks().visit(tree))
    namespace = {'VerificationError': verifier.VerificationError}
    exec(compile(tree, '<regression>', 'exec', optimize=2), namespace)
    with pytest.raises(verifier.VerificationError, match='Frozen verifier check failed'):
        namespace['check']()


def test_full_verification_rejects_inherited_failure_without_report_write(evidence):
    # Bindings still pass, but the old verifier's identity check must reject.
    path = evidence / 'raw/neuron-identities.npz'
    with np.load(path, allow_pickle=False) as saved:
        arrays = dict(saved)
    arrays['dn_index'][0] = -1
    replace_npz(path, arrays)
    with pytest.raises(verifier.VerificationError, match='Frozen verifier check failed'):
        verifier.verify(evidence)
    verifier.require(not (evidence / 'verification.json').exists(), 'Verifier must not write old report')
