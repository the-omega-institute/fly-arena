# DN observability diagnostics, September 2026

These are isolated research tools for a frozen development experiment, not an application decoder or a behavior qualification. The stable MVP remains on `61a89f6`. The two diagnostic panels use the retained 165,122-neuron, 25,563,197-edge connectome and record all 1,314 descending-neuron rates.

The first panel contains 24 × 0.6 seconds of matched terminal clamps, mirrored dynamic stimuli and controls. Fixed linear current/history probes failed the declared weak-contrast criteria. Distinct neural responses were observed, so the failed probes do not establish absence of neural information.

A single fixed Gaussian kernel candidate (alpha 1, causal lags 0/50/100 ms) was trained on the 20 noncontrol development sequences. Its preprocessing, bandwidth, weights and 24 fresh evaluation waveforms were frozen before execution. The fresh result was:

| Measurement | Result | Required |
|---|---:|---:|
| Late weak-contrast sign | 75/128 = 58.59375% | ≥95% |
| Individual nonzero sequences meeting sign gate | 1/8 | 8/8 |
| Maximum absolute neutral sequence mean | 0.03127321918706112 | ≤0.02 |
| Empty late evaluation windows | 0 | 0 |

The candidate stopped. No refit, motor/sensor change, runtime replacement or body trial followed. Common/trend and cue-offset limitations are retained in the raw reports. Reliable approach, capture and sustained feeding remain unresolved.

Protocol SHA256: `f8192e152c2b939db662a01c278b1f45376ec76af01516cde531bbdde5e41798`.
Candidate SHA256: `b02233e152f8f935ed6a47712e513576729f50117bc079f541a56ec92e2f0989`.
Each panel contains 1,440 samples and 72 complete neural checkpoints. Exact replay and training-only fitting were checked. Five original diagnostic tests and four nonlinear tests passed.

The passive contact observer records the existing engine's head, mouth and antenna geometry without changing physics or scoring. Its zero-step check is observation validation, not biological or dynamic feeding validation.

## Frozen evidence and verification

The complete raw panels, checkpoints and trained arrays are retained locally under `/tmp/fly-arena-approach-v5/var/diagnostic-v5` and `var/nonlinear-v5`; they are not included in Git. This branch publishes source and a result summary, not a self-contained signed dataset. The source is intentionally tied to the declared base and frozen experiment; a regenerated panel on another source/environment needs a separately identified protocol and result.

Historical `assay_v5.py` and `nonlinear_v5.py` remain unchanged to preserve their source identities. Their original `verify` commands are historical diagnostics, not production admission gates. For the frozen nonlinear evidence, use the separately versioned [verification supplement](../verification-supplement-v1/README.md), which derives truth from the raw stimuli, checks saved truth and receipt identities, and recomputes metrics. It preserves the prior checks with explicit exceptions that survive optimized Python, in an isolated namespace bound to the exact trusted frozen source. This is not a sandbox for untrusted code.

The supplement's 21 tampering/missing-evidence tests passed, and actual verification under optimized Python produced `integrity_passed=true` and `scientific_gate_passed=false`. Generated verification reports, preservation manifests and test XML remain in the local supplement directory; they are not committed. Reproduction instructions in its README describe that exact local evidence installation. No additional neural panel is required to validate the supplement.

The initial protocol's wider preservation check uses file size/mtime where no content hashes were recorded. Explicitly hashed sources, model, inputs and checkpoints provide the stronger stated checks; metadata alone is not claimed as a complete historical content audit.

No NyxID activation, node configuration, public tunnel or service deployment is included. Future identification work must preserve these failures and define new evidence before changing a sensor, decoder or retention controller.
