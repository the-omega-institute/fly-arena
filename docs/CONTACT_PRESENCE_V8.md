# Contact presence 48 mV, tethered v8

Research only. The full Fly Arena goal remains unmet. The authoritative approved
plan is copied verbatim into `var/contact-v8/inputs/approved-plan.json` and frozen
inside registration before the first new neural/body condition. No old profiles,
15 historical gates, artifacts, source evidence, services or production routes
are changed.

The unchanged v7 scientific helper snapshots are copied with their historical
hashes. Canonical neural/compiler/connectome/odor sources must match the old
registration. The binary adapter loads the exact `compiled.mjb` digest
`5a9b00ad3df366f2837aa811cf7b732e8c55b912c0afc8080c58e1db71bd4691` and
saved numerical rest state, names, signs and geometry. It reproduces a saved
v7 physical .20–.21 s interval and next contact sample before new outcomes.
There is no XML reconstruction, coordinate assay, mechanics tuning or sweep.

A contact sensor sums norms of actual FlyGym segment net world forces on each
leg's tibia/tarsus1/tarsus2, divides by native weight, and injects 48 mV on every
original tactile afferent iff the finite ratio is strictly positive. Every
positive signal requires a loaded, positive-normal-force probe/leg contact pair.
All raw MuJoCo pairs, IDs, exclusion/equality addresses, native six-component
wrenches, distance and 3×3 contact frames are saved at the initial forward and
all 10,000 physical steps. A raw pair row has columns contact index, geom1,
geom2, exclude, efc_address, distance, wrench[6], frame[9]. `offsets[t:t+2]`
selects pairs present at physical endpoint tick t. Multi-contact cancellation
remains a limitation. This is an engineering synchronous switch, not measured
physiology; there is no adaptation or proprioception.

MuJoCo step order is retained: force data read at endpoint tick t were evaluated
at t−1, except the initial forward at 0. `force_evaluation_tick`,
`force_read_tick`, `input_start_tick`, and `output_end_tick` make this explicit.
Input sampled at t is held for the following 100 neural ticks. Body motion in
that interval uses the previous command; the newly computed rate-only command
is eligible for the next interval. No force, contact, position or reward enters
`.1 * (mean flexor − mean extensor) / 444.41470981063657`. The approved literal
is used; the tiny floating-point difference from v7's computed rate ceiling is
documented in preflight, not selected from outcomes. Contact is never gated by
the nominal .2–.5 s probe window. Negative and initial-contact data are retained.

The panel is exactly 72 neutral A/B/C cells and 24 WT odor-OFF cells: LF/RM/RF,
state 42/43 (+/− .005 rad own knee), intact/tactilezero/motorzero/noprobe. Three
LF42-neutral-intact repeats (one per actual subject) bring the hard cap to 99.
Sham remains at [0,0,10] mm and is checked every physical step. Motorzero clamps
neural position offsets but keeps neutral servos. The initial conditions and
imposed probe are matched across whole trials; realized contact can differ
through feedback. OFF official/submitted and direct LM/LH/RH probes are absent,
not zero. All six output pools/body coordinates remain recorded.

Frozen thresholds are >.01 rad for ≥.05 s consecutive whole 10 ms intervals,
requiring both endpoints strictly above threshold, constant direction and
same-direction temporal overlap of intact−tactilezero and intact−motorzero.
Both states must have consistent nonzero signed full-trial mean. Causal ordering
uses actual sensor times, own afferent increments, own MN pool/command changes,
precontact equality and delayed command application; no sub-bin latency claim.
RF own-output null cannot be replaced by movement elsewhere.

Y and N are signed trapezoid means on all 101 frames. Resolved pair differences
must have the same sign across states, exceed .001 rad / 1 Hz respectively and
10× exact-repeat error. Joint tactile phenotype additionally needs a local gate
in at least one subject. Raw curves, peak, RMS, duration and all pairwise/control
differences remain published. No statistical population/superiority/equivalence
claim follows from deterministic initial perturbations.

Run with `sh scripts/env-v8.sh SCRIPT`. The environment uses existing original
read-only dependencies, disabled bytecode and isolated scratch caches. First
run preflight and tests; then `run_contact_v8.py` freezes exclusively and runs
once. No automatic restart or overwrite is allowed. Source changes after
registration must be separately versioned and disclosed; failed registration
and partial records remain immutable. Integrity errors stop dependent work;
scientific nulls do not. Evidence is capped at 1.5 GB including snapshots.

`verify_contact_v8.py` imports no candidate bridge, loader, runner or gate. It
reconstructs force/current/pools/commands/clamps, checks timestamps and fixed
checkpoints, replays every .20–.21 physical interval and one fixed .20–.50 neural
interval per actual subject. Same-integrator replay proves deterministic
integrity, not independent validation of the LIF model. `report_contact_v8.py`
recomputes all means/traces from records and compares with independent metrics.
The HTML embeds recorded arrays and works without a service; PNG gets static
visual inspection only, with browser QA explicitly absent.

Whole-trial execution and artifact-store seams remain research scripts. No
production application integration, public/remote activation, free-body trial,
NyxID activation, repository mutation, dependency install or model modification
is performed. Steering/approach/capture/retention/fork choice, free walking,
visual/memory/social competition and all historical gates, PR-comment acceptance,
browser/device/remote qualification and broader platform work remain outside
this bounded slice.
