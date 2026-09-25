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
- Runtime installation and source synchronization have succeeded on the configured deployment host; preparation is complete and its graph/readout weight hashes match local outputs. The app is supervised on loopback; five API matches were verified, including the agent script’s completed two-match swapped-slot series. Measured deployment-host wall times: 21.92 seconds for a 2-second solo; 44.24–54.97 seconds for 2-second dual food tasks; 48.13 seconds for the ring trial. See [remote matches](evidence/remote-matches.json) and [timings](evidence/remote-runtime.json). The public frontend preview is available at <https://fly.omega.gift>; its API and simulation deployment remain separately configured. No remote throughput number is claimed yet.

## Final deployment check

The final source version passed the same 12 tests on the configured deployment host (3.87 seconds). After restarting the private service with graph/readout admission checks, match `9b4321f00d1f45a1a3275e15f2772f7c` completed and verified in 43.65 seconds. Its receipt freezes the actual data/readout and source hashes: [release-check.json](evidence/release-check.json). The public frontend preview is available at <https://fly.omega.gift>; this does not claim that the API or simulation service is publicly reachable.

## Optional NyxID authentication boundary

The subsequent authentication change passed all 30 local tests (5.98 seconds), including 18 offline OIDC/session cases and the existing 12 simulation/platform tests. The provider fixture uses real RSA signatures and mocked HTTP discovery, token exchange and JWKS; it verifies PKCE, nonce, issuer/audience, signature, expiry, browser binding, single-use callbacks, persistent sessions, CSRF, agent-token expiry/revocation and ownership isolation. The web TypeScript and production build passed; the existing bundle-size warning remains.

NyxID remains disabled by default. No real OAuth client was registered and no production NyxID login was attempted. Its configuration, callback contract and later integration checks are documented in [NYXID_LOGIN.md](NYXID_LOGIN.md). Live NyxID configuration is explicitly deferred to the user.

The restarted local server returns HTTP 200 for the built workbench, disabled NyxID config and anonymous session contract. A fresh visual auth check through Computer Use was unavailable (`cgWindowNotFound`); the earlier Safari simulation workflow evidence applies to the baseline, not a live NyxID flow.

## Deployment-host authentication-interface release

Application source commit `1fb68581fef9614fe290ce20a037279ad955781f` was synchronized after confirming an empty queue and stopping the app. Locked dependencies installed successfully, all 30 tests passed on the configured deployment host in 5.77 seconds, and the app-only service restarted in local authentication mode. Served HTML, JS and CSS SHA256 values match the local production build.

An actual API identity submitted solo orchard match `bb34ecf57c634140a9d1707bab42570c`, seed 42, duration 2 seconds. It independently verified with food score 0.4032, 41 replay frames, 3,469,178 neural spikes and wall time 23.91 seconds. All seven recorded simulation source hashes and the dependency lock match local files. The graph and frozen readout weights match the baseline release. Full receipt, web hashes and test result: [auth-release-check.json](evidence/auth-release-check.json). This is the latest private runtime release; NyxID is not activated and no public tunnel is running.
