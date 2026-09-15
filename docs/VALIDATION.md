# Genesis Alpha validation

Updated 2026-09-16. This is a living implementation report, not certification that all research gates in ROADMAP.md passed.

## Confirmed locally

- Official full retained MaleCNS import: 165,122 neurons, 25,563,197 directed edges, 124,025,046 synaptic contacts. Manifest SHA256 `473ff8f53214a9a6fecf5b866c4bb11bf6302c938e569898d2ce03fbf3917ccc`.
- Shared engineered readout calibration: 250 controlled-stimulus training observations, held-out mean absolute error approximately 0.098. This validates the engineering fit to the chosen target, not natural fly behavior.
- `pytest -q`: 12 tests passed, including compiler cancellation/roundtrip/bounds, delayed neural events, chunk/checkpoint equivalence, lease fencing, atomic paired-series admission, disjoint physical contact sensors, and tampered/truncated evidence rejection using completed real contests.
- Web TypeScript + production build passed. Browser automation could not create a tab because the browser connector rejected the current authentication method (`unsupported Codex auth method: apikey`). A subsequent Computer Use fallback in Safari successfully rendered the design workbench and anatomical model, authenticated a local test designer, and completed server budget validation. The same designer subsequently published `UI Nectar Verified`, submitted match `69e6d2218eea43f0858dbe60f5a0fae1`, received an automatically loaded verified replay and scrubbed its timeline while the displayed real neural rates changed. Screenshots: [design](screenshots/design.png), [arena](screenshots/arena.png). Mobile layout has responsive CSS but has not received a separate device QA pass.
- Full graph + actual body solo, seed 42, 2 seconds: food 0.4032. Historical probe `var/probes/solo-v2`.
- Full graph per contestant + shared physical world, 2 seconds, seed 42: orchard scores `[0.3424, 0.0608]`, independently verified; wall 66.06 seconds on development machine. Receipt `24df3cb8fe20aca03a3eab0b383acc9f307ee14f06a4aa1c6502cf2c7d2cd906`.
- The initial obstacle match `[0.8704, 0.8]` was superseded after discovering disabled body-level collision masks. With corrected precompiled masks, the actual walls block both flies: `[0, 0]`, neither exits, finite physical state throughout. It is a working obstacle task but does not establish navigation competence.
- Corrected ring run: 2,056 physics ticks with actual inter-fly contact; slot 1 exits at tick 13,751 and the run ends at 13,800. Corrected orchard run records 21 contact ticks with the same food totals. Machine-readable evidence is in [evidence/local-matches.json](evidence/local-matches.json).

## Bugs found and fixed

- FlyGym 2.1 root-level ground sensor names collided between flies. Its sensor lookup was also overwritten on each add. Arena now namespaces sensors and preserves all contestants' mappings; a two-body regression test checks disjoint sensor indices and shared-world stepping.
- Setting geom masks after model compilation left MuJoCo body broadphase masks zero, disabling fly/fly and fly/obstacle contacts. All masks now enter the MJCF before compilation. A forced-contact regression and actual full-graph matches verify the correction.
- Fused MuJoCo head bodies invalidated direct body lookup. A fixed head site now supplies physical sensor transforms.
- Admission now freezes both graph and readout weight hashes; compiled artifacts from a different neural/budget profile are rejected.
- Replay camera now remounts when leaving anatomical preview, avoiding an inherited close-up camera. Verified winners are displayed in the replay.
- Replay evidence manifests now enumerate the intended immutable files, excluding live worker logs.
- The independent judge now rejects early termination unless justified by the ring exit rule, and checks physical/neural final clocks.

## Still limited or pending

- Recorded engineering causality probe: exact repeat under the same stimulus; the Nectar mutation changes 16,275 neural firing-rate entries; output ablation gives 0.11956 mm of settling displacement and zero food, compared with approximately 21 mm of baseline travel in the earlier 2-second solo probe. See [evidence/causality.json](evidence/causality.json). This is a single-seed engineering check, not a powered biological or strategic comparison.
- Consistent purposeful navigation, naturally plausible behavior and statistically supported genotype advantage are not established. Starter flies frequently pass food and exit after a short walk.
- Visual inputs, online plasticity, aggression circuits, flying dynamics and GPU simulation are not available.
- Independent scoring verifies trusted-worker evidence, food conservation, ordering, clocks, hashes and admitted inputs. It is not a cryptographic proof that arbitrary untrusted worker geometry or event logs are authentic. Production requires stronger admission/isolation and broader adversarial tests.
- Tournament series use repeated seeds and swapped slots. That design does not by itself establish absence of all slot bias. Rankings are exploratory within this workspace.
- Full cross-backend numerical comparison, convergence, fault-injection matrix, backup restore and sustained public load tests remain later engineering gates.
- Remote runtime installation and source synchronization have succeeded; remote preparation is complete and its graph/readout weight hashes match local outputs. The app is supervised by launchd on loopback; five remote API matches verified, including the agent script’s completed two-match swapped-slot series. Measured Mac Studio wall times: 21.92 seconds for a 2-second solo; 44.24–54.97 seconds for 2-second dual food tasks; 48.13 seconds for the ring trial. See [remote matches](evidence/remote-matches.json) and [timings](evidence/remote-runtime.json). Public tunnel activation was rejected by automatic approval review and awaits explicit user approval of public access scope. No remote throughput number is claimed yet.
