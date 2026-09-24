# Maze locomotion: issue #82 phase 1

This document records the phase-1 diagnosis and the preregistered follow-up
for the long labyrinth observation. The replay is an observation artifact;
the body, neural readout and motor response remain engineering models described
by the repository science documents.

## Recorded diagnosis

The requested evidence is release asset `labyrinth-180s-v0.7.9.tar.gz` from
release commit `9687bb105b734fc1ab3d92642654cd4c`. It was not present under
`var/` in this worktree, and `gh issue view 82` / the release download could not
reach `api.github.com` in the execution environment. Therefore no replay
numbers are reported here. In particular, this phase does **not** claim an
upright fraction, inversion time, wall interaction, drive asymmetry, goal
contact or coverage from an unavailable recording. The requested first-wall
interaction/inversion window at 45–65 s is consequently unresolved.

Run the analysis once the immutable asset is available:

```sh
gh release download v0.7.9 -p 'labyrinth-180s-v0.7.9.tar.gz' -D var/research/issue82
uv run python scripts/analyze_maze_locomotion.py \
  var/research/issue82/labyrinth-180s-v0.7.9.tar.gz \
  --output var/research/issue82/diagnosis.json
```

`analyze_maze_locomotion.py` reads recorded poses, drives, events and scene
geometry. It reports upright time using the recorded thorax quaternion,
contiguous inversion episodes and whether each episode recovered, wall-contact
intervals from recorded contact events/fields, bilateral drive statistics before
the first inversion, first actual goal-food contact (null when absent), and
one-millimetre XY path coverage. It does not infer contact from proximity,
fill missing poses or convert failure into a zero-time arrival.

## Body-only probe

`scripts/probe_maze_locomotion.py` is a short mechanics diagnostic around the
existing `Bodies` and `HybridTurningController`. It runs wall-present and
wall-absent windows with symmetric and sustained differential drives for seeds
42 and 43. The probe has no brain, route following, target steering, pose edit
or upright reset. Its output is evidence about the body/controller fixture
only, not evidence that a maze recovery mechanism works.

```sh
uv run python scripts/probe_maze_locomotion.py --seconds 5 \
  --output var/research/issue82/body-probe.json
```

One five-second CPU smoke window did complete locally (`wall_present=true`,
`symmetric`, seed 42): 500 recorded samples, upright fraction `1.0`, minimum
recorded upright-Z projection `0.7827541911`, first inversion `null`, path
length `44.5576189667 mm`, and final position
`[-6.864849, 7.001789, 1.043496] mm`. These are body-only measurements for
that one window. An attempted full eight-window invocation was interrupted for
runtime and produced no aggregate claim; its partial output was discarded.
A failed, partial or timed-out window remains a failure record and must not be
summarized as a measurement.

## Versioned recovery candidate

`dn-cpg-approach-v4` and its `MotorTransfer` implementation are unchanged.
The new opt-in profile `dn-cpg-recovery-v5-candidate` wraps that transfer and
adds a bounded bilateral leg-drive correction from measured body state:

- thorax local-Z upright projection (`upright_z`),
- measured roll and pitch angular rates, and
- measured left/right tarsal support fractions.

The correction is smooth, capped, and attenuates propulsion during low
stability. It can produce a restoring moment through the two existing leg
drive channels; it never teleports or resets a body, steers toward a target,
follows a route, edits a recording, or invents a pose. It is constructed only
through `motor_for_profile(..., admission="sandbox"|"observation")`; deployment,
training and competition admission reject it. Existing v2 profiles, readouts,
receipts and historical replays do not select this candidate.

## Preregistered phase-2 protocol

This protocol is written before the missing replay diagnosis is available.

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
3. wall-contact timeline and total contact duration from recorded events;
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
