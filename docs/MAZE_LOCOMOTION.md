# Maze locomotion: issue #82 phase 1

This document records the phase-1 diagnosis and the preregistered follow-up
for the long labyrinth observation. The replay is an observation artifact;
the body, neural readout and motor response remain engineering models described
by the repository science documents.

## Recorded diagnosis

The supplied `labyrinth-180s-v0.7.9.tar.gz` gallery contains match
`9687bb105b734fc1ab3d92642654cd4c` (a **match ID**, not a release commit),
attempt 1, WT `0c136a17a43c84c2eb32539454285783`, seed 42, labyrinth/forage,
180 s, `engineered-kernel-contact-v1`, and motor `dn-cpg-approach-v4`.
The local evidence is under `var/research/issue82/replay-gallery-v1/` and is
ignored by Git. No simulation was rerun to produce the replay diagnosis.

### Receipt verification: passed

Before analysis, the existing canonical digest and file SHA-256 helpers were
used to check all three supplied receipt-bound replay files. The receipt's
canonical digest, its byte hash in match metadata, and the match's verified
status, result/source receipt IDs, request and participant/artifact bindings
also agree. The analyzer now repeats these checks and rejects mismatches.

| Bound item | Verified SHA-256 |
|---|---|
| `scene.json` | `e4bcaa979a0361e1312cbd1bcbc2662abfbb21ffbd18c643dbbc55c910436789` |
| `frames.json` | `1a04ff67c3df730cc7a8b4ad11378e1e931dca44151a101b3c80046612890411` |
| `events.json` | `80951c14f23bac5fdf064273593e6b2daf8f29fa3dc70afc871f572d02d8389b` |
| Canonical receipt | `b92d085c91c568333198f00582ccb01f7555fd6de98f40bf12c3fafd9879b966` |
| Receipt file bytes | `f8e4ab5290795f41e9a7f6b884f641aea1d897371fdf1092559e0294bc05deaf` |

This establishes consistency of the supplied browser bundle, not independent
reverification of the simulation. `brain-0.npz`, `physics.npz` and `result.json`
are listed in the receipt but absent from this gallery and were not verified.
The receipt does not hash `match.json`; its bindings were checked, not a
nonexistent receipt hash for the entire match file.

Reproduce the verified diagnosis with the requested interpreter:

```sh
PYTHONPATH=src /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python \
  scripts/analyze_maze_locomotion.py var/research/issue82/replay-gallery-v1 \
  --window 45 65 --rows 45 50 51 51.5 51.7 51.75 51.8 52 54 54.15 60 65 \
  --output var/research/issue82/diagnosis.json
```

The analyzer accepts both ordinary run directories and prefixed gallery files,
including either layout inside a tar archive. It uses the recorded thorax
render-geom list index, not the MuJoCo geom ID. Upright means the Z projection
of `q(t) * inverse(q(0))` is nonnegative, matching `behavior_metrics` and the
replay UI's **tilt relative to the initial pose** definition. The previous
analyzer used the uncorrected mesh-local Z axis, which is not the anatomical
body Z axis; that gave 51.80 s and 34.1111%. Correcting the reference gives the
issue's **51.75 s and 34.0% exactly** (within floating-point precision).
No recorded poses are changed or invented by this coordinate calculation.

### Measured stability, drive and coverage

There are **3,601 frames**, from 0 through 180 s at 20 Hz. Duration estimates
hold each sample until the next frame and stop at the final frame. They cannot
resolve within-frame transitions. “Upright” here includes any tilt up to 90°;
a threshold crossing back to upright is not a claim of stable walking.

| Measurement | Recorded result |
|---|---|
| Upright time / fraction | **61.20 s / 180 s = 34.0000%** |
| First sampled inversion | **51.75 s**, bracketed by upright at 51.70 s |
| Inverted time | **118.80 s** |
| Inversion episodes | **5**, all eventually cross back to upright within the observation |
| Goal `food-0` | **No contact**, 0 food-contact events; first contact remains `null` |
| XY coverage | **176** visited 1 mm × 1 mm cells, on the world-origin grid |
| Sampled XY path length | **491.215558 mm** |
| XY bounding-box span | **17.04185 × 25.89213 mm** |

