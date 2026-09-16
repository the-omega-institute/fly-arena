# Frozen nonlinear-v5 verification supplement v1

This supplement repairs only the saved-truth and receipt-identity verification contract for the already stopped candidate. It does not change the candidate, scientific thresholds, controller or frozen implementation. Integrity verification passes; the scientific candidate still fails.

`verify_v1.py` checks the actual protocol and candidate bytes against the identities recorded in the approved candidate conclusion, then binds the protocol checksum, candidate weight identity, receipt identities and summary identities to those bytes. It requires ordered coverage of all 24 sequences and all four evidence files per sequence. It verifies their receipt hashes and checks each raw stimulus grid and sample times against the frozen protocol before deriving all 24 × 60 × 3 truth values with the frozen, source-verified label helper. Saved truth must be exactly array-equal to derived truth, including the four controls. Metrics are computed from derived truth.

The original verifier contains valuable source/data hashes, encoded input/current checks, complete checkpoint and replay checks, training-statistics/bandwidth/ridge-equation checks, exact DN prediction and silence checks, and prior-evidence preservation checks. Calling it directly would overwrite the old verification report. The supplement therefore parses the hash-pinned source and reuses only `load_protocol` and `verify` in a private namespace. Every assertion in those two functions becomes an explicit `if not ...: raise VerificationError(...)` with its original predicate and line number. Existing NumPy testing calls already raise explicitly. The sole report writer is replaced by a capture function that rejects unexpected or duplicate writes. The metrics function in that namespace checks saved truth against derived truth again and uses derived truth. The frozen module and source remain unchanged; no freeze, fit, analyze, neural run or body entrypoint is called. Binding checks repeat after the inherited verification.

`verification-report-v1.json` records successful complete verification of the actual old evidence under Python `-O`, including the inherited check receipt and all metrics derived from raw truth. It is outside the old evidence tree. It preserves the negative result: pooled sign 75/128 (58.59375%), seven of eight individual sign failures, and maximum absolute neutral mean 0.03127321918706112, above 0.02. No scientific gate or body/retention claim follows from an integrity pass.

`test-results-v1.xml` records 21 passing regression cases. Tampering uses disposable links/copies only; every mutation replaces a link rather than modifying its target. Cases cover corrupted sign/common/trend/control truth paired with a consistently regenerated summary, missing truth and evidence, forged or absent receipt identities, omitted/duplicated sequences, omitted receipt file hashes, altered raw inputs with an updated receipt hash, assertion conversion under optimization, and rejection by an inherited neuron-identity check without an old report write. The actual negative-evidence baseline is also checked.

Reproduce tests with the existing environment and no cache/bytecode writes (use a new owned test directory and result filename):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/fly-arena-approach-v5/verification-supplement-v1:/tmp/fly-arena-approach-v5/src /tmp/fly-arena-approach-v5/.venv/bin/python -B -m pytest -q -p no:cacheprovider /tmp/fly-arena-approach-v5/verification-supplement-v1/test_verify_v1.py --basetemp=/tmp/fly-arena-approach-v5/verification-supplement-v1/test-work-rerun --junitxml=/tmp/fly-arena-approach-v5/verification-supplement-v1/test-results-rerun.xml
```

Run full verification using a new filename in this supplement directory; the CLI refuses to overwrite a report:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/fly-arena-approach-v5/.venv/bin/python -B -O /tmp/fly-arena-approach-v5/verification-supplement-v1/verify_v1.py --report /tmp/fly-arena-approach-v5/verification-supplement-v1/verification-report-rerun.json
```

`preservation-before-v1.json` records size/mtime for 390 existing files, excluding Git/environment internals, and SHA256 for 120 frozen nonlinear evidence/source files. `preservation-report-v1.json` compares these after execution. Prior diagnostic preservation also remains checked by the frozen protocol's metadata snapshot and development hashes. Prohibited log contents were not read; their metadata, where present, is not a content audit. No dependencies were installed. Fresh waveform evidence remains consumed evidence, and reliable approach/capture/retention remains unqualified.
