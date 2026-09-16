# Annotated contact → Ti antagonist candidate v6

**Research implementation complete; neural prerequisite failed; candidate stopped.**
This is a local, versioned contact sensor and six-channel neural motor-intent
interface, with an executed full-connectome assay. It is not an admitted walking
controller, a measured knee displacement, or an improvement to arena behavior.
No existing runtime, graph, weights, sensor, decoder, controller, or behavioral
threshold was changed.

The isolated checkout is `/tmp/fly-arena-contact-v6`, branch
`research/annotated-contact-tibia-v6`, based on
`61a89f6cb94e4a6ff206f3fe1e3a147c535a44b2`. Python and data were read through
explicit original paths. `PYTHONPATH` resolved this checkout's source; bytecode
writes were disabled and Numba cache writes were redirected into this checkout.
There was no install, service, hardware, external operation, commit, or push.

## Fixed interfaces and actual APIs

`src/flyarena/experiments/contact_v6.py` binds all retained raw-annotation rows by
body ID to canonical graph indices. The six afferent groups select
`class=mechanosensory_tactile`, `rootSide=L/R`, and
`entryNerve=ProLN/MesoLN/MetaLN` for fore/middle/hind legs. Counts in
LF/LM/LH/RF/RM/RH order are **151/378/394/115/428/411**. These broad nerve groups
are explicitly lumped contact inputs, not proven tibia/tarsus receptor maps.

Readout uses exact `Ti flexor MN` and `Ti extensor MN` types with `vnc_motor`,
`somaSide`, `somaNeuromere=T1/T2/T3`, and matching exit nerve. All 49 selected MNs
are retained: flexor counts **5/5/9/5/5/8**, extensor counts **2/2/2/2/2/2**.
Each antagonist pool is an arithmetic mean of actual Brain exponential rates.
Each independent leg intent is
`0.10 * clip((flexor_mean_Hz - extensor_mean_Hz) / 100, -1, 1)` radians.
Positive denotes flexion intent only. No physical coordinate sign has been
registered and these values are not joint displacement observations.

The sensor helper accepts six sets of three segment net-force vectors, sums
their norms, and divides by body weight. The FlyGym helper reads
`Simulation.get_bodysegment_contact_forces(..., ground_only=False)` for
`tibia`, `tarsus1`, and `tarsus2`. In FlyGym 2.1.0 this method transforms native
`mj_contactForce` vectors into world coordinates and sums per segment. The native
gravity declaration is `[0,0,-9810]` mm/s². Compiled fly-only body masses times
the norm of compiled gravity have the same native force units as these contact
forces, so the ratio requires no SI conversion. The actual API and gravity
source files are preserved in the evidence. No physical model was compiled or
stepped to qualify this helper after the failed neural gate.

The bridge clears the complete Brain external-current array before applying
`48 * clip(F/W, 0, 1)` mV to selected afferents. Chemical input is zero. Actions
read only neural rates; the sensor has no heading, pose, distance, food, reward,
or target input. There is no CPG or HybridController reflex. The actual existing
`CPUBrainBackend.advance`, `neural_output`, `checkpoint`, and `restore` APIs are
used. Checkpoints include membrane potential, synaptic current, refractory
state, all 19 delayed-event slots, external current, rates, tick, total spike
count, and the six held commands.

## Prespecified actual assay

`scripts/contact_tibia_v6.py` executed **8 × 0.6 seconds**: blank, one unit
force/weight pulse for each of six legs, and one exact LF repeat. Every run
restored the same complete rest checkpoint; there are no nominal independent
neural seeds. Pulse intervals are exactly `[0.2,0.4)` seconds. The LIF time step
is 0.1 ms and sampling is every 100 steps (10 ms). No input subgroup, gain,
selector, threshold, fixture, or model search was performed.

The graph contained **165,122 neurons and 25,563,197 edges** with canonical
baseline weights. Recorded observers include all 1,877 afferents, 49 selected
MNs, all 1,314 DNs, and all 1,620 structurally identifiable two-hop VNC
intermediaries: afferent successors intersect MN predecessors, restricted to
`vnc_intrinsic`. This is a structural observer rule, not proof of functional
mediation. The union contains 4,860 neurons.