Coverage counts cells containing recorded positions; it does not fill cells
between samples or express a percentage of traversable maze area. Path length
includes inverted motion and is not navigation success. Goal absence is
censored at 180 s, not a zero-time arrival.

| Inversion start (s) | First upright sample (s) | Duration / recovery latency (s) |
|---:|---:|---:|
| 51.75 | 54.00 | 2.25 |
| 54.15 | 168.30 | 114.15 |
| 170.20 | 172.10 | 1.90 |
| 172.15 | 172.30 | 0.15 |
| 172.35 | 172.70 | 0.35 |

Drive statistics are sample statistics of the recorded bilateral motor outputs,
not neural firing or forces. Standard deviations use the population convention.
The initial zero-drive frame is included in the full pre-inversion window.

| Window | Samples | Left mean ± SD (range) | Right mean ± SD (range) | Mean R−L | R > L |
|---|---:|---|---|---:|---:|
| [0, 51.75) s | 1,035 | 0.229182 ± 0.169995 (0–0.4499) | 0.195406 ± 0.095744 (0–0.4454) | −0.033776 | 43.8647% |
| [46.75, 51.75) s | 100 | 0.026123 ± 0.002493 (0.0216–0.0340) | 0.192558 ± 0.011717 (0.1708–0.2192) | +0.166435 | 100% |

There are no missing drive samples in these windows. The full-window mean
hides the sustained right-greater differential immediately before inversion;
it should not be interpreted as a single turning direction throughout the run.

### Wall contacts around 45–65 s

Contact duration is estimated from each selected slot's recorded
`senses.contact_environment`, restricted to `obstacle-*`; other flies do not
count as walls. `environment_contact` events record **new contact onsets**,
not offsets or durations, and are now reported separately. No contact is
inferred from proximity. All 3,601 frames have this contact field.
The whole replay has **54.75 s** of sampled wall contact. In [45, 65) s,
**230 of 400 frames (57.5%, 11.50 s)** have wall contact, with **119 onset
events**. Per-object counts overlap: obstacle-0 has 181 samples, obstacle-2
166, and obstacle-4 23. These are respectively the west outer wall, south
outer wall and left internal divider in the recorded scene.

The complete sampled wall-contact intervals intersecting this window are
[45.00, 52.00), [52.05, 52.35), [52.65, 52.75), [52.80, 53.45),
[53.65, 54.95), [55.50, 55.80), [55.95, 56.40), [56.55, 57.05),
[57.10, 57.30), [57.40, 57.65), [57.75, 57.80), [57.90, 58.15),
[59.75, 59.80), [60.00, 60.05), and [60.25, 60.30) s.
The first interval is clipped at 45 s, not a claim that contact began there.
Continuous sampled contact does not exclude brief unsampled separations.

The table below is generated from `window_report.rows` in the command above.
Rows use exact recorded timestamps, including the closed window endpoint at
65 s; no interpolation is used. Heights and XYZ use `frames.positions[slot]`,
the recorded thorax body position, rather than the render-geometry center.
`window_report.pre_inversion_height_max` selects the earliest maximum among
all samples in [window start, min(window end, first inversion)), not just
the requested table rows. Missing contact fields remain `null`.

| Time (s) | Thorax height (mm) | Upright projection relative to initial pose | Recorded obstacle contacts |
|---:|---:|---:|---|
| 45.00 | 1.34718 | +0.936556 | 0 |
| 50.00 | 1.10362 | +0.999044 | 0, 2 |
| 51.00 | 1.67331 | +0.849302 | 0, 2 |
| 51.50 | 2.46935 | +0.181471 | 0, 2 |
| 51.70 | 2.13256 | +0.340694 | 2 |
| 51.75 | 1.67540 | -0.477757 | 2 |
| 51.80 | 0.48657 | -0.735991 | 0, 2 |
| 52.00 | 0.45464 | -0.977879 | None |
| 54.00 | 1.69773 | +0.721720 | 0 |
| 54.15 | 0.46226 | -0.603305 | 2 |
| 60.00 | 0.50885 | -0.987684 | 0 |
| 65.00 | 0.49962 | -0.990584 | None |

