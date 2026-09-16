# Neural-only v4 motor corrective result

Verdict: **partial**. 12/15 unchanged gates passed.

The frozen v2 decoder still supplies exactly two neural outputs. The v4 motor applies smooth high-drive slowing between common decoded magnitudes 0.54 and 0.64, retaining 40% propulsion at the upper threshold. No food, pose, sensory channel or reward enters the motor. Sensor, decoder, body, task geometry, 1.1 mm mouth radius and scientific acceptance thresholds are unchanged.

Selected development candidate: **b**. B feeds in 2/4 cases versus A 1/4; total intake 10.64 versus 4.00, with lower final food distance in every matched case. B still fails gradient42 and fork43 feeding, so this is a bounded engineering candidate, not qualified behavior.

Development used only seeds 42/43, four ten-second trials for each of two bounded candidates. Both pilot evidence trees and motor sources are preserved. The root policy freeze was verified before the untouched 20042–20045 cohort ran exactly once through scripts/qualify_integration_v2.py. Scientific sources stayed frozen throughout that cohort; the subsequent verifier-only repair is identified below.

| Trial | Seed | Intake | Closest thorax distance (mm) | Final distance (mm) | Time within 1.8 mm (s) |
|---|---:|---:|---:|---:|---:|
| heldout-left | 20042 | 0.00 | 1.656 | 1.874 | 0.43 |
| heldout-right | 20043 | 0.64 | 1.092 | 6.479 | 1.24 |
| bifurcation-left | 20044 | 0.00 | 1.351 | 8.506 | 0.85 |
| bifurcation-right | 20045 | 0.00 | 2.548 | 6.566 | 0.00 |

Failed gates: heldout-left-long-approach, bifurcation-left-choice-and-food, bifurcation-right-choice-and-food.

Real in-process HTTP experiment `66454e9d567b40d7b38050fe784340c4` completed one WT/official/design triplet under a shared condition. Intake: wildtype 0.00, official 2.40, design 0.00. These differences do not establish design superiority.

Arena status: **HTTP 422; solo/dual are internal diagnostics only**. No listener, service, deployment or live authentication activation was used.

Verified 41 final scientific source files, 94 historical/frozen files, the policy freeze and all final probe/experiment/arena receipts. Full graph: 165,122 neurons and 25,563,197 structural edges; actual backend cpu-numba.

Historical cohort scientific profile SHA-256: `154da13ba6b500f7d183512a8f37140e22e64e8dbf791831fa9b8f10bd1e9956`.

The subsequent [checkpoint-contract repair](QUALIFICATION_V4.md) changes only verification and its source identity. The profile above still identifies the original cohort and archived sources, not the repaired current verifier. Its complete receipts remain independently verifiable; the recorded 12/15 result and three failures are unchanged. No motor tuning or held-out rerun accompanies that repair, and research-v2 competition remains unavailable.

Evidence: `var/research-validation/qualification-v4/final/acceptance.json`, `qualification.json`, `experiment.json`, `arena.json`, `motor-approach.png`, `heldout-trajectories.png`, `experiment-trajectories.png`; bounded pilot summaries/plots are under sibling `pilot-a` and `pilot-b`.

Reliable food approach and retention remain unproven wherever the recorded trajectories or gates fail. CUDA, biological validity, learning and memory remain unqualified. Historical v3 failed evidence and both frozen readouts were preserved.

Validation: the full Python suite passed 175 tests with zero skips before cohort launch; the final-evidence service/arena/tampering regression passed again after new artifacts existed. Nine targeted motor/source tests passed. Nineteen historical/development probe receipts also verified. Two existing dependency deprecation warnings remain. All five generated pilot/final figures were visually inspected; owned-file whitespace checks passed.
