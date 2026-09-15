# Genesis Alpha validation

Updated 2026-09-16. This is a living implementation report, not certification that all research gates in ROADMAP.md passed.

## Confirmed locally

- Official full retained MaleCNS import: 165,122 neurons, 25,563,197 directed edges, 124,025,046 synaptic contacts. Manifest SHA256 `473ff8f53214a9a6fecf5b866c4bb11bf6302c938e569898d2ce03fbf3917ccc`.
- Shared engineered readout calibration: 250 controlled-stimulus training observations, held-out mean absolute error approximately 0.098. This validates the engineering fit to the chosen target, not natural fly behavior.
- `pytest -q`: 10 tests passed, including compiler cancellation/roundtrip/bounds, delayed neural events, chunk/checkpoint equivalence, lease fencing, atomic paired-series admission, disjoint physical contact sensors, and tampered/truncated evidence rejection using completed real contests.
- Web TypeScript + production build passed. Browser automation could not create a tab because the browser connector rejected the current authentication method (`unsupported Codex auth method: apikey`). Visual and interactive browser QA is **not yet passed**.
- Full graph + actual body solo, seed 42, 2 seconds: food 0.4032. Historical probe `var/probes/solo-v2`.
- Full graph per contestant + shared physical world, 2 seconds, seed 42: orchard scores `[0.3424, 0.0608]`, independently verified; wall 66.06 seconds on development machine. Receipt `24df3cb8fe20aca03a3eab0b383acc9f307ee14f06a4aa1c6502cf2c7d2cd906`.
- Obstacle garden dual match, 2 seconds: `[0.8704, 0.8]`, independently verified.
- Initial ring geometry: verified exit at tick 13,316 (run ends at sensing boundary 13,400); no inter-fly contact occurred. This is a valid boundary match but **not evidence of pushing**. Ring spawn geometry has subsequently been adjusted symmetrically and requires a fresh run.

## Bugs found and fixed

- FlyGym 2.1 root-level ground sensor names collided between flies. Its sensor lookup was also overwritten on each add. Arena now namespaces sensors and preserves all contestants' mappings; a two-body regression test checks disjoint sensor indices and shared-world stepping.
- Fused MuJoCo head bodies invalidated direct body lookup. A fixed head site now supplies physical sensor transforms.
- Replay evidence manifests now enumerate the intended immutable files, excluding live worker logs.
- The independent judge now rejects early termination unless justified by the ring exit rule, and checks physical/neural final clocks.

## Still limited or pending

- Real graph mutation causality and motor-output ablation: pending recorded experiment.
- Consistent purposeful navigation, naturally plausible behavior and statistically supported genotype advantage are not established. Starter flies frequently pass food and exit after a short walk.
- Visual inputs, online plasticity, aggression circuits, flying dynamics and GPU simulation are not available.
- Independent scoring verifies trusted-worker evidence, food conservation, ordering, clocks, hashes and admitted inputs. It is not a cryptographic proof that arbitrary untrusted worker geometry or event logs are authentic. Production requires stronger admission/isolation and broader adversarial tests.
- Tournament series use repeated seeds and swapped slots. That design does not by itself establish absence of all slot bias. Rankings are exploratory within this workspace.
- Full cross-backend numerical comparison, convergence, fault-injection matrix, backup restore and sustained public load tests remain later engineering gates.
- Remote runtime installation and source synchronization have succeeded; remote preparation and public deployment verification are in progress. No remote throughput number is claimed yet.