The height peak within [45, 51.75) s is 2.46935 mm at 51.50 s, near the
southwest wall corner (XYZ = [-12.07178, -12.25204, 2.46935] mm), before the drop and
inversion. This is consistent with **wall-associated climbing/rearing under
sustained differential drive**. The data support an interaction hypothesis;
they do not establish whether wall climbing alone, turning drive alone, or
contact-driven neural feedback is necessary or sufficient. Contact objects and
pose samples do not resolve the forces or individual footholds causing the flip.

To distinguish those hypotheses, use matched body experiments with and without
walls, matching the common drive while changing only its asymmetry, and replay
the measured pre-inversion drive history into the body with neural feedback
explicitly disabled. Then compare to a matched closed-loop run to test feedback.
Those would be declared mechanics interventions, not synthetic behavioral
recordings. The short constant-drive probe below does not perform these longer
or matched-history tests.

## Body-only probe

The existing `scripts/probe_maze_locomotion.py` completed **four windows** in
this follow-up: seed 42, five simulated seconds each (20 s total, 200,000
physics steps). Each window starts a fresh `Bodies`/`HybridTurningController`
fixture and records 500 samples at 100 Hz (0.01 through 5.00 s). The wall-absent
condition removes all obstacle geometry, including outer walls. Symmetric
input is [0.3, 0.3]; differential input is [0.25, 0.55]. These are explicitly
imposed body-test commands, with no neural simulation, target steering, route
following, pose edit or upright reset, and no recovery candidate selected.

```sh
PYTHONPATH=src /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python \
  scripts/probe_maze_locomotion.py --seconds 5 --seed 42 \
  --output var/research/issue82/body-probe.json
```

| Walls | Drive | Samples | Upright fraction | Minimum body upright-Z | First inversion (s) | XY path (mm) | Final XYZ (mm) |
|---|---|---:|---:|---:|---|---:|---|
| Present | Symmetric | 500 | 1.000 | 0.7827541911 | `null` | 44.55761897 | [−6.864849, 7.001789, 1.043496] |
| Present | Differential | 500 | 1.000 | 0.6378298680 | `null` | 65.24119889 | [−6.179437, −10.843357, 1.344302] |
| Absent | Symmetric | 500 | 1.000 | 0.9979286207 | `null` | 25.01533629 | [9.183751, −9.379123, 1.078002] |
| Absent | Differential | 500 | 1.000 | 0.9933232288 | `null` | 34.76895928 | [−15.564257, −8.879168, 1.113001] |

All four windows finished, with no sampled inversion and no failed window in
this invocation. Upright here is the actual body rotation's world-Z projection,
not the rendered mesh axis. No inversion within five seconds is not evidence
of long-horizon stability or recovery. The two drive conditions also differ in
common drive (0.3 vs 0.4), so they cannot isolate asymmetry. Seed 43 was not run.

For continuity: the earlier phase completed only the wall-present symmetric
seed-42 smoke window; an attempted eight-window invocation was interrupted and
produced no aggregate result. It remains an incomplete attempt, not additional
measurements. The four rows above come from the completed follow-up invocation.

## Versioned recovery candidate

`dn-cpg-approach-v4` and its `MotorTransfer` implementation are unchanged.
The new opt-in profile `dn-cpg-recovery-v5-candidate` wraps that transfer and
adds a bounded bilateral leg-drive correction from measured body state:

- thorax local-Z upright projection (`upright_z`),
- measured roll and pitch angular rates, and
- measured left/right tarsal support fractions.

The correction is smooth, capped, and attenuates propulsion during low
stability. It is intended to produce a restoring moment through the two existing
leg-drive channels; that effect has not been demonstrated. It never teleports or
resets a body, steers toward a target, follows a route, edits a recording, or
invents a pose. It is constructed only
through `motor_for_profile(..., admission="sandbox"|"observation")`; deployment,
training and competition admission reject it. Existing v2 profiles, readouts,
receipts and historical replays do not select this candidate.

The measured diagnosis does **not** justify changing the candidate's gains or
adding scripted steering. The candidate remains unchanged and isolated: its
measured tilt/rate/support inputs and reduced propulsion address a plausible
low-stability component of the observed wall/drive interaction. That is a
hypothesis, not evidence of prevention or righting. This replay provides neither
the candidate's counterfactual response nor a paired candidate evaluation.

## Why the v5 candidate failed - measured comparison

