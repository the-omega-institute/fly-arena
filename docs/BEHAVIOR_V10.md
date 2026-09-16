# Cadence-normalized hybrid v10

This is a separately versioned scientific candidate, not a production controller
selection or an admission receipt. The existing historical Bodies controller,
canonical anatomy, neural graph, transmitter signs, sensory channels, decoder,
v4 motor transfer, and historical qualification retain their interpretation.

The approved hypothesis separates common drive from the amplitude of the native
compatible step trajectory. For two finite nonnegative v4 outputs, let
`c = (uL + uR)/2` and `a = (uR - uL)/(2c)`. The registered outer input domain is
`c <= 0.4` and `abs(a) <= 0.8`. Above `c = 1e-4`, native left/right target
amplitudes are `0.6*(1-a)` and `0.6*(1+a)`. Both the native intrinsic frequencies
and coupling weights are multiplied by `c/0.6`, which scales the entire phase
derivative. The physics/CPG timestep and magnitude convergence at 20/s are
unchanged. Turning still changes amplitude; Cartesian clearance preservation is
not asserted.

At or below the silence threshold, the controller holds all oscillator and
hybrid correction state, counters, RNG, last angles, and last adhesion. Reset
uses seeded phases, zero magnitudes, the compatible step asset's neutral angles,
and the installed hybrid adhesion convention including swing extension. Silent
calls return copies and cannot mutate the stored command through aliasing.
The adapter delegates active reflex observations and action generation to the
installed HybridController. The legacy right roll/yaw conversion remains solely
in PreprogrammedSteps. No IK, new anatomy, sensor channel, neural side swap,
world-to-motor shortcut, or muscle-level claim is introduced.

`CadenceHybridController.checkpoint()` versions and copies every controller
member, including mutable configuration, spline assets, reset bases, last command,
and RNG. Real physics restoration uses a full MuJoCo data copy, including cached
kinematics and contacts used by the existing peripheral observation code.
`mjSTATE_INTEGRATION` alone does not retain those cached observations. The
checkpoint fixture deliberately damages destination state before restoring it.
It reuses 100 ticks from two scheduled trials' identical silent prefix, avoiding
extra physical seconds beyond the 260-second mechanical cap. Active controller
continuation and RNG/reset continuation are independently checked by a contract
fixture. This is a bounded restoration test, not evidence of arbitrary active
physical checkpoint portability across models or dependencies.

The exclusive experiment root contains a prospective registration, original
approved plan, subject references, archived source closure, model binary, compiled
model arrays and native names, graph/artifact hashes, raw streams, per-run
terminal receipts, reconstructed panel decisions, and resource accounting.
Each run records all physical ticks for qpos/qvel, thorax pose, input, native
control and actuator force, phases/magnitudes, hybrid corrections and counters,
and contact state. Collision mesh transforms are recorded every millisecond.
A separate diagnostic MjData reconstructs current-time geometry without changing
the existing controller's observation path. Whole-foot clearance uses the lowest
vertex among all five tarsal collision meshes, rather than a tarsus origin.
Foot slip uses the tarsus5 mesh centroid as a fixed material reference.
Per-time thorax transforms provide body-frame diagnostics.

Contact/absence runs must have both bounding transitions within the registered
steady window, and positive phase progress. No outcome-dependent debounce or
minimum-duration selection is applied. Complete contact-free runs are swings;
complete contact runs are stances. Every nonzero condition requires at least one
of each for every leg. Missing cycles or missing geometry samples fail. The zero
case has no commanded locomotor cycle and is exempt from swing/stance and
speed/turn gates; finite, upright, and stop gates still apply.

Numeric evidence has a fixed archive schema (`ticks`, `values`), exclusive
creation, bounded chunks, initialized-prefix retention, a separate failing
state, and finally-written terminal failures. An optional terminal snapshot
failure cannot replace the original error or prevent other retention attempts.
The writer never forwards caller-controlled names into `np.savez`. Small fixtures
exercise nonfinite data, reserved metadata names, partial chunks, simulated disk
failure, budget exceptions, and failed optional snapshots. These are contract
tests, not physical qualification.

The bounded post-review correction independently attempts resource reporting and
both stream finalizations. An incomplete terminal, reported retention failure, or
thrown finalization error stops the runner before another trial. Trial and
execution terminals separate the primary failure from secondary retention
failures; the primary exception is re-raised with secondary details attached.
Terminal writing is itself best effort: total filesystem failure cannot guarantee
any persisted receipt. Synthetic runner regressions and their receipts live in
`tests/test_behavior_v10_correction.py` and `var/behavior-v10-correction`.

The independent verifier validates complete condition panels, source identities,
integer tick horizons, archive shape/types and hashes, exact input waveforms,
and geometry reconstructed from qpos and the native compiled model. It computes
pose/yaw/speed, mesh clearance, contact-cycle slip, native saturation diagnostics,
and aggregate decisions directly from raw streams. Producer summaries or their
self-hashes cannot admit a candidate. Current production admission is unchanged.
The restoration validator still lacks explicit continuation-array shape checks
and binding to the corresponding trial streams. Its bounded historical comparison
is outside future positive admission until that separate advisory is resolved;
this finalization repair does not expand restoration validation.

For a future separately authorized experiment, register the then-current source
in a fresh exclusive output directory with the existing environment:

```sh
scripts/behavior_v10.sh register --output var/behavior-v10/mechanical-FRESH
scripts/behavior_v10.sh run --output var/behavior-v10/mechanical-FRESH
```

The script fixes one CPU worker and scratch cache paths and uses the original
read-only virtual environment. No package install, service, remote worker,
authentication, original data/artifact write, or source publication is involved.
Do not rerun `run` in an existing executed directory. The scientific registration
and source archive identify the exact tested computation; later changes require
a new stage identity and do not upgrade these receipts.

The original 32-trial negative result belongs to its archived source, preserved
with evidence in the original workspace's
`var/delivery/behavior-v10/registered-development.tar` (SHA-256
`36b3a3a49814840500c3229718bb7b9ca060c56a47da924f68c1273ebbc7bb53`).
The corrected runner has not been physically qualified. Its changed source must
not be substituted into the old manifest; `validate_freeze` should reject that
substitution. No new physical or neural trials were run for this correction.

The development panel continues while states remain safe, resources permit, and
mandatory evidence finalizes successfully. A candidate
failure blocks untouched evaluation and every full-network interpretation. Only
all-pass mechanical development permits evaluation and the exact repeat. Only
all-pass evaluation permits the fixed full-network sequence in the approved
plan. Successful later stages would require a new source freeze before their
outcomes and the real existing Lab/API/replay integration, without an unqualified
public toggle. See BEHAVIOR_V10_RESULTS.md for measured outcomes and remaining
goal gaps.
