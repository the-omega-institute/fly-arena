"""Read-only supplement for the stopped, frozen nonlinear-v5 candidate.

The frozen verifier is reused in memory; its assertions become explicit raises
and its sole report write is captured. No fitting or simulation entrypoint runs.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
from flyarena.diagnostics import nonlinear_v5 as frozen

PROTOCOL_SHA256 = 'f8192e152c2b939db662a01c278b1f45376ec76af01516cde531bbdde5e41798'
CANDIDATE_SHA256 = 'b02233e152f8f935ed6a47712e513576729f50117bc079f541a56ec92e2f0989'
SOURCE_SHA256 = '922a048d3d9328bb2bfcce29a77903e221182445cbbea54d9e7f6272bff4eb07'


class VerificationError(ValueError):
    """Evidence does not satisfy the frozen verification contract."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def check_bindings(evidence):
    """Validate all raw sequences before deriving labels, including controls."""
    evidence = Path(evidence)
    protocol_hash = sha256(evidence / 'protocol.json')
    candidate_hash = sha256(evidence / 'candidate.npz')
    require(protocol_hash == PROTOCOL_SHA256, 'Frozen protocol identity mismatch')
    require(candidate_hash == CANDIDATE_SHA256, 'Frozen candidate identity mismatch')
    require((evidence / 'protocol.sha256').read_text().strip() == protocol_hash,
            'Protocol checksum mismatch')
    protocol = read_json(evidence / 'protocol.json')
    require(protocol['candidate']['weights_sha256'] == candidate_hash,
            'Protocol candidate binding mismatch')
    # Validate helpers before using labels/metrics from the frozen implementation.
    require(frozen.sources() == protocol['source_sha256'], 'Frozen source identity mismatch')
    receipt = read_json(evidence / 'run-receipt.json')
    require(receipt.get('protocol_sha256') == protocol_hash, 'Receipt protocol identity mismatch')
    require(receipt.get('candidate_sha256') == candidate_hash, 'Receipt candidate identity mismatch')
    require(receipt['started_unix'] > protocol['created_unix'], 'Execution predates freeze')
    rows = protocol['sequences']
    entries = receipt['sequences']
    require(len(rows) == len(entries) == 24, 'Require all 24 sequences')
    require([row['index'] for row in rows] == list(range(24)), 'Protocol sequence order mismatch')
    require([entry['index'] for entry in entries] == list(range(24)), 'Receipt sequence coverage/order mismatch')
    raw_sequences = []
    for row, entry in zip(rows, entries):
        i = row['index']
        require(entry['id'] == row['id'], f'Sequence {i} identity mismatch')
        required = {f'seq-{i:02d}-{part}.npz' for part in ('samples', 'start', 'middle', 'final')}
        require(set(entry['files']) == required, f'Sequence {i} evidence coverage mismatch')
        for name, expected_hash in entry['files'].items():
            require(sha256(evidence / 'raw' / name) == expected_hash, f'Evidence hash mismatch: {name}')
        with np.load(evidence / 'raw' / f'seq-{i:02d}-samples.npz', allow_pickle=False) as sample:
            raw = sample['raw'].copy()
            require(raw.shape == (60, 2) and np.isfinite(raw).all(), f'Sequence {i} invalid raw grid')
            require(np.array_equal(raw, np.asarray(row['raw'])), f'Sequence {i} raw/protocol mismatch')
            require(np.array_equal(sample['input_start_ms'], protocol['input_start_ms']),
                    f'Sequence {i} input times mismatch')
            require(np.array_equal(sample['response_end_ms'], protocol['response_end_ms']),
                    f'Sequence {i} response times mismatch')
            raw_sequences.append(raw)
    derived_truth = frozen.labels(np.stack(raw_sequences))
    with np.load(evidence / 'predictions.npz', allow_pickle=False) as saved:
        require({'prediction', 'truth', 'silence'} <= set(saved.files), 'Missing prediction/truth/silence evidence')
        require(np.array_equal(saved['truth'], derived_truth), 'Saved truth differs from raw-derived truth')
        expected_metrics = frozen.metrics(saved['prediction'], derived_truth, saved['silence'], protocol)
    summary = read_json(evidence / 'summary.json')
    require(summary.get('protocol_sha256') == protocol_hash, 'Summary protocol identity mismatch')
    require(summary.get('candidate_sha256') == candidate_hash, 'Summary candidate identity mismatch')
    for key, value in expected_metrics.items():
        require(summary.get(key) == value, f'Raw-derived summary mismatch: {key}')
    return protocol, derived_truth, expected_metrics