This section reports a recording-only comparison of the five receipt-bound
phase-2 pairs. It uses the comparison script at
`f7dc3acbb5c432d433f157d0b61bb0d18c48c5de6ba2fc21bd47009ce6aa4963` and the
compact [arm-comparison evidence](evidence/maze-phase2-20260924-arm-comparison.json).
The source files were not rerun or modified. Recorded candidate
`motor_body_state` values are labeled as recorded. The `upright_z`, roll-rate
and pitch-rate values used here come from those candidate recordings; they are
not inferred from the trajectory. The attenuation factor is explicitly a
modelled value computed from recorded inputs and candidate receipt
configuration, not a measured force or actuator torque.

The exact per-seed command was run from `/Users/macstudio/fly-arena-mvp` with
the Mac Studio deploy environment:

```sh
for seed in {42..46}; do
  PYTHONPATH=src /Users/macstudio/fly-arena-mvp/.venv/bin/python \
    scripts/compare_phase2_arms.py \
    "var/research/issue82-phase2/study-20260924/seed-$seed"
done
```

The comparison uses a 5.0 s drive window ending at each arm's first recorded
inversion, an initial-pose-relative inversion threshold of `upright_z < 0`,
recorded `environment_contact`/wall-contact onsets only, and a 1 mm relative
XY path-separation threshold. All pairs have 3,601 common recorded timestamps.
The evidence file records the condensation rule: correction-input time series
were replaced by their key list, long attenuation lists were reduced to count
plus their first 40 entries, and trajectory samples were kept every 100th
sample. The values below are the retained scalars and short context lists.

### Per-seed outcome and contact context

Later first inversion is favorable. The candidate was worse in seeds 42, 45
and 46, and later in seeds 43 and 44, matching the preregistered negative
set-level verdict.

| Seed | First inversion baseline -> candidate (s) | Candidate change (s) | Inversion episodes, baseline -> candidate | Wall-onset count before first inversion, baseline -> candidate | Last candidate onset -> inversion (s) | First >1 mm divergence / maximum (s / mm) |
|---:|---:|---:|---|---:|---:|---:|
| 42 (worse) | 51.75 -> 17.75 | -34.00 | 5 (5 recovered) -> 1 (0 recovered) | 196 -> 170 | 17.66 -> 17.75 (0.09) | 1.40 / 26.3820 |
| 43 (improved) | 1.50 -> 22.30 | +20.80 | 1 (0 recovered) -> 2 (1 recovered) | 1 -> 61 | 21.42 -> 22.30 (0.88) | 0.80 / 12.5115 |
| 44 (improved) | 27.95 -> 36.15 | +8.20 | 4 (3 recovered) -> 4 (3 recovered) | 33 -> 110 | 35.96 -> 36.15 (0.19) | 1.35 / 27.5695 |
| 45 (worse) | 20.75 -> 13.50 | -7.25 | 4 (3 recovered) -> 1 (0 recovered) | 16 -> 37 | 13.01 -> 13.50 (0.49) | 2.75 / 18.1253 |
| 46 (worse) | 28.20 -> 9.10 | -19.10 | 1 (0 recovered) -> 1 (0 recovered) | 39 -> 27 | 8.95 -> 9.10 (0.15) | 2.75 / 18.0703 |

Every candidate first inversion had a recorded wall-onset event shortly before
it, with lead times from 0.09 to 0.88 s. That association is also present in
every baseline arm, with lead times from 0.02 to 0.37 s. It therefore does not
separate the candidate failure from baseline behavior. The paired trajectories
also diverged above 1 mm in 0.80 to 2.75 s, well before some first inversions;
the paired recordings are not identical histories after the intervention.

### What each hypothesis supports

