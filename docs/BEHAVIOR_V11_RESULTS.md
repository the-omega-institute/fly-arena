# Distal-foot realization audit v11 — complete diagnostic, no gait admission

All 28 required nonzero development cases and all three fixed kinematic records
are complete. The audit covers ticks 6000..25000 inclusive, using every retained
0.1 ms qpos: **532,028 times / 1,596,084 record-times**. No physical integration,
reset, controller advancement, neural trial, parameter sweep, gain selection,
lift offset or IK was performed. The original v10 development failure is unchanged.

## Main diagnosis

**Hind-foot scuffing extends across the full panel, not merely the two motivating
contact-free bouts.** Tarsus5 sets whole-foot minimum clearance at every dense
hind sample in actual, command and unit-reference records. No actual hind foot
reaches 0.02 mm anywhere in any of the 28 audit windows. Historical maxima are
0.002875 mm (LH) and 0.003233 mm (RH); cadence maxima are 0.006212 mm (LH) and
0.009726 mm (RH), including partial intervals. This conclusion does not depend
on the parser successfully identifying a clean stride.

The source equation reproduces every retained command exactly. The native
transmissions/axes, compatible asset and exactly-once original right yaw/roll
conversion check out. A generic axis/sign bug is not supported by this evidence.
At the same root/passive pose, historical hind command geometry intersects the
floor throughout every window. Cadence hind command geometry intersects the
floor in 95.75–100% of window samples. Tracking error exists, but perfect tracking
of those frozen-pose targets would usually drive the hind mesh into the floor;
it would not generally yield a clear protraction. This rules out a *tracking-only
explanation at the retained pose*, not every possible dynamic tracking remedy.

The unit reference offers limited geometric headroom but does not establish a
complete fix. It exceeds 0.02 mm somewhere in 9/14 cadence LH windows and 8/14 RH
windows. Its hind mesh still intersects the floor during 90.02–100% (LH) and
92.20–100% (RH) of entire windows. Those are **counterfactual floor intersections**,
not integrated outcomes, anatomically impossible poses, or proof that a freely
adjusting body could never walk.

## Phase/AP alignment and ambiguity

The registered parser retains each increasing 2π cell, earliest posterior
minimum, earliest intervening anterior maximum, all ties/reversals, and all
partial/degenerate intervals. Each reference is parsed independently and is also
measured on the actual record's intervals. These are diagnostic intervals, not
new admission predicates. No ambiguity was removed to improve a result.

| Record, measured on the same actual hind intervals | Historical protractions >0.02 mm | Cadence protractions >0.02 mm | Cadence whole intervals >0.02 mm |
|---|---:|---:|---:|
| Actual | 0/581 | 0/168 | 0/168 |
| Recorded command at actual root/passives | 0/581 | 1/168 | 11/168 |
| Source-native r=1 at actual root/passives | 3/581 | 17/168 | 90/168 |

On the unit reference's *own* AP segmentation, cadence has 76/168 hind
protractions above 0.02 mm, versus only 17/168 on actual protractions. Thus the
apparently promising reference lift is frequently out of alignment with actual
foot progression. Averaged across the same actual hind protractions, command
and unit-reference floor-intersection fractions are 99.874% and 98.319%,
respectively. These interval means give equal weight to each interval; the
window fractions above weight samples.

All 509 complete cadence intervals across all six legs are ambiguous under the
registered no-smoothing reversal rules. Historical has 1,729 ambiguous of 1,745
complete intervals. Extra reversals are explicit observations, not a reason to
discard a case. Cadence seed42 straight0.08 LH has **no complete interval** because
the window lacks the required pair of adjacent complete phase cells; its full
dense window, partial intervals and original bouts remain analyzed. Stride
qualification there is explicitly inconclusive. All 8,778 parsed intervals are
retained, including 1,008 unbounded prefix/suffix intervals; cells and ties remain
in each case's parsed.json. Clearances above are not asserted to represent
unambiguous natural locomotor cycles.

