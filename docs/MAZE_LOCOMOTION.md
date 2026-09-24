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

| Time (s) | Thorax height (mm) | Upright projection relative to initial pose | Recorded obstacle contacts |
|---:|---:|---:|---|
| 45.00 | 1.34718 | +0.936556 | 0 |
| 50.00 | 1.10362 | +0.999044 | 0, 2 |
| 51.00 | 1.67331 | +0.849302 | 0, 2 |
| 51.50 | 2.46935 | +0.181471 | 0, 2 |
| 51.70 | 2.13256 | +0.340694 | 2 |
| 51.75 | 1.67540 | −0.477757 | 2 |
| 51.80 | 0.48657 | −0.735991 | 0, 2 |
| 52.00 | 0.45464 | −0.977879 | None |
| 54.00 | 1.69773 | +0.721720 | 0 |
| 54.15 | 0.46226 | −0.603305 | 2 |
| 60.00 | 0.50885 | −0.987684 | 0 |
| 65.00 | 0.49962 | −0.990584 | None |

The height peak within [45, 51.75) s is 2.46935 mm at 51.50 s, near the
southwest wall corner (x = −12.07178, y = −12.25204 mm), before the drop and
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

## Preregistered phase-2 protocol

The following protocol was written before the replay diagnosis became available
and is retained here without retuning its seeds, horizon or success criteria.
No phase-2 baseline/candidate pair was executed in this follow-up.

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

The candidate counts as an improvement only if it has a predeclared paired
improvement on the primary stability outcome (higher upright fraction **and**
shorter or equal first inversion/recovery burden) without reducing recorded
goal contact or coverage, and the direction is present in at least 4 of 5
matched seeds. A result with fewer than 4 improved seeds, any unbounded drive
or pose intervention, or a missing/failed paired run is null for the claim.
A lower upright fraction, longer inversion burden, lower coverage/goal contact,
or any failure that occurs only after selecting the candidate is negative for
this candidate. These rules do not establish biological righting or competition
fitness; they decide only whether this versioned engineering candidate merits a
later study.