| Hypothesis | Verdict with these recordings | Measured finding |
|---|---|---|
| Attenuated propulsion leaves the fly pushed into walls. | **Not distinguishable** | The candidate has one modelled attenuation period from 0.05 to 180.00 s in every seed, with a modelled minimum factor of 0.2; its last recorded wall onset precedes the first inversion in all five seeds. However, candidate wall-onset counts are lower than baseline in 42 (170 vs 196) and 46 (27 vs 39), and higher in 43 (61 vs 1), 44 (110 vs 33) and 45 (37 vs 16). The mixed outcome and absence of wall force or torque measurements do not support a causal claim that attenuation left the fly pushed into a wall. |
| Correction amplifies roll on uneven support. | **Not distinguishable** | The candidate context contains recorded state changes compatible with this mechanism. At -0.5 s and at inversion, respectively, candidate roll/pitch rates and left/right support fractions were: seed 42, (-31.4405, -10.9143; 0.333/0.333) -> (6.6801, 33.4309; 0/0); 43, (-45.9494, -15.1985; 0.333/0.333) -> (72.1953, -24.2903; 0.333/0); 44, (-44.6385, -8.0468; 0.333/0.333) -> (-11.6947, 60.2970; 0.667/0); 45, (6.2504, 5.5813; 0.333/0.667) -> (-101.9974, -27.5445; 0/0); and 46, (-0.5156, -3.3628; 1/0.333) -> (2.7289, 26.6599; 0.333/0). These are recorded inputs/state observations, not the applied restoring moment. Seed 42 has equal support at both listed pre-inversion points, and no run records the force or torque that would establish amplification. |
| Earlier inversions arise from altered gait. | **Not distinguishable** | The 5 s recorded drive summaries differ between arms, but not in one outcome-predicting direction. Baseline -> candidate left/right means were 42: (0.026123, 0.192558) -> (0.021705, 0.169419); 43: (0.353577, 0.222643) -> (0.309100, 0.121433); 44: (0.234217, 0.101615) -> (0.361011, 0.079261); 45: (0.212820, 0.108537) -> (0.225417, 0.177709); and 46: (0.441050, 0.199162) -> (0.327839, 0.093109). Candidate first inversion was earlier in 42/45/46 but later in 43/44, while trajectory divergence exceeded 1 mm in every pair. Altered recorded drive is supported as a correlate; altered gait as the cause of the earlier inversions is not identified. |

The candidate attenuation periods are modelled from recorded correction inputs
and receipt configuration. Their per-seed reported maximum factors were 0.999432,
0.999916, 0.999682, 0.999532 and 0.999988 for seeds 42 through 46,
respectively; the baseline attenuation status is unavailable because the
baseline receipt contains no candidate correction configuration. These values
must not be read as measured propulsion or wall force.

### What remains unestablished

The recordings establish paired timing, recorded contact onsets, bilateral
drives, candidate state inputs and trajectory separation. They do not establish
wall reaction forces, foot-ground forces, actuator torques, individual foothold
geometry, the applied correction moment, or a causal role for contact-driven
neural feedback. A 20 Hz pose/contact record also cannot resolve events between
samples. Baseline pose-rate values are proxies when the candidate state fields
are absent, so their rates cannot be treated as a direct force or controller
comparison. None of these observations is a biological activity or behavior
claim.

### Minimal next experiment (not run)

Use a preregistered short mechanics intervention with the same initial state,
body, timestep, seed and measured pre-inversion drive history. The minimum
diagnostic is a 2 x 2 comparison of walls present/absent and the existing
candidate correction off/on, replaying the common drive open-loop with neural
feedback disabled. Record contact forces and torques if exposed by the
engine, alongside contact points, support, pose and bilateral drive. Add one
matched closed-loop pair with the same initial state to test whether feedback
changes the result. A wall-specific inversion that disappears without walls
would support a mechanics interaction; a candidate-only change under equal wall
conditions with a corresponding support/roll change would support a correction
interaction; divergence without walls or feedback would support an altered
drive/body mechanism. This is a mechanics diagnosis using existing profiles,
not a synthetic behavioral recording, and it requires no gain change or
scripted steering. It was not run for this report.

## Preregistered phase-2 protocol

The protocol predates the replay diagnosis. The decision rule below is clarified
before any phase-2 run: later first inversion is favorable, censoring is explicit,
and goal contact is descriptive rather than an acceptance criterion. The seeds,
horizon and four-of-five threshold are retained. No phase-2 baseline/candidate
pair was executed in this follow-up.

| Item | Frozen value |
|---|---|
| Wild type | `0c136a17a43c84c2eb32539454285783` |
| Tasks | `labyrinth` / `forage` |
| Contact model | `engineered-kernel-contact-v1` |
| Horizon | 180 s simulated |
| Seeds | 42, 43, 44, 45, 46 |
| Execution | Mac Studio, serialized one run at a time |
| Baseline | current selected motor profile, with the same body/readout/runtime |
| Candidate | `dn-cpg-recovery-v5-candidate`, sandbox observation only |

