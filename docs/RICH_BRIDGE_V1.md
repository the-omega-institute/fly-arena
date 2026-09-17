# Rich odor, obstacle-touch and excursion bridge v1

This is one **implemented source candidate**, not an admitted or qualified
behavioral profile. Its ID is `rich-odor-obstacle-touch-excursion/v1`.
`profile_manifest()` reports `ready=false`, `research_only=true` and
`qualified_base=false`. All admission requests, including research, production
and CUDA requests, fail. Existing profiles, routes, readiness flags, scientific
files and the original 259-second qualification are unchanged.

The mechanical source base is preserved v15 at
`d84169e547ffad2416c455bf1699ecd53f91a4bd`. Its use here does **not** qualify its
gait. Physical use requires a later qualified mechanical base, a refrozen joint
profile, separate authorization, and independent review. No model was constructed
and no neural, controller, CPG, physics, or detached kinematics step was run in
this implementation task.

## Concrete source interfaces

- `rich_bridge_v1.py` implements the four-channel sensory frame, contact latch,
  frozen DN kernel algebra, unchanged v4 transfer, separate Q rate projection,
  synchronous boundary proposal/commit, owned checkpoints and closed admission.
- `rich_bridge_v1_maps.json` contains frozen body IDs and row indices, preserving
  original ORN and DN order. `rich_bridge_v1_seals.py` pins that artifact, the
  existing readout asset, and reused source hashes. No graph edges are included.
- `rich_bridge_v1_controller.py` provides `RichBridgeController.step(intent, obs)`
  with an explicit three-value signature. Its `_advance` is the original v15
  implementation with only the additional argument and the approved amplitude
  assignment changed. It does not forward three values to the old two-drive API.
- `rich_bridge_v1_body.py` provides read-only compiled metadata bindings and a
  `RichBodyAdapter` source path. It snapshots all supplied same-tick allocation
  observations, validates all subjects, proposes actions on private controller
  copies, assembles the compiled actuator controls, then contains exactly one
  shared-world step. Its public `step` always refuses admission before reaching
  that path. This gate is intentional and must not be bypassed to obtain a trial.

`BridgeState.from_canonical(metadata_root, geometry)` is the canonical source
factory. It checks frozen `ids.npy`, `side.npy`, and manifest hashes, matches each
selected body ID and bilateral side, and verifies the existing readout NPZ hash.
It verifies the reused neural kernel source through the joint profile manifest.
The lower-level constructors also support explicitly authored tiny fixtures;
those constructors do not certify canonical metadata or authorize execution.

`geometry_from_existing(body, subject, obstacle_names, controller)` consumes an
already compiled body and its source-owned segment metadata. It binds all geoms
for all 48 required leg segments, independently checks compiled ownership, and
rejects missing or silently omitted geometry. Ground, self/non-leg geometry and
other flies are excluded. Only explicitly named external `obstacle-*` geometries
can trigger this first candidate. The actuator factory checks the actual 42
position plus six adhesion addresses, names, joint transmission, DOF and leg
order. Its identity is included in the geometry binding and therefore the bridge
binding. These factories were inspected as source; the real compiled factories
were not exercised. Tests use small authored metadata records.

The model hash used for v15 allocation observations is preserved for compatibility.
It identifies the specified compiled arrays, not a complete native-engine
checkpoint. Full native-model/state binding remains part of the later delegated
restore and mechanical qualification gate.

## Frozen sensory and neural projection

The input order is exactly:

| Channel | Meaning | Population | External current |
| --- | --- | --- | --- |
| `odor_left` | unchanged `encode_odor` left value | original 884 left ORNs | `48 * value` |
| `odor_right` | unchanged `encode_odor` right value | original 1,344 right ORNs | `48 * value` |
| `tactile_left` | binary left-leg obstacle contact latch | 1,264 left tactile neurons | `48 * value` |
| `tactile_right` | binary right-leg obstacle contact latch | 1,294 right tactile neurons | `48 * value` |

Encoded values are dimensionless in `[0, 1]`; current is mV-equivalent using the
existing backend convention. Every boundary starts with an all-zero external
array, so unselected neurons receive zero and no tonic drive is added. The tactile
selector is exactly `superclass=vnc_sensory`, `class=mechanosensory_tactile`, and
`side=L/R`. The 48 mV broadcast is an engineered approximation, not measured
mechanoreceptor tuning.

The existing 1,314-neuron descending kernel and unchanged v4 `MotorTransfer`
produce two drives `u`. The distinct third readout Q contains exactly 49 neurons
with `superclass=vnc_motor` and type in `Ti flexor MN`, `Ti extensor MN`: 37 flexor,
12 extensor, 25 left and 24 right. This anatomical membership does not establish
a muscle assignment, natural step command, or reachable independent control.
No CNS coordinate is used to infer a leg or side.

The new projection and filter are fixed:

```text
m = clip(mean(rate[Q]) / 100 Hz, 0, 1)
beta = exp(-0.010 / 0.050)
q_next = beta*q + (1-beta)*m
e = 1 - 0.25*q_next                 # [0.75, 1]
c = mean(u)                         # [0, 0.4]
a = (u_right-u_left)/(2*c) if c else 0  # [-0.8, 0.8]
```

The pinned neural source decays its rate state by `exp(-0.1/50)` at a 0.1 ms
base tick, adding `(1-rate_decay)*10000` per spike. Its numerical unit is Hz and
its time constant is 50 ms. This is a static source observation, not an executed
neural response result.