## Contact, positive support and displacement

All **178,073** original constant-contact runs are retained, including boundary
partials and one-tick/zero-phase-advance runs. All **165,766** runs meeting the
original v10 predicate reproduce the original boundaries and sparse metrics to
1e-12 mm. The new dense measurements do not replace the original decision.

For cadence, the original 30,820 qualifying contact-free bouts retain their
17,532 missing, 11,063 single and 2,225 multiple geometry-sample categories.
The 27,857 qualifying stance bouts retain 16,289 missing, 10,788 single and 780
multiple categories. **Every one of those 10,788 single-sample stance zeros has
positive material-point displacement at dense resolution.** None of the dense
original qualifying stance bouts reaches 0.15 mm; their maximum displacement
from the first dense sample is 0.036301 mm. This anchor differs from the first
sparse sample, so the maximum need not equal or exceed the old sparse maximum.
Missing measurements and one-sample zeros cannot establish zero slip.

The recorded contact flag means any foot contact with distance<=0. Sequential
native mj_forward observation reproduces that flag exactly at every retained
time. It also yields positive normal force on **52.995% of cadence contact-free
foot samples**, and 78.008% of historical contact-free samples. Contacts can
supply force at positive distance under the native contact model; 1.20–34.94%
of summed per-condition/leg normal force comes from those contacts. Therefore
old contact-free segmentation does not reliably denote absence of support.

These normal forces are **instantaneous native solver reconstructions**, not
retained original ground-force measurements. Contact flags and geometric frames
are independently matched; generalized-force balance residual is at most
2.558e-13 native units. This validates reconstruction consistency, not exact
historical contact-force equality or biological force fidelity.

A prospective support envelope is each actual AEP-to-next-PEP retraction, keeping
all numerical contact/force gaps. Its displacement is not restarted at each
small gap. Of 509 cadence complete envelopes, 16 have no positive support and
8 have only one positive-support sample. Among the remainder, 85 show material
point displacement >=0.15 mm; maximum is 1.172581 mm (seed43, turn-positive0.8,
RF, ticks8661..13014), including a 66.5 ms unsupported gap. All those intervals
are ambiguous, and gap-spanning material motion is **not proof of loaded
contact-patch slip**. Historical has 40/1,745 such large envelope displacements,
maximum 0.294542 mm. The original sparse stance result remains verbatim below.
The new observation is that fragmented bouts can hide motion over a broader
support/retraction envelope, not that v10 has been retroactively regraded.

## Commanded versus realized, root and passive motion

Raw qpos/qvel/commands/phases/magnitudes/adhesion/corrections/actuator forces remain
fixed references to the original inputs. Dense evidence adds per-link geometry,
material trajectories and native Jacobian velocity contributions. Every active
and passive joint has a range/error summary; the dense original joint traces are
not duplicated. Reference root and all 24 passive joints exactly equal actual.

Maximum per-joint command-tracking RMS across the panel is 0.113417 rad. For
cadence hind legs, each condition's maximum joint RMS ranges 0.058496–0.088157
rad. Hind passive-joint excursions reach 0.439207 rad at the proximal passive
hinge; they are not negligible fixed straight extensions. At actual qpos,
centroid velocity is decomposed into root(6), active(42), passive(24) DOFs.
Cadence hind vertical component RMS ranges are 2.274–7.360 mm/s (root),
3.736–10.172 mm/s (active), and 1.374–3.760 mm/s (passive). RMS components are not
additive and their amplitudes are not intervention effects.

Correlations of finite-difference hind vertical velocity with those components
range -0.010..0.049 (root), 0.329..0.655 (active), 0.500..0.694 (passive).
Clearance versus tracking-error-norm correlations range -0.293..0.542. Historical
net hybrid correction is identically zero; cadence maximum absolute retained net
correction is 9.882732. Neither that difference nor these correlated motions
identifies a causal culprit. No reflex/adhesion/gain/passive adjustment is selected.