For every seed, run a matched baseline and candidate from the same WT artifact,
scene seed, task, horizon and runtime. Preserve both successful and failed
attempts, including timeouts and incomplete recordings. Bind each report to the
profile identity, body/readout source hashes, scene, seed and recording policy.
Do not pool or silently replace a failed seed.

Report for each run and for the paired five-seed set:

1. upright fraction and first inversion time;
2. inversion episode count, duration and recovery duration (with null for an
   unrecovered episode);
3. wall-contact onset events and sampled contact-duration estimates, reported separately;
4. left/right drive mean and spread before first inversion;
5. first actual goal-food contact and censored/no-contact status; and
6. XY path length and one-millimetre visited-cell coverage.

Compare candidate **C** with baseline **B** separately within each seed
42–46; never compare different seeds or use pooled means to override a pair.
Use the same 20 Hz recording policy, initial-pose-relative upright definition,
and sample-hold duration calculation for both runs. Compute comparisons from
unrounded values; exact equality is a tie and never a strict improvement.

| Metric | Favorable direction and paired comparison | Role in decision |
|---|---|---|
| Upright fraction U | Higher: U_C > U_B is improvement; equality is a tie; lower is worsening. | Required strict improvement in each improved seed. |
| First sampled inversion latency L | Later is better when both runs invert: L_C > L_B improves, equality ties, earlier worsens. A complete run with no inversion through 180 s has L = null with an explicit right-censor flag; this is the best observed outcome. Candidate censored / baseline inverted improves; both censored ties; candidate inverted / baseline censored worsens, including an inversion at the 180 s endpoint. | Must improve or tie in each improved seed; never convert null to zero, a measured 180 s latency, or infinity. |
| Total inversion duration / recovery burden D | Lower is better: D_C < D_B improves; equality ties; higher worsens. D is the sum of all inverted sample-hold intervals clipped to [0, 180 s]. Include the observed duration of an unrecovered episode through 180 s; retain its recovery latency as null/right-censored. No inversion gives D = 0. | Must improve or tie in each improved seed. D is the prespecified aggregate recovery burden, not the mean of only recovered episodes. |
| Visited-cell coverage V | Higher is favorable; V_C >= V_B meets the guardrail; lower worsens. | Must not decrease in each improved seed. |
| First actual goal-food contact | Report the recorded time and censor/no-contact status for both runs; no directional acceptance comparison. | Descriptive only; neither a criterion nor a veto. |
| Episode count, individual recovery latencies, wall contact, drive statistics and XY path | Report both runs and available paired differences. Unrecovered latencies stay null/censored. No favorable direction is prespecified for these diagnostics; more path or fewer episodes alone does not establish better stability. | Descriptive only. |

A seed is **improved** only when its complete, valid pair has strictly higher
upright fraction, equal or better first-inversion outcome, no greater total
inversion/recovery burden, and no lower coverage. A seed is **negative** if
any of those four metrics worsens, even if another improves, or if the candidate
fails while its matched baseline completes. All other complete pairs are
**null** (including all ties and partial favorable changes that do not satisfy
the strict upright-fraction requirement). Two inversion-free runs therefore
tie on latency and burden; that tie cannot itself count as an improved seed.

Apply the following set-level rule in order:

1. Any unbounded drive or pose intervention invalidates the study for the claim:
   report **null / protocol violation**, retain the evidence, and do not count
   affected runs as improvements.
2. Any negative seed makes the candidate verdict **negative**, with the seed and
   adverse metric or candidate-only failure stated explicitly. A negative fifth
   seed cannot be hidden by four improved seeds.
3. Otherwise, any missing, failed, timed-out or incomplete paired run makes the
   claim **null / incomplete**. Censoring is valid only for a complete 180 s
   recording, never a substitute for a failed or missing recording. Do not drop
   a seed, count missing evidence as a tie, or silently replace an attempt.
4. With all five valid pairs and no negative seed, **improvement** requires at
   least **4 of seeds 42–46** to be improved by the joint rule above; the remaining
   seed may be null. Fewer than four improved seeds gives a **null** verdict.