class ExplicitChecks(ast.NodeTransformer):
    """Preserve each frozen assertion's expression and location under python -O."""

    def visit_Assert(self, node):
        message = ast.Constant(f'Frozen verifier check failed at line {node.lineno}: {ast.unparse(node.test)}')
        replacement = ast.If(test=ast.UnaryOp(op=ast.Not(), operand=node.test),
                             body=[ast.Raise(exc=ast.Call(func=ast.Name(id='VerificationError', ctx=ast.Load()),
                                                         args=[message], keywords=[]), cause=None)],
                             orelse=[])
        return ast.copy_location(replacement, node)


def run_frozen_checks(evidence, derived_truth):
    """Reuse only load_protocol/verify, without editing their source or outputs."""
    source = ROOT / 'src/flyarena/diagnostics/nonlinear_v5.py'
    require(sha256(source) == SOURCE_SHA256, 'Unsupported frozen verifier source')
    tree = ast.parse(source.read_text(), filename=str(source))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in {'load_protocol', 'verify'}]
    require(len(functions) == 2, 'Missing frozen verification functions')
    assertion_count = sum(isinstance(node, ast.Assert) for fn in functions for node in ast.walk(fn))
    module = ast.fix_missing_locations(ExplicitChecks().visit(ast.Module(body=functions, type_ignores=[])))
    require(not any(isinstance(node, ast.Assert) for node in ast.walk(module)), 'Unconverted verification assertion')
    captured = []

    def capture_report(path, value):
        require(Path(path) == Path(evidence) / 'verification.json', 'Unexpected frozen verifier write')
        require(not captured, 'Duplicate frozen verifier report')
        captured.append(value)

    def derived_metrics(prediction, saved_truth, silence, protocol):
        require(np.array_equal(saved_truth, derived_truth), 'Saved truth changed during verification')
        return frozen.metrics(prediction, derived_truth, silence, protocol)

    namespace = dict(vars(frozen))
    namespace.update(OUT=Path(evidence), write_json=capture_report, metrics=derived_metrics,
                     VerificationError=VerificationError)
    exec(compile(module, str(source) + ':read-only-supplement-v1', 'exec', optimize=0), namespace)
    with contextlib.redirect_stdout(io.StringIO()):
        namespace['verify']()
    require(len(captured) == 1 and captured[0].get('passed') is True, 'Frozen verification incomplete')
    return captured[0], assertion_count


def verify(evidence=ROOT / 'var/nonlinear-v5'):
    """Accept integrity of the negative evidence, never imply scientific success."""
    try:
        protocol, truth, expected_metrics = check_bindings(evidence)
        inherited, assertion_count = run_frozen_checks(evidence, truth)
        # Check bindings again after the inherited reads to detect changed inputs.
        _, final_truth, final_metrics = check_bindings(evidence)
        require(np.array_equal(truth, final_truth) and expected_metrics == final_metrics,
                'Evidence changed during verification')
        return dict(schema='nonlinear-v5-verification-supplement/v1', integrity_passed=True,
                    verified_unix=time.time(), evidence_root=str(Path(evidence).resolve()),
                    protocol_sha256=PROTOCOL_SHA256, candidate_sha256=CANDIDATE_SHA256,
                    frozen_verifier_sha256=SOURCE_SHA256, supplement_sha256=sha256(__file__),
                    python_optimization=sys.flags.optimize, raw_sequence_count=len(protocol['sequences']),
                    truth_shape=list(truth.shape), explicit_inherited_checks=assertion_count,
                    inherited_verification=inherited, metrics_from_raw_truth=expected_metrics,
                    scientific_gate_passed=expected_metrics['gate_result']['passed'],
                    decision='STOP remains: no refit, runtime change, simulation or body trial')
    except VerificationError:
        raise
    except (OSError, KeyError, ValueError, TypeError, IndexError, AssertionError) as error:
        raise VerificationError(f'Missing, malformed or inconsistent evidence: {error}') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report_path = args.report.resolve()
    require(report_path.parent == Path(__file__).resolve().parent,
            'Reports must be new files in the supplement directory')
    require(not report_path.exists(), 'Refuse to overwrite a previous report')
    report = verify()
    with report_path.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'integrity_passed': True, 'scientific_gate_passed': report['scientific_gate_passed'],
                      'report': str(report_path)}))


if __name__ == '__main__':
    main()
