# Sensorimotor research v2

This is an **engineering sensorimotor approximation** on the full retained MaleCNS graph, embodied in a solo FlyGym/NeuroMechFly MuJoCo body. It does not validate biological navigation, biological metabolism, learning, or memory. CUDA is unavailable until a real device adapter passes differential qualification.

The v1 neural equations, v1 body, and original `data/connectome/readout.{json,npz}` remain unchanged. `runner.py` dispatches explicitly: absent/legacy profile requests retain the committed v1 bilateral encoder and readout, while research-profile requests use the versioned bridge. V2 wraps the same neural integrator and body under separate sensor/readout/probe identities. The body exposes **two bilateral action channels**. Speed/turn are a reparameterization of those channels, not additional degrees of freedom.

## Sensor and frozen decoder

Only the two local chemical measurements enter the sensor wrapper. Summed raw sources are not individually clipped before contrast. Common concentration uses half saturation at 0.3; normalized bilateral contrast is amplified with a bounded tanh; a single shared normalization retains its sign. The sensor is stateless, so it cannot maintain a hidden cue memory. Zero cue injects zero sensory current. This wrapper does not change `Brain.stimulate`, whose tonic current remains part of v1.

The engineering choice is a Gaussian kernel ridge decoder of **all annotated descending-neuron rates**, fitted once on baseline neural responses to a fixed raw-concentration grid and cue-removal transients. Its width and regularization are selected only by grouped cross-validation on calibration stimuli and then frozen. Targets couple concentration to drive magnitude and bilateral contrast to action asymmetry. At runtime the decoder receives only DN rates; it has no odor, time, fly pose, world coordinates, food location, or task input. Neural silence has zero motor authority. The physical action convention is measured: `[1,.2]` produces negative yaw and `[.2,1]` positive yaw. Therefore left-high chemical calibration targets right-high action.

Calibration uses no evaluation trajectories, player mutations, or held-out task seeds. Independent concentration pairs test directional signs, absent-cue stopping, monotone concentration-dependent speed, bounded prediction error, and neutral-cue asymmetry. Weak bilateral contrasts are explicitly represented in calibration and held-out checks. A failed gate leaves `profile_manifest().ready` false. Profile reads never calibrate or instantiate a brain/body. Preparation is an explicit operation, and an existing v2 folder is never overwritten.

## Protocols and evidence

- `gradient-v2`: the fly starts facing +X, with food off axis at approximately `(7, ±5)`. Adjacent even/odd seeds share source jitter with mirrored Y. This is an analytic Gaussian local concentration fixture that penetrates walls, not simulated odor diffusion.
- `bifurcation-v2`: a central physical barrier and outer walls leave two wide traversable branches. The versioned integration fixture uses a food-centered Gaussian source (sigma X=9 mm, Y=6 mm) to bias one branch; historical receipts preserve the previous imposed diagonal field. Branch choice is measured after X ≥ 9.5 mm and |Y| ≥ 3.5 mm; no crossing means no choice. The chemical fixture is explicitly imposed by the experimenter.
- `delayed-cue-v2`: cue is absent before 0.25 seconds, present from 0.25 to 1.0 seconds, then exactly absent. Transient neural/motor persistence is measured without interpreting it as memory.

`run_probe(fly, probe_id, seed, duration_seconds, output, *, data=DATA, var=VAR)` loads and verifies the compiled artifact, full graph and readout, instantiates the CPU backend and one real MuJoCo body, and advances both at 0.1 ms with a 10 ms sensory/action boundary. Optional diagnostic arguments are `ablation='output'`, `stimulus='blank'`, and `decoder_version='v1'`; each changes the frozen condition key and is never ranked as a normal trial. These flags do not change the artifact.

Every 10 ms sample records measured thorax position and rotation-derived yaw, raw and encoded chemical levels, population rates, unsmoothed commands, applied drives, game energy, intake, and actual wall-contact ticks. Contacts inspect MuJoCo contact geom IDs, never proximity surrogates. A solo body has no opponent contact. Intake is a declared 10 ms mouth-distance/height rule. Food latency is null when no food was consumed. Game energy is an accounting reserve, not physiological energy.