Report each seed's metric comparisons and classification, the improved/null/
negative counts, and all incomplete or invalid attempts alongside the verdict.
These rules decide only whether this versioned engineering candidate merits a
later study; they do not establish biological righting or competition fitness.

## Phase-2 execution harness

Run the frozen ten observations **on Mac Studio**, from its matching source and
prepared environment. This invokes `runner.simulate` directly, with the existing
WT artifact and research-v2 readout. SQLite is opened read-only to obtain the WT;
no match, job, standings or leaderboard row is created. Each child exits before
the next begins. The explicit output directory is also the resume handle:

```sh
cd /Users/macstudio/fly-arena-mvp
ARENA_DATA="$PWD/data" ARENA_VAR="$PWD/var" PYTHONPATH=src \
  .venv/bin/python scripts/run_maze_phase2.py \
  --horizon 180 --seeds 42 43 44 45 46 \
  --output var/research/issue82-phase2/preregistered-v1
```

Omit `--output` to allocate `var/research/issue82-phase2/<run-id>/`. Repeat the
exact command to resume. A completed run is skipped only after its canonical
receipt, **all** receipt-bound files (including neural/physics checkpoints),
request, subject, motor, runtime, readout and complete 20 Hz frame grid verify.
The paired scene/runtime bindings must also agree. Changed scientific sources,
harness, arguments or readout are rejected on resume. Failed, timed-out,
interrupted and invalid attempts are retained and never silently rerun; pending
arms/seeds can continue, but a new attempt cannot replace an old seed's evidence.
An output-directory lock prevents simultaneous writers to the same study.
Optional `--timeout SECONDS` records a per-run wall-clock timeout as a failure;
there is no default computation deadline.

Each `seed-<seed>/<baseline|candidate>/` contains a versioned motor-selection
`manifest.json`, worker log, outcome, analysis and `replay/` directory containing
the normal scene/frames/events/result/checkpoints/receipt. Baseline receipt
semantics and selected motor are unchanged. The candidate alone adds the
receipt field `observation_motor` (`arena-observation-motor/v1`) and is constructed
with `motor_for_profile(..., admission="observation")`. Its existing gains are
unchanged. The runner measures thorax local angular velocity and upright
projection directly from MuJoCo, and per-side tarsal support as the fraction
of three legs with actual supporting terrain contact. Each support contact must
be below the thorax with its normal towards the fly within 45 degrees of world
up; food and other flies are excluded. These motor inputs are saved in the
candidate's recorded senses. This is an engineered body-state measurement and
motor intervention, not recorded biological righting.

Append-only `partial-frames.jsonl` and `partial-events.jsonl` preserve observed
samples and events flushed at each 20 Hz snapshot if a worker fails or is killed.
They can stop before the failing integration step and are explicitly incomplete,
not receipt-verified replays. Errors and tracebacks remain alongside them; no
missing pose or event is reconstructed. A completed run retains these journals
as well as the normal immutable replay files. Ordinary runner callers do not
activate these observation hooks or acquire candidate fields in their receipts.

The existing maze analyzer runs after each completed, verified observation.
`paired-report.json` includes its full diagnostics, censor flags, recovery burden,
paired differences, receipt/source bindings and every failed/invalid attempt.
`paired-report.md` provides the paired table and the ordered decision above.
The report never pools seeds to override a negative or incomplete pair. The
first completed run prints an extrapolated runtime estimate; startup, compilation
and behavior make this an estimate rather than a promised deadline.

Local real smoke command (two simulated seconds, seed 42, **both** profiles):

```sh
ARENA_DATA=/Users/lexa/Desktop/lexa/omega/fly-arena/data \
ARENA_VAR=/Users/lexa/Desktop/lexa/omega/fly-arena/var \
PYTHONPATH=src \
  /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python \
  scripts/run_maze_phase2.py --dry-run
```

`--dry-run --horizon 2 --seeds 42` is equivalent. This performs real neural/body
integration and explicitly forces the same `pose-20hz-events-20hz-v1` recording
policy for both short runs; ordinary short matches still use their normal
100 Hz policy. Any non-180-second horizon or non-five-seed set is marked
**not the preregistered protocol** and receives **no set-level verdict**. A short
run's no-inversion/no-contact flag is censored only at its actual short endpoint
and cannot qualify as 180-second evidence. Missing research-v2 assets are reported
as preflight errors and are never regenerated by the harness.