The instantaneous tangent decomposition is approximate as an explanation of
sample-to-sample realized motion: maximum coordinate finite-difference residual
RMS is 7.237887 mm/s; maximum integrated coordinate displacement residual is
0.028160 mm. These residuals are reported explicitly; no claim of exact dynamic
attribution or exact slip velocity follows from the Jacobians.

## All 28 conditions

The table uses complete **actual** hind intervals for unit-reference comparisons,
including every ambiguous interval. Peak columns use the **entire dense window**,
including partials. H=historical, C=cadence-normalized-hybrid-v10. All front/middle
legs and all three independently parsed records are in the 504-row CSV and figure.

| Profile | Seed | Condition | Actual LH window peak mm | Actual RH window peak mm | Unit r=1 protractions >0.02 / actual hind intervals |
|---|---:|---|---:|---:|---:|
| H | 42 | straight-008 | 0.001067 | 0.001085 | 0/41 |
| H | 42 | straight-02 | 0.001835 | 0.001800 | 0/41 |
| H | 42 | straight-04 | 0.002762 | 0.002846 | 0/41 |
| H | 42 | turn-negative-04 | 0.001947 | 0.001770 | 0/41 |
| H | 42 | turn-positive-04 | 0.002098 | 0.002188 | 0/41 |
| H | 42 | turn-negative-08 | 0.002422 | 0.002274 | 0/41 |
| H | 42 | turn-positive-08 | 0.002064 | 0.003233 | 0/42 |
| H | 43 | straight-008 | 0.001122 | 0.001307 | 3/42 |
| H | 43 | straight-02 | 0.001707 | 0.001750 | 0/42 |
| H | 43 | straight-04 | 0.002875 | 0.003166 | 0/42 |
| H | 43 | turn-negative-04 | 0.001922 | 0.001768 | 0/42 |
| H | 43 | turn-positive-04 | 0.002235 | 0.002099 | 0/42 |
| H | 43 | turn-negative-08 | 0.002174 | 0.002224 | 0/42 |
| H | 43 | turn-positive-08 | 0.002795 | 0.002210 | 0/41 |
| C | 42 | straight-008 | 0.003162 | 0.003589 | 0/1 |
| C | 42 | straight-02 | 0.003185 | 0.004266 | 0/11 |
| C | 42 | straight-04 | 0.003454 | 0.003565 | 0/27 |
| C | 42 | turn-negative-04 | 0.003281 | 0.004066 | 0/11 |
| C | 42 | turn-positive-04 | 0.004322 | 0.004755 | 1/11 |
| C | 42 | turn-negative-08 | 0.005485 | 0.005494 | 4/11 |
| C | 42 | turn-positive-08 | 0.005673 | 0.009726 | 3/12 |
| C | 43 | straight-008 | 0.002858 | 0.002881 | 0/2 |
| C | 43 | straight-02 | 0.002844 | 0.003065 | 0/11 |
| C | 43 | straight-04 | 0.003457 | 0.003548 | 0/26 |
| C | 43 | turn-negative-04 | 0.003247 | 0.003871 | 0/11 |
| C | 43 | turn-positive-04 | 0.005779 | 0.004044 | 0/12 |
| C | 43 | turn-negative-08 | 0.005569 | 0.006342 | 5/11 |
| C | 43 | turn-positive-08 | 0.006212 | 0.005820 | 4/11 |

## Decision and one bounded next physical question

**The audit is complete; selection of a physical remedy remains causally
inconclusive.** Source-native excursion has enough whole-interval geometric
headroom to merit a controlled question, but neither its frozen-body feasibility
nor its AP alignment is robust enough to declare an amplitude remedy established.
No candidate, gain or offset is chosen or run by this audit.