All-selected-readout exact silence, or explicit output-off, clears both the new
Q filter and the old decoded/motor filter authority and holds intent `(0,0,1)`.
Q alone cannot start movement from rest. The controller preserves the v15 silence
hold and, above that threshold, uses:

```text
intrinsic_freqs = base_freqs * (c/0.6)
coupling_weights = base_coupling * (c/0.6)
intrinsic_amps = e * repeat([1-a, 1+a], 3)
# exactly the original one CPG step follows in its original native ordering
```

At fixed `c,a`, `e` changes only nominal amplitude. No phase injection, gain knob,
new trained head, global monkeypatch, or runtime AST rewriting is present. The
original reflex, persistence, adhesion, normal allocation, limit checks, and
shadow commit code are preserved. This is a source/algebra statement; its actual
joint trajectory and physical effects have not been run.

## Integer clock and state ownership

The base tick is 0.0001 seconds and a sensory/readout interval is exactly 100
base ticks. A contact record retains the completed solve's **prestate tick**,
solver contact index, owned geometry, obstacle geometry and signed distance.
The latch observes every tick, including empty contact sets; gaps, duplicates,
incomplete intervals and mismatched model identities fail.

At boundary tick `t`, the host has already copied contacts from `[t-100,t)` for
every subject. `snapshot_boundary` copies all subjects' local raw odor and
current neural rate arrays before any injection/decoding. `commit_boundary`
validates every complete frame and every proposed next state before writing any
external array or owned state. The resulting currents and `(c,a,e)` are held for
the next interval. Newly injected current cannot affect the already snapshotted
rates; its first possible influence is the next readout. No browser time, reward,
global goal position, or direct scene-to-motor shortcut enters the decoder.

`checkpoint()` covers every bridge-owned dynamic field: interval and boundary
ticks, contact latches and event provenance, held four-channel frame and current,
both old filter states, new Q filter, and held intent. `restore_owned()` validates
all fields, shapes, dtypes, domains, identities, current/frame consistency,
filter/intent consistency and reconstructed contact provenance before committing.
It copies mutable arrays and nested state; caller and subject aliases are rejected
or eliminated.

These are **owned bridge checkpoints, not complete experiment checkpoints**.
The controller snapshot includes its native controller/CPG/RNG state, but controller
restore and body restore deliberately fail closed. `restore_full()` also refuses.
A later complete restore must bind and atomically restore neural arrays, all
clocks, native integration state and solver cache, controller/reflex/CPG/RNG state,
actuator identities and the bridge snapshot. A render snapshot or existing
key-only v15 restore is not accepted as full restoration.

## Verification and outstanding gates

The focused suite has 60 passing checks, under a 60-second phase watchdog with
numerical thread settings fixed to one. An import blocker excludes scientific
engines/backends and an audit hook refuses graph-edge files, network and
subprocesses. The fixtures use nine-element authored rate arrays, a one-row
kernel, small coupling arrays, copied fake contacts and 48 segment metadata rows.
The controller is parsed and compared as source, never imported or stepped.

The initial run had 58 passing checks and two verification failures. The approved
ID hashes serialize numeric IDs, while the artifact stores decimal ID strings;
the assertion now uses the approved numeric serialization. Checkpoint equality
now compares all values, dtypes, shapes and nested state, with explicit alias
checks, instead of pickle object memoization bytes. No candidate source change
was needed to resolve those two failures. Both run receipts are retained.

Final fixture phase: 60 passed in 0.40 seconds (0.52-second wrapper phase),
53,837,824 bytes observed maximum RSS. Selector freeze: 0.73 seconds,
190,087,168 bytes observed maximum RSS. No OS memory or CPU-affinity isolation is
claimed. Source and fixture hashes, exact preserved baseline, resource receipts,
selector provenance and the closed inventory are in the delivery bundle.

Still unrun/unqualified: real compiled factory binding; neural response to touch;
reachable independent Q variation; DN behavior outside odor-only training support;
actual controller execution and native allocation feasibility; amplitude-to-joint
and body effects; stable mechanical behavior; full neural/native restore;
WT/official/user matched causal phenotype; original 259-second gates; CUDA;
rendered/live MVP behavior. This delivery provides executable contracts and an
explicit future body consumption path, with no biological validation, causal
phenotype result, production readiness or active capability admission.


## Separately sealed fix1 validation correction

The original source candidate and its sealed delivery remain unchanged historical
identities. Fix1 corrects two validation gaps found in independent review, using
one registered correction pass. Its joint profile source seal changes; prior
fixtures or evidence do not claim execution of the corrected source.

`commit_boundary` accepts writable native contiguous `float64` destinations only.
A contiguous view is supported when existing cross-subject and rate alias checks
also pass. Zero-stride, internally overlapping, reversed and strided destinations
are rejected across the whole batch before any destination or bridge-owned state
is committed. No hidden destination copy or runtime layout fallback is used.

`bind_geometry_metadata` requires each explicitly named `obstacle-*` geometry to
have the compiled owner `world`, matching the preserved Bodies builder. A name
alone cannot admit self anatomy or another fly as an obstacle. Ground, self and
other-fly exclusion and the complete 48-segment leg binding remain in force.

Eight new tiny cases cover late-participant destination refusal with unchanged
state/backing storage, valid contiguous-view current delivery, self/other-fly
obstacle-owner refusal, and valid world-obstacle contact with excluded geometry.
Before correction, six rejection checks fail and two positive controls pass.
The existing 60 checks and eight additions pass after correction. Scientific
imports stay blocked; no actual compiled factory, controller, CPG, neural,
physics, kinematics or model execution is part of these checks. Admission and
full/native restoration remain closed; all earlier qualification gaps remain.