Implementation smoke (local, final harness): both seed-42, two-second runs
completed in **79.11 s process wall time** (**78.78 s** measured inside the
harness, including preflight and analysis). Evidence is retained at
`var/research/issue82-phase2/smoke-verified/`. Each run recorded 41 frames and
used the full retained graph (165,122 neurons, 25,563,197 edges). Both short
runs had upright fraction 1.0 and no sampled inversion; these are short-window
observations only. The report is explicitly outside the preregistered protocol
and has no set-level verdict. The complete five-seed, 180-second Mac Studio
study has **not** been executed by this implementation task.


## Completed phase-2 study: 2026-09-24

**Preregistered verdict: negative.** All ten 180-second observations completed
on Mac Studio in 21,892.84 wall seconds (6 h 4 min 53 s). Seeds 43 and 44
improved under the joint rule; seeds 42, 45 and 46 were negative. There were
no incomplete or invalid pairs, no reported protocol violations and no recorded
execution errors. Issue #82 remains unresolved. This candidate does not meet
the criterion for advancement and is not promoted to the default motor profile.

The baseline was `dn-cpg-approach-v4`; the candidate was
`dn-cpg-recovery-v5-candidate`. Both used the frozen canonical WT, labyrinth /
forage, `sensorimotor-research-v2`, `engineered-kernel-contact-v1`, the same
runtime and paired scene, and the preregistered 20 Hz recording policy.

| Seed | Upright B → C (%) | First inversion B → C (s) | Inverted burden B → C (s) | Visited cells B → C | Joint result |
|---:|---:|---:|---:|---:|---|
| 42 | 34.0000 → 9.8611 | 51.75 → 17.75 | 118.80 → 162.25 | 176 → 28 | negative |
| 43 | 0.8333 → 15.8611 | 1.50 → 22.30 | 178.50 → 151.45 | 15 → 63 | improved |
| 44 | 18.1944 → 37.3611 | 27.95 → 36.15 | 147.25 → 112.75 | 126 → 181 | improved |
| 45 | 11.6667 → 7.5000 | 20.75 → 13.50 | 159.00 → 166.50 | 92 → 53 | negative |
| 46 | 15.6667 → 5.0556 | 28.20 → 9.10 | 151.80 → 170.90 | 92 → 32 | negative |

The table rounds only for display; the decision uses unrounded values. All four
acceptance metrics worsened in each negative seed. The preregistered rule makes
any negative seed sufficient for a negative set-level verdict; improvements in
other seeds cannot compensate. No run recorded goal-food contact through 180 s.
Those goal times remain null/right-censored, and goal contact is descriptive,
not an acceptance criterion.

The [complete paired report](evidence/maze-phase2-20260924.json) retains every
run's inversion episodes, individual recovery censoring, wall-contact onsets
and sampled duration, pre-inversion drive statistics, path length, coverage,
paired differences and source/receipt bindings. The frozen study digest is
`93659137407be6a093d51842adebc738ac0e4a2166050b99620a69fd5d10394b`.
Original recordings remain at
`/Users/macstudio/fly-arena-mvp/var/research/issue82-phase2/study-20260924/`.

A separate [post-completion evidence audit](evidence/maze-phase2-20260924-audit.json)
rechecked all ten observations on Mac Studio without running another simulation
or rewriting the original study evidence. It checked canonical study/manifest/
receipt digests, frozen harness and analyzer hashes, all 60 receipt-bound files
(including neural and physical checkpoints), all ten 3,601-frame grids, bounded
recorded drives, subject/runtime/motor/scene bindings, and equality of recomputed
analysis with the retained analysis and final report. Recomputing the joint
rule returned the same negative verdict. This establishes integrity and
reproducibility of the recorded analysis; it is not an independent simulation
replication or biological validation.

The measured outcome argues against this version of the engineering recovery
controller. It does not establish which feedback or gait interaction caused
the regressions. A later candidate needs a separately specified intervention
and a new prospective evaluation; these five seeds must not be relabeled as
unseen validation data after tuning against this result. Preserve this failed
candidate and the earlier failed baseline observation as evidence.