A run directory is immutable through this API: any existing content is rejected. It contains `scene.json`, `evidence.json`, `events.json`, complete neural and physics checkpoints, `receipt.json`, and `report.json`. The receipt binds scientific sources, dependency versions, FlyGym packaged body/controller/mesh/configuration files, environment, graph/readout identities, scene, horizon/grid, artifact/weights, and evidence file hashes. Subject identity and weights appear in the receipt **outside** `conditions`; condition keys are therefore shared across matched subjects. The complete report is emitted only after file hashes, condition identity, time grid and recomputed metrics match evidence.

The required exports are in `flyarena.experiments.probes`: `probe_catalog`, `profile_manifest`, `run_probe`. Returned trajectories contain `{time,x,y,yaw}`. Additional body diagnostics live in `neural_trace` to preserve platform report contracts. `verify_evidence(path, report)` permits independent verification of emitted evidence and report correspondence. The platform worker owns experiment orchestration and comparison integration.

Checkpoint acceptance now requires the complete versioned neural and physical state, including delay/current/refractory/rates/external arrays, MuJoCo integration state, bilateral drives and all emitted hybrid-controller/CPG arrays. Field sets, shapes, dtypes, finite values, exact integer scalars and terminal-state correspondence are validated even when an attacker rehashes all files and receipts. Dispatch uses the model/body/dependency versions already declared by `probe-receipt/v2`; unknown layouts fail closed. See [the qualification contract](QUALIFICATION_V4.md) for the exact supported layout. This verifier-only repair changes the profile/evaluator source identity. Old complete receipts remain independently verifiable against their original declared versions, but neither old sources nor their failed cohorts are relabeled as current evidence. Motor behavior and scientific thresholds are unchanged, and research-v2 competition stays disabled.

## Prepare, validate, and transfer

Run from the repository with its installed environment:

```sh
OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/calibrate_v2.py
OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/research_probe.py --validate --duration 2 --output var/research-validation/engineering-v2-final
.venv/bin/python -m pytest tests/test_backend.py tests/test_probes.py -q
```

Calibration writes only new ignored `data/connectome/research-v2/readout.npz` and `readout.json`. Transfer **both files together** to the same relative directory on the remote machine, alongside the unchanged graph, required package environment, and matching science sources. Do not rerun calibration remotely if using this qualified frozen readout. Compare `profile_manifest()` hashes after transfer. A changed model, encoder, backend or decoder source invalidates readout readiness; use a separately versioned release and fresh data root for recalibration. No preparation or transfer command activates authentication or deploys an external service.

For a single precompiled Fly dictionary:

```sh
.venv/bin/python scripts/research_probe.py --fly /path/to/fly.json --probe gradient-v2 --seed 42 --duration 3 --output var/research-validation/new-trial
```

The acceptance script runs matched WT, duplicate WT, mirrored cue, intrinsic threshold mutation, output ablation, v2 blank, v1 blank, cue-offset bifurcation trials, and two unused mirrored seed trials sequentially. It persists measured metrics, matched trajectory divergence and receipt hashes to `summary.json`. A mutation is allowed to have no measurable effect; nonzero divergence is not evidence of advantage. The development seeds are 42/43; the final untouched task seeds are 10042/10043, separate from calibration/reset seeds. Short horizons may produce no branch choice or food intake and are reported honestly.

The readout transfer hashes are recorded in `var/research-validation/readout-transfer-manifest.json`. `scripts/research_diagnostics.py` emits raw sensor saturation examples and transparent held-out readout diagnostics. `scripts/research_plot.py <validation-directory>` renders measured trajectories after verifying every included receipt. The local locomotion controller retains its existing leg/contact reflex observations; the new neural interface adds no contact or visual sensory inputs.

## Historical v2 decoder and original-transfer evidence

These preserved receipts qualify the earlier transfer only; they do not qualify the current motor v3 candidate.

`var/research-validation/engineering-v2-final/summary.json` binds 11 actual two-second full-graph/MuJoCo trials and 14 passing engineering checks. The readout's mean independent held-out command MAE is 0.06488; all directional, zero-cue, concentration-speed, neutral-bias and aggregate-error gates passed.

