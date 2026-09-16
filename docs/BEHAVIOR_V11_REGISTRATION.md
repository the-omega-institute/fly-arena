# v11 exclusive distal-foot realization audit

This diagnostic does not qualify walking, choose gains, or amend the failed v10
result. The approved plan is authoritative. All 28 historical/cadence-normalized
profiles × seeds 42/43 × seven nonzero conditions are mandatory. Primary samples
are exactly ticks 6000 through 25000 inclusive (19001 per trial, dt=.0001 s).
The full original streams are hash/schema/condition checked. Rows 0..5999 are
used only to reconstruct the observer's native contact solver state; no dynamics
or controller is advanced. No controller is instantiated. No reset or mj_step.

## Frozen references, units, and geometry

Records are actual qpos; recorded position commands substituted through compiled
joint transmissions; and installed PreprogrammedSteps at exactly magnitude r=1
and recorded phases, through the same transmissions. This is the NeuroMechFly
single_steps_untethered asset, not the separate FlyBody asset. Source loader
performs right yaw/roll conversion once; the audit applies no further conversion.
Unit reference contains no hybrid correction; actual commands, magnitudes,
asymmetry and net corrections remain alongside it. The native source equations
and transmission gain/bias/gear are authoritative; force-zero position is solved
algebraically, with a native transmission test. Root and all passive qpos are
identical in the three records. No fitted coefficient, IK, offset or reference
sweep. Counterfactual floor intersection is signed geometric infeasibility at
that frozen root/passive pose; it cannot rule out dynamic body adjustment.

All 30 native tarsus1..5 compiled collision meshes are used without convex-hull
reduction or point sampling. Lowest vertex world z relative to the native plane
is per-link clearance; minimum across five is whole-foot clearance. Earliest link
index wins an exact limiting-link tie; tie counts are retained. The tarsus5
material point is the arithmetic mean of all compiled mesh vertices in its fixed
mesh frame, transformed with the geom transform. It is a reproducible material
centroid, not center of mass or a changing contact point. Native length is mm,
time s, angle rad; forces retain native units without biological interpretation.
Thorax AP is its +x axis; transform is R_thorax.T @ (world_point-thorax_position).
All dense actual transforms must match every recorded 1ms overlap bitwise,
including thorax transforms. Every compiled array must match the frozen arrays.
Native-axis/material-point Jacobians are tested against central finite
perturbations, with no integration. Mesh clearance is independently tested by
explicit world-vertex transforms. Algebraic references are checked against native
actuator lengths/forces and raw spline knots, including right-side signs.

## Prospective AP and phase parser (diagnostic, not admission)

Each leg and EACH of the three records is parsed independently, using its thorax
AP trajectory and the common recorded unwrapped phase. No smoothing or debounce.
Phase must be finite and strictly increasing. Phase cell k is [2pi*k,2pi*(k+1));
observed sample membership uses floor(phase/(2pi)), with no boundary tolerance.
Every observed cell, including initial/final partial cells, is retained. A cell
is complete only if its entry and next-cell boundary are both observed within
the audit window. A skipped integer cell is an explicit missing/degenerate cell.
Earliest global posterior AP minimum in each observed cell is the PEP. Ties are
all samples within 1e-12 mm of the global minimum; earliest tie wins and every
tie tick is retained. Consecutive PEPs from adjacent complete cells bound a
complete diagnostic stride, both endpoints included for metrics; intervals
involving partial cells are retained as partial. Earliest intervening global AP
maximum is AEP, with the same tie rule. PEP..AEP is protraction; AEP..next PEP is
retraction. End maxima, AP range<=1e-12, tied extrema, or extra reversals mark
ambiguity; none is removed. Reversal detection ignores |delta AP|<=1e-12 mm,
collapses zero slopes, and records every remaining sign switch. Expected sequence
is positive then negative. More than one switch, any negative motion in
protraction or positive motion in retraction is explicitly ambiguous. Prefix
before first PEP and suffix after last PEP are retained as unbounded partials.
All records also get metrics on ACTUAL-parser intervals for paired comparisons.
Absent complete strides is an explicit inconclusive condition, never a pass.

For each interval preserve wholefoot peak/minimum clearance, fraction >.02 mm,
floor intersections (<0), per-link minima and limiting-link counts, AP range,
world/body material-point excursion, contact and adhesion duty, and positive
normal-support duty. Comparisons to .02mm/.15mm are descriptive only.

## Original bouts and support