Each run records 61 endpoint rate/current/command frames (including rest),
60 force/current/held-command intervals, per-neuron spike counts per interval,
whole-graph spike totals, and complete checkpoints at 0, 0.2, 0.4, and 0.6 s.
An additional common rest checkpoint is retained: **33 complete checkpoints**
in total. `protocol.json`, source snapshots, selector IDs, annotation records,
graph/source/schema hashes, dependency versions, and rest state were registered
before neural integration. The complete run, including setup and evidence
writing, took **22.669652 seconds** on the local CPU.

Before running, the assay fixed the incremental-magnitude window to endpoint
samples 0.21–0.40 s. An own-leg response must exceed 0.001 rad for five consecutive
samples and end at no more than 20% of its pulse peak. At least one left and one
right channel, including both forelegs for the bilateral body stage, must pass.
Any raw antagonist command reaching the clipping boundary in any channel/run
rejects the panel. The complete LF repeat must agree bitwise. These explicit
engineering interpretations were frozen in the registration, not chosen from
the observations.

## Measured rejection

All values below are neural motor intent, not physical knee motion. The blank
had zero spikes and zero commands. Peak magnitudes are blank-subtracted own-leg
values during the pulse. Extensor columns are the peak group mean over the run.

| Pulse | Afferent peak mean Hz | Own extensor peak mean Hz | Own intent peak magnitude rad | Consecutive samples >0.001 | Final/peak | Saturated channel-samples |
|---|---:|---:|---:|---:|---:|---:|
| LF | 179.295542 | 67.315578 | 0.067315578 | 19 | 0.021380 | 0 |
| LM | 165.621709 | 233.592152 | 0.100000000 | 20 | 0.048941 | 21 |
| LH | 172.845301 | 68.805446 | 0.068805446 | 19 | 0.012980 | 0 |
| RF | 181.506486 | 0.000000 | 0.000000000 | 0 | undefined | 0 |
| RM | 165.639031 | 197.840652 | 0.100000000 | 20 | 0.040052 | 19 |
| RH | 167.916196 | 138.680799 | 0.100000000 | 20 | 0.027098 | 15 |

The RF input generated **4,235 afferent spikes and 18,305 whole-graph spikes**,
but **zero spikes and zero rates in both own RF antagonist pools**, hence an
exactly zero own RF command. Activity reached other outputs: the LM command
reached −0.042458441 rad in that RF run. This rules out a globally silent input
or integrator as the explanation for this measurement, but does not establish
an absent anatomical path or physiological causation.

LM/RM/RH each saturated their own channel, including post-pulse endpoint
samples where applicable, for **55 channel-samples total**. Their extensor
activity exceeded the fixed 100 Hz difference scale. Own flexor pools had zero
spikes in five of six pulse conditions; LH flexors emitted two spikes and had a
peak mean rate of 3.953744 Hz. Five own channels passed magnitude and decay,
but **the bilateral foreleg requirement and no-saturation requirement failed**.

LF and LF-repeat matched all sample arrays and all complete checkpoints exactly.
Independent verification passed evidence integrity and recomputed the rejected
gate. No neural retuning or new candidate followed.

## Independent verification and reproduction

`scripts/verify_contact_tibia_v6.py` does not import the candidate module or its
decoder. It independently hashes recorded files and canonical data, rebinds
selectors from raw annotations, checks the canonical baseline weight bytes,
reconstructs intermediary membership, checks exponential-rate bounds against
recorded spike counts, checks full checkpoint/trace correspondence, recomputes
neural-only commands and all gates, and compares the exact repeat. This verifies
the recorded evidence without running an additional scientific condition.
It is not an independent implementation of the entire LIF integrator.