| Measured check | Result |
| --- | --- |
| Development left/right yaw at 0.5 s | +0.36511 / −0.56916 rad |
| Unused-seed left/right yaw at 0.5 s | +0.26880 / −0.50868 rad |
| Duplicate WT trajectory and neural trace | Exactly equal |
| +1 mV threshold mutation mean matched trajectory divergence | 1.97971 mm; not an advantage claim |
| Blank v2 applied action | Exactly zero; trajectory exactly equals output ablation |
| Blank v2 / v1 path over 2 s | 0.41073 / 28.72608 mm |
| Passive zero-action endpoint drift | 0.11955 mm; retained as physical settling, not zero-filled |
| Mean action after cue offset plus 0.3 s | 0.00579 |
| Revised bifurcation | Cued branch; intake begins 1.87 s; minimum upright Z 0.99114 |

The accepted fork run has zero wall-contact time because it traverses the open branch. The preserved earlier fork audit records real contact events and an overturning failure, which motivated widening the fixture; it is not accepted as successful navigation. Final emitted receipt sources match the saved source snapshot. Older development evidence and both v1 readout files are preserved. The final matched left-cue run has null food latency, while right-cue and bifurcation trials consume food; no censored latency is converted to zero. These are engineering checks with a small seed set, not broad behavioral or biological qualification.

Final validation including recorded evidence and platform report parsing:

```sh
ARENA_SCIENCE_EVIDENCE=var/research-validation/engineering-v2-final OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest tests/test_backend.py tests/test_probes.py tests/test_core.py -q
```


## Integration motor transfer and arena boundary

The frozen decoder, sensor, CPU wrapper and both original/prepared readout assets remain byte-identical. The new `dn-cpg-asymmetry-v3` transfer operates only on the two decoded neural commands and fixed motor filter state. It receives no sensors, time, pose, goal, energy or world coordinates. A fixed prefilter smooths decoded commands, bounded normalized asymmetry amplifies turns, and a common-amplitude cap plus turn slowing reflects measured CPG body response. This remains a two-channel engineered approximation.

The supplied body-dose audit is preserved at `var/research-validation/integration-v2-engine/motor-dose-audit.json`; its SHA-256 is frozen in the motor configuration. At common amplitude 0.6, bilateral differences 0.2, 0.4 and 0.6 produced approximately 0.55, 1.09 and 1.66 rad over 0.8 seconds. Lower common amplitude reduced translation while retaining turning. These measurements motivated a bounded transfer; they do not establish a hard actuator dead zone. Development pilots use seed 42 and remain separate from held-out qualification.

`probe-protocol-v3` identifies the updated experiment runtime while stable UI probe IDs remain `gradient-v2`, `bifurcation-v2`, and `delayed-cue-v2`. The profile exposes explicit motor/protocol IDs, actual CPU backend, and a hash of the full Python source and scientific dependency closure. Altered transfer or probe source changes the profile and invalidates old admissions, caches and motor qualifications. Existing historical receipts remain independently verifiable under their recorded identity. Prepared readout training identities are not rewritten to hide changes.

Arena `sensorimotor-research-v2` uses the same backend/encoder/frozen decoder/motor transfer as probes, plus existing physical competition rules. `arena-offaxis-v2` adds fixed 0.65 rad spawn-heading offsets without consulting targets. Raw summed chemical channels remain unclipped before bilateral encoding. Legacy scenes and runtime interpretation remain intact. Probe intake uses its declared 10 ms observation rule; arena intake retains the original per-physics-tick conservation rule, and both policies are frozen in receipts.

New match admission is fail-closed until `var/research-validation/integration-v2-engine/final/qualification.json` verifies against the current profile and all held-out gates. Qualification requires ten-second mirrored approach with actual food intake, early directional response, deterministic repeated trajectory/trace, both ten-second bifurcation choices with food and upright bodies, blank/passive ablation and cue-offset stopping. The API returns an explicit unavailable reason if any gate or source binding fails. This qualification is local to the recorded platform/environment and does not establish biological navigation or portable GPU equivalence.

