# Motor qualification v4 admission contract

`flyarena.experiments.qualification` is the shared evaluator for production bridge admission and `scripts/qualify_integration_v2.py`. Qualification is derived from verified observations on each read. Neither a summary's self-digest nor its claimed gate values establishes readiness.

Public interface:

```python
SCHEMA = 'motor-qualification/v4'
CASES  # tuple of (name, probe_id, seed, seconds, options)
build_qualification(root: Path, expected_profile: dict) -> dict
verify_qualification(path: Path, expected_profile: dict) -> dict
```

The builder reads existing evidence and returns a document; it never runs trials or writes files. The verifier validates the complete document, calls the same builder against the sibling trial directories, and compares canonical JSON without coercion. Invalid evidence raises `ValueError`. A complete, faithfully reported **failed** cohort returns its false gates; callers must require every gate to be exactly `True`. Bridge admission does this for both matches and tournaments, while keeping legacy replay semantics.

The exact trial contract is:

| Name | Probe | Seed | Seconds | Options |
| --- | --- | ---: | ---: | --- |
| heldout-left | gradient-v2 | 20042 | 10 | normal stimulus, no ablation |
| heldout-right | gradient-v2 | 20043 | 10 | normal stimulus, no ablation |
| heldout-repeat | gradient-v2 | 20042 | 10 | normal stimulus, no ablation |
| bifurcation-left | bifurcation-v2 | 20044 | 10 | normal stimulus, no ablation |
| bifurcation-right | bifurcation-v2 | 20045 | 10 | normal stimulus, no ablation |
| blank | gradient-v2 | 20042 | 3 | stimulus=blank |
| output-ablation | gradient-v2 | 20042 | 3 | ablation=output |
| delayed-cue | delayed-cue-v2 | 20042 | 3 | normal stimulus, no ablation |

All trials require decoder v2, the same ready `dn-cpg-*-v4` profile, the current complete runtime source closure, and the unchanged generated scene for the specified probe and seed. The evaluator pins the existing canonical unmodified WT artifact `aaf1fb32e763e7bda8b34bea1519e1041e9b73b07bed6b5dc1c4552840785bd7`, trusted reference ID `0c136a17a43c84c2eb32539454285783`, and retained MaleCNS graph (165122 neurons / 25563197 edges). These identities are established by the preexisting canonical compiler/reference artifacts, not display names or caller-supplied labels. A different scientific graph or baseline requires a separately versioned policy.

The unchanged 15 acceptance predicates are:

- Each gradient: at least eight seconds, closest body distance below 1.8 mm and positive food intake; mirrored yaw change at 0.5 seconds greater than 0.05 radians. The contract requires the full ten-second trial.
- Each fork: correct branch and positive intake; minimum upright z greater than 0.8.
- Repeated gradient: exactly equal trajectory and neural trace.
- Blank and output ablation: exactly equal passive trajectories; each has mean drive below 1e-8 and displacement below 0.25 mm.
- Delayed cue: post-cue mean drive below 0.05.
- Every trial: more than 100000 neurons, with the pinned retained graph identity and counts additionally enforced.
- Final source: actual source closure and evaluator file remain unchanged across verification.

Before evaluating those predicates, the policy verifies receipt/file hashes, checkpoint horizons and neural totals, complete 10 ms observation grids, exact subject/profile/scene/conditions, numeric observation types, and recomputed metrics. Missing or unknown fields, gates, trials, conditions or schemas are rejected. Boolean/numeric/string substitutions, duplicate JSON keys, nonfinite values, incomplete checkpoints and redirected evidence symlinks are rejected. The document contains exactly `schema_version`, `profile_sha256`, `policy_sha256`, `checks`, `receipts`, `metrics`, `measured`, and `sha256`. `policy_sha256` is the evaluator file's SHA-256; `sha256` is the canonical digest of all other fields. The runtime profile also binds the evaluator, bridge, receipt verifier and metric implementation through the full scientific source closure.

`bridge.QUALIFICATION` and the qualification script's default output root point to `var/research-validation/qualification-v4/final/qualification.json`. The script refuses an existing output root, runs the shared cases, builds and verifies the document, then retains its real HTTP experiment and arena diagnostic workflow. With `--output`, its process-local bridge uses the selected evidence path. This does not activate that alternate path in another service.

The historical `var/research-validation/integration-v2-engine/final` v3 evidence remains immutable and independently verifiable under its recorded profile. Its 12/15 result does not qualify a v4 candidate. A missing, failed or malformed new proof leaves research-v2 admission unavailable. The policy worker does not run the new held-out cohort: the motor worker must wait for root's `var/sshx/research-upgrade/policy-v3-frozen.json`, freeze scientific sources, then execute the qualification script once.

The checkpoint verifier dispatches on the receipt's declared `malecns-lif-cpu-v1` model, `neurofly-mujoco-v1` embodiment, FlyGym 2.1.0 and MuJoCo 3.9.0 versions under `probe-receipt/v2`. Unknown or missing versions fail closed. This existing version combination defines the complete layout; no historical metadata is rewritten and no dimensions are inferred from submitted arrays. Neural state requires float64 voltage/current/external/rates vectors, a `(19, neuron_count)` float64 delay buffer, an int32 refractory vector, and scalar int64 tick/spike counters. Solo physical state requires the 752-element float64 `mjSTATE_INTEGRATION` vector, `(1,2)` float64 drives, scalar int64 tick, four six-element float64 controller/CPG vectors, and six int64 retraction persistence counters. Every field must be present, with no extras, and all values must be finite. Integer metadata, state bounds, integration time, terminal drives and neural totals are also checked before evidence acceptance.

This is a verifier-only contract repair. It changes the runtime source closure and evaluator hash, without changing the motor, sensor, decoder, body, graph, thresholds or scientific gates. Historical complete receipts remain verifiable under their original declared versions; their recorded profiles and source archives remain historical. The frozen v4 cohort still records 12/15 gates and cannot qualify the repaired source. Research-v2 competition remains unavailable; receipt integrity does not establish current-source qualification. No held-out cohort was rerun for this repair.

Repair verification recorded profile SHA-256 `6f38218dde2dc8a3e70736a0514c0553e109910125badf12cd103afd650e75dd` and evaluator SHA-256 `0d1073601da530d5b6bf1930e5a8cd90639f3e796320f4d611fbad01ea4faffc` in the installed CPU environment. These identify the repaired source; they do not relabel any historical receipt or establish a new behavioral qualification.

Regression fixtures contain explicitly synthetic full-horizon observations and complete state from the real neural and physical checkpoint emitters, with synthetic horizon/terminal-drive assignments. They exercise the real file/receipt verifier and both HTTP admission paths with a patched synthetic source provider. Rehashed missing fields, bad shapes/dtypes, nonfinite state, fractional/boolean counters, integration-clock and drive mismatches, and unknown versions are rejected through research verification and match/tournament admission. These are contract tests, not scientific evidence or a motor performance claim.