Exact commands, run in `/tmp/fly-arena-contact-v6`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/fly-arena-contact-v6/src NUMBA_CACHE_DIR=/tmp/fly-arena-contact-v6/var/contact-v6/cache /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python -m pytest -q tests/test_contact_v6.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/fly-arena-contact-v6/src NUMBA_CACHE_DIR=/tmp/fly-arena-contact-v6/var/contact-v6/cache /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python scripts/contact_tibia_v6.py --data /Users/lexa/Desktop/lexa/omega/fly-arena/data --output /tmp/fly-arena-contact-v6/var/contact-v6/assay-001
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/fly-arena-contact-v6/src NUMBA_CACHE_DIR=/tmp/fly-arena-contact-v6/var/contact-v6/cache /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python -m pytest -q tests/test_contact_v6.py tests/test_backend.py tests/test_architecture.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/fly-arena-contact-v6/src /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python scripts/verify_contact_tibia_v6.py --data /Users/lexa/Desktop/lexa/omega/fly-arena/data --output /tmp/fly-arena-contact-v6/var/contact-v6/assay-001
```

Results: initial candidate tests **4 passed in 0.93 s**; targeted candidate,
backend and architecture regression checks **15 passed in 0.56 s**; assay and
independent verifier each exited 0. Exit 0 means execution/integrity succeeded,
not that the scientific gate passed. The authoritative gate is
`neural_prerequisite_pass=false` in `verification.json`.

The runner refuses an existing output directory; never overwrite this assay.
For read-only reverification of existing evidence, load the verifier module
and call `verify(output_path, data_path)` rather than its write-once CLI.
Use a fresh output path only when a separately authorized replay is needed.

Primary evidence is `var/contact-v6/assay-001/` (about 35.2 MB):

- `registration.json`: SHA-256 `407b2f535a766db3a420fab477ed758db266a0b4e942eefee291aeae5431f2d4`.
- `inventory.json`: SHA-256 `4c700c32b40179421dbffde7f239e4c467e923f0ef5dc8c7a505a5f66497c624`; hashes every registered source, record, and checkpoint, excluding the subsequent verification report itself.
- `verification.json`: authoritative independent outcome, with group spikes/rates, gates, and inventory/registration anchors.
- `source/`: exact implementation, backend, Brain, checkpoint-contract, verifier, and inspected FlyGym source snapshots.
- `../commands.json` and `../delivery-manifest.json`: exact command receipts and hashes of deliverable source/tests/docs and reports.

Runtime: Python 3.12.13, NumPy 2.5.3, Numba 0.67.0, PyArrow 23.0.1,
FlyGym 2.1.0, MuJoCo 3.9.0. FlyGym and MuJoCo were inspected, not used for a
body trial.

## Stop boundary and remaining goal gaps

**Body qualification: NOT RUN.** The ±0.05 rad coordinate-sign pulse, foreleg
neutral-pose actuator adapter, frozen physical contact fixtures, 12 matched
one-second continuations, afferent/output clamps, identity shuffle, blank body
controls, uprightness, passive collision separation, and >0.01 rad knee
qualification all remain unexecuted because the prerequisite failed. No model
or gain was adjusted to escape that stop. The action interface presently emits
six held neural intents; it has no production or physical actuator wiring.

**WT/official/user 12×2 s physical comparison panel: NOT RUN.** No successful
user-fly effect, walking, capture, retention, or strategy improvement is claimed.
The 15 old behavioral gates were left unchanged and were not rerun for this
rejected bridge. Existing provenance, matched UI comparisons, platform/Chrono
ports, and inactive NyxID integration were preserved by leaving their source
untouched. Olfactory approach/fork/capture, recurrent persistence in that
separate pathway, richer modalities, memory/fight/survival, design-dependent
embodied strategies, fresh behavioral validation, UI/device verification, and
reviewed source synchronization remain outside this completed stopped stage.

The next causal question, for a separately approved candidate, is why this fixed
RF tactile drive reaches other leg outputs while both annotated RF Ti pools
remain silent, and why the same fixed transfer overdrives three other pools.
This result alone does not justify a gain change, an anatomical subgroup search,
or a physiological claim. There were **no plan deviations**.