Run the complete independent integration acceptance from a fresh output directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -u scripts/qualify_integration_v2.py
```

It runs full-graph probes, saves their immutable receipts, creates a real design through the HTTP application, runs the automatically scheduled WT/official/design experiment through the isolated durable job, and executes solo/dual v2 arena matches with receipt verification and HTTP replay checks when qualified. It uses a separate SQLite/artifact root and no listening socket, leaving existing private services alone. CPU is the actual neural backend. CUDA remains unavailable; NyxID remains disabled and no external service is activated.

The prior diagonal branch field increased forever away from food; increasing turn fidelity exposed that fixture mismatch. `gaussian-branch-source-v3` explicitly replaces it with a local source centered on receipted food. Gaussian sensory sampling uses antenna positions as part of the world model; neither the decoder nor motor transfer receives those positions. No legacy receipt geometry/stimulus is rewritten.

## Final integration result: competition qualification remains unavailable

The final-source CPU evidence is in `var/research-validation/integration-v2-engine/final`. Its profile SHA-256 is `10659469c9140909a005be3807875de146e2f48323a820435302ec96aa414682`. All runs use 165,122 retained neurons and 25,563,197 structural edges. Forty Python source files and the scientific dependency/body asset closure are frozen in the profile and receipts.

The motor candidate passes 12 of 15 published qualification gates. It **does not qualify for new v2 competition admission**: the ten-second left gradient and both ten-second forks fail the required food-intake gates. The API verifies this state and rejects an explicitly selected v2 match with HTTP 422; it never substitutes v1. Legacy remains explicitly selectable/default while this qualification fails. Research execution remains available for measuring the candidate and designs.

| Final held-out condition | Intake | First intake | Measured behavior |
| --- | ---: | --- | --- |
| Gradient, seed 10042, 10 s | 0 | Censored | +0.251 rad yaw at 0.5 s; closest thorax/source distance 1.596 mm |
| Gradient, seed 10043, 10 s | 2.32 | 1.90 s | −0.420 rad yaw at 0.5 s; later moves away from food |
| Fork, seed 10044, 10 s | 0 | Censored | Correct left branch; no wall contact; upright |
| Fork, seed 10045, 10 s | 0 | Censored | Correct right branch; no wall contact; upright |
| Blank and output ablation, 3 s each | 0 | Censored | Exactly zero drive; identical passive trajectories; 0.141 mm endpoint settling |
| Delayed cue, 3 s | 0 | Censored | Mean drive after cue offset +0.3 s: 0.003792 |

The repeated ten-second left trial has exactly identical trajectory and neural trace. Turning and stopping transfer are measured; reliable food approach/retention is unresolved. Development pilots and failed fixtures are preserved. The motor was not retuned against these held-out results.

The actual automatically scheduled three-subject experiment is `1b044921813b4454beaf23bf375b8792` (`final/experiment.json`). It independently ran WT, official and a submitted olfactory/intrinsic design under seed 42 and the same three-second conditions. Food intake was respectively **0 / 3.44 / 2.80** units. Official-minus-WT and design-minus-WT mean trajectory divergence were 1.8130 and 1.2247 mm. These are measured condition-specific differences, not a general advantage or biological claim.

Actual v2 solo and dual shared-body arena diagnostics both pass independent receipt/event/replay verification on the final source. Solo intake was 1.7456 units; dual intake was 1.6508 / 0.1332. Their records are in `final/arena.json`. Since the motor qualification failed, these are explicitly internal diagnostics, not API-admitted competitive matches and not leaderboard entries. Separately, `job-root-check/summary.json` records real legacy-default HTTP admission, isolated-root subprocess execution and verified HTTP replay.

`final/admission.json` records the real HTTP refusal and season profile status. `final/qualification.json` includes every gate and bound receipt. `final/experiment-trajectories.png` and `final/heldout-trajectories.png` show verified trajectories with equal x/y physical scale and actual receipted source/obstacle geometry; `final/plots.json` binds their inputs and output hashes.

The frozen v1 and prepared v2 readouts, decoder/sensor/backend training sources, three existing weight artifacts, eight historical arena receipts and eleven older scientific receipts remain preserved and verifiable. CPU is the actual backend. CUDA remains unavailable; no NyxID activation, deployment, public listener, or changes to existing private services occurred.