Preserve EVERY maximal constant contact/noncontact run in the audit window,
including boundary partials, one-tick/zero-phase-advance runs. Mark exactly which
meet the original v10 rule: bounded by opposite samples and phase[end-1]>
phase[start]. End is exclusive. Retain original 1ms sample category: missing,
single, multiple; missing displacement is null, single zero is NOT proof of no
slip. Dense .1ms reconstruction is an additional column, not a replacement of
original observations/decision. Match all original qualifying bout boundaries and
metrics to frozen development-decision.json with numerical tolerance 1e-12.

Native ground contacts are reconstructed with mj_forward from recorded qpos,
qvel, ctrl and time sequentially from row0, matching the old diagnostic observer,
without integration. Contact flags (distance<=0) must match every dense retained
row exactly. mj_contactForce yields per-foot summed positive normal force,
including contacts at positive distance if the solver supplies force; record
force-bearing and penetrating-contact distinctions. Force is a reconstructed
instantaneous solver estimate, not a directly retained ground-force measurement.
Validate finite/nonnegative normal forces (negative tolerance 1e-10), native
force-zero actuator equations, and inverse generalized-force balance via the
forward solver's M*qacc+bias-passive-actuator-constraint residual (relative
1e-6, absolute 1e-7). Recorded actuator_force belongs to the preceding integrated
interval and is NOT asserted equal to an instantaneous reconstruction.

Each actual diagnostic retraction is a prospective support envelope. Stitch
material-point displacement from its first positive-normal-support sample
through its last, retaining every internal contact/force gap without debounce
or restarting displacement. Report maximum 3D displacement from first supported
sample, net chord, path length, largest unsupported gap and support duty. No
positive support -> null/unsupported, one support sample -> unresolved. Partial
and ambiguous envelopes stay in the evidence. Also retain displacement over the
entire retraction, so the choice of supported endpoints cannot hide motion.
This is material-point motion, not proof of contact-patch slip or biological gait.

## Realization and decomposition

Per active joint retain command-minus-actual angle RMS/max and native force
summary; raw qpos/qvel/ctrl/correction traces are fixed hash references to inputs.
Passive joint range/RMS and root translation/orientation summaries are included.
At EVERY dense actual sample use mj_jac at the fixed tarsus5 centroid, multiplied
by recorded qvel grouped into root(6), active(42), passive(24). Save the three
world-velocity contributions. Their sum is the native tangent velocity; compare
with centered finite differences of reconstructed material positions (one-sided
at endpoints), reporting residual RMS/max, and integrated trapezoid displacement
residual. Report descriptive correlations of distal vertical velocity/clearance
with active/passive/root contributions, command error, correction and adhesion;
zero variance is null. Neither decomposition nor correlation identifies causes.

## Exclusive output, integrity, and budget

Before outcomes, exclusive registration records this specification hash, all
case inventories, source/asset/input/axes/material-point hashes. Before execution,
a separate exclusive implementation seal binds the finished audit source/tests.
No scientific algorithm changes after execution; failure requires a deviation
return. All writes are new exclusive v11 artifacts; old sources/evidence/assets
are read-only. No import of old recorder, correction runner or physical runner.
Fixed numeric archive keys are ticks/values; metadata is separately JSON encoded
with allow_nan=False. Chunk commits are flushed/fsynced and indexed only after
successful close; a partial failed file is never an accepted chunk. Each 1000-row
chunk is retained incrementally with independently reconstructable source refs.
Failure receipts are attempted independently in finally, with primary error,
last initialized row, last committed chunk and secondary retention errors;
an emergency numeric buffer is attempted on normal flush failure. A failed
terminal write gets a separate fallback receipt in owned scratch. Total
filesystem failure cannot guarantee any durable receipt and is reported to stderr.
Initialized empty cases are retained if execution stops before their first row.

One CPU worker; 90 minutes total from 2026-09-16T16:53:48Z; 8 GiB RSS; 2 GiB total
new files (target source/evidence plus owned scratch); zero physical/neural
seconds, zero parameter sweeps, no installs/network/services/Git/subagents.
BLAS/OpenMP/VECLIB threads fixed to one. Budget checked before registration,
every chunk, every trial and finalization. Reserve 64MiB output headroom; stop
before exceeding 2GiB. Hash/frame/missing/schema/nonfinite/cap mismatch stops
all remaining cases with partial evidence; no alternate algorithm or restart.

All original v10 gates/failure text, 15 neural predicates, untouched seeds
31042/31043 and downstream plan remain unchanged. A successful audit can justify
only a separately registered next physical question, never admission or an API
qualification toggle. Final evidence distinguishes reference feasibility, actual
support estimates, ambiguity, correlations and unresolved causal/dynamic effects.