The bounded next question is: **Can source-native excursion be realized as
>0.02 mm actual hind-foot clearance during actual protraction, with freely
responding root/passive posture, while preserving the existing support,
upright, speed, turn and stop bounds?** A later, separately registered single
physical candidate must define its commands, parser/ambiguity handling, state
restoration, resource budget and full development panel before outcomes. The
present fixed-root intersections cannot answer that dynamic question. The
all-condition reference/actual timing mismatch and support-envelope evidence
must be part of that prospective test, rather than hidden by a passing peak.

Mechanical qualification, untouched seeds31042/31043, exact repeat and active
physical restoration remain prerequisites. Downstream remains unchanged:
fullgraph40s development;59s evaluation of all original15 predicates;
120s WT/official/submitted matched phenotypes +10s repeat +30s ablations, original
subjects and mirrored conditions, with an observable neural-linked effect erased
by output ablation; then the existing Lab/API/100Hz replay product path. No
neural, sensor, transfer, public API, Chrono port, identity or qualification toggle
was changed. The broader walking/phenotype product goal remains unmet.

## Original failure, verbatim

> All14 nonzero candidate trials fail swing and stance. Of30820 complete contact-free bouts,17532 lack a1ms geometry sample;12926 of13288 sampled bouts fail peak clearance>0.02mm. Of27857 stance bouts,16289 lack a geometry sample. All sampled stance displacements are below0.15mm; maximum0.0366065092mm. Stance failure is missing measurement, not demonstrated excessive slip.

## Evidence and validation

- Registration: `var/behavior-v11/audit-01/registration.json`, its exclusive
  pre-outcome clerical deadline addendum, `inputs.json` (2,023 bound files),
  `native.json`, and `implementation-seal.json`.
- Dense fixed-schema archives: 560 chunks, 288 columns, 19,001 rows per case;
  each committed chunk has its own SHA256 receipt. Metadata records raw case
  identity and reconstructable source references; no pickle in new evidence.
- `all-conditions.json` and each case's `summary.json`, `parsed.json`,
  `paired.json`, `original-bouts.json`, and terminal receipt.
- `report/all-case-leg-records.csv`, `paired-actual-strides.csv`,
  `support-envelopes.csv`, `original-bout-inventory.csv`, `facts.json`,
  `cross-tabs.json` and `verification.json` preserve all conditions.
- Static scientific figures [all-condition plot](evidence/behavior-v11/all-conditions.png) and
  [representative all-leg plot](evidence/behavior-v11/representative-all-legs.png) were generated and visually inspected.
  The representative is the prereferenced seed42 straight0.2 condition, all six
  legs and the entire registered window; it is not clearance-selected.
- 17 contract tests pass, including all native active/passive/root axes, raw
  spline knot/sign/order checks, force-zero transmissions, explicit full-vertex
  geometry, parser ties/reversals/partials, contact-gap stitching and independent
  failure/total-filesystem-failure fixtures. These are not physical trials.
- Runtime: exact commands at all532,028 times; bitwise actual contact/thorax
  agreement; all53,228 geometry overlaps bitwise equal; all165,766 original bout
  boundaries/metrics reproduced. Final independent saved-archive check covers
  every chunk/case/record, interval/contact partitions and all504 CSV rows;
  2,520 explicit world-mesh checks have maximum clearance error2.78e-17 mm.
  Frozen inputs and implementation hashes match at final verification.
- Audit process:266.28s wall, peak RSS669,827,072 bytes; task wall includes setup,
  tests, reporting and finalization. New files approximately1.21GB before final
  receipts, below2GiB. One CPU worker and fixed one-thread BLAS settings; zero
  physical/neural seconds/sweeps/installs/network/subagents. Final exact resource
  receipt records the complete task interval.

All output paths are exclusive. On a failure, initialized cases and committed
prefixes remain; primary and retention errors have independent finally receipts,
with owned-scratch fallback. No durable receipt can be guaranteed under total
filesystem failure; that limitation is explicit and fault-tested. No failure or
cap stop occurred in this audit. The original recorder and unaccepted correction
runner are neither imported nor used.
