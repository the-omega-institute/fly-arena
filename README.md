# Fly Arena · Genesis Alpha

用真实果蝇神经图谱，让人和 AI 修改神经网络参数设计数字果蝇，然后在多种竞技环境下 PK。

Implemented research preview: React/Three.js design workbench, immutable FlySpec compiler, full retained MaleCNS neural simulation, server-owned reference provenance, matched WT/official/design experiments in the Phenotype Lab, shared-world FlyGym/MuJoCo competitions, anatomical replay, and an agent API. **This is an experimental connectome-constrained game, not a validated reproduction of natural fly intelligence.** Research experiments and legacy competitions have separate admission and evidence paths.

The current graph retains **165,122 Traced neurons, 25,563,197 directed neuron-pair connections, and 124,025,046 synaptic contacts** from MaleCNS v1.0. Anatomical connectivity is real; weights/signs and neural dynamics follow a declared simplified model. The default input is bilateral odor current; opt-in experimental profiles add geometric visual observations and food/environment contact currents. The engineered descending-neuron readout and locomotion transfer are fixed across subjects within a selected profile. The body has two bilateral locomotion action channels. A biological retina, online plasticity, natural aggression, and a qualified GPU neural backend are not implemented.

## Current shipped scope (rounds 1–2)

The current product increment ships the first two rounds of the research preview: the Phenotype Lab has recorded 3D scene inspection; the map registry labels observation-only mazes and keeps them out of competitive/training eligibility; Arena setup is shared across preview and match flows; and the science guide explains what is modeled, recorded and still unavailable. Round 2 adds the recorded life lineage tree, receipt-backed replay inspection, the `arena-geometry-v1` geometry contract, and the issue-82 phase-1 maze diagnosis with the preregistered phase-2 study runner. The complete five-seed 180-second phase-2 study is now recorded with a negative verdict: seeds 42, 45 and 46 were negative, seeds 43 and 44 improved, and the candidate is not promoted. See [the retained analysis](docs/MAZE_LOCOMOTION.md#completed-phase-2-study-2026-09-24).

These surfaces expose recorded evidence and modeled mechanisms separately. A replay or comparison can describe the supplied conditions and observations; it cannot by itself establish biological validity, causal effects or generalization.

![Design workbench](docs/screenshots/design.png)

## Run locally

Requires Python 3.12, Node 22+ and at least 8 GB free memory for preparation and two-fly experiments; allow several GB of disk. Mac Studio is the primary deployment target. Linux CPU also supports the simulation; browser rendering uses the viewer's GPU.

```sh
uv sync --python 3.12
npm ci --prefix web
npm run build --prefix web
uv run arena prepare
uv run arena seed
uv run arena serve --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080. `arena prepare` downloads the official public MaleCNS files, imports the graph and prepares the **legacy-v1** readout at `data/connectome/readout.{json,npz}`; it is not an instant startup step and **does not create the research-v2 readout**. `data/` and `var/` are ignored by Git. The optional `ARENA_DATA` and `ARENA_VAR` environment variables relocate them. See [operations](docs/OPERATIONS.md).

For the research preview, after graph preparation and before starting the server, explicitly prepare the separate readout:

```sh
# Uses ARENA_DATA when set, otherwise the repository's data/ directory.
uv run python scripts/calibrate_v2.py
# Alternative: select a data root that already contains the imported graph.
# uv run python scripts/calibrate_v2.py --data /absolute/path/to/data
```

The script's data-selection flag is `--data`; it writes `connectome/research-v2/readout.npz` and `readout.json` beneath that root. Use the same root for the server through `ARENA_DATA`. Preparation refuses an existing `research-v2` directory: preserve frozen readouts and use a fresh data root with the imported graph for a separately versioned recalibration. Keep both readout files together. `GET /api/v1/research/catalog` reports readiness and its reason without calibrating. Readout readiness enables research trials; competition also requires a valid qualification bound to the current scientific sources.

`arena serve` dispatches queued experiments to separate simulation processes. `--no-worker` leaves new experiments durably queued, so it is suitable for inspecting existing reports but will not produce a new comparison.

## Use the MVP

First visit: the design page includes a short guide from copying WT through editing, saving, training and comparison. Expand **How this fly works** for the connectome source and the neural/body simulation explanation. In Arena, **Prepare WT challenge** selects a compatible unmodified reference and a small preset; the two-match series swaps positions, at two simulated seconds per match.

For your AI, open **AI / API** and copy the task prompt. It includes this deployment's API and a standalone [agent quickstart](docs/AI_QUICKSTART.md), also served without authentication at `/api/v1/agent-guide`. The AI can propose parameters, run an external optimizer or analyze recorded behavior and neural activity. An authorized finite task can proceed without repeated permission prompts.

1. In **设计工坊 / Design**, start from the canonical draft or clone a saved fly, edit circuit weights and intrinsic parameters, validate the budget, and save an immutable design. Saving stays in Design and opens a comparison with WT and compatible public designs from other owners. Choose an observation window (default 10 seconds, up to 180 per match), review the two swapped matches per reference, then explicitly start. Progress and complete paired results stay here; the next action opens Arena for replay and further experiments. Saving alone does not consume simulation time. See [the first comparison flow](docs/FIRST_COMPARISON.md).
2. For optional controlled research comparisons, open **Phenotype Lab**, select your saved design, a probe, **1–8 distinct nonnegative int32 seeds**, and an integer horizon of **1–30 seconds**. The catalog currently offers an off-axis gradient (`gradient-v2`), a fork with a barrier (`bifurcation-v2`), and a delayed/disappearing cue (`delayed-cue-v2`). Each seed compares independent solo trials with the same scene, body, backend, readout, motor profile and horizon. Verified reference trials may be reused only for the identical condition and artifact; design trials execute anew. Lab experiments never enter match standings.
3. Inspect all three frozen subject IDs and artifact hashes, then use the seed selector, shared playback/scrubber, trajectory overlay, metrics and paired deltas against WT, trajectory divergence, and neural/drive trace selector. The scene shows recorded arena bounds, obstacles, spawns and initial food sources at equal x/y physical scale. Older reports without scene data display unavailable geometry. Receipts and frozen profile details are inspectable. Failed, partial or mismatched trials do not produce a successful comparison; missing/censored latency stays missing, no branch choice is explicit, and a zero delta is a null effect. Motion or activity alone does not establish an improvement.
4. In **竞技场 / Arena**, explicitly select the available **Legacy v1** profile, an orchard, obstacle garden, scarce-resource oasis or sumo ring. Existing modes are solo foraging, two-fly food competition and contact-based ring competition; a paired series exchanges spawn slots with identical seeds. Verified matches expose anatomical replay, food scores and circuit activity. Failed runs remain visible and do not score. Research-v2 competition is unavailable as described below.
5. In **AI / API**, export/import FlySpec and obtain your designer token. API documentation is served at `/docs`; research contracts are in [RESEARCH_API](docs/RESEARCH_API.md). The script below publishes a real mutation and evaluates a legacy two-match paired series:

```sh
# Set ARENA_URL and ARENA_TOKEN in your environment; do not commit tokens.
uv run python scripts/ai_designer.py
```

**Provenance is server-owned.** WT is the canonical baseline and the official release is a frozen server reference. A name, clone, matching weight hash or claimed owner cannot confer either role. `reference_kind` distinguishes `wildtype`, `official`, `user` and registered-agent `ai`; `release_id` and `submission_channel` (`seed`, `web`, `api`) are separate metadata. An API submission alone does not prove AI authorship. The Lab labels a subject “Your design” only for the experiment's authenticated owner; other viewers see “Submitted design.”

Advanced interventions support exact pre/post **class, type, side (`L`/`R`) and canonical neuron ID** selectors against pinned graph metadata. The editor offers real annotation suggestions, counts and the metadata digest; unsupported ROI, regex, unknown annotations and empty matches are rejected. Overlapping changes combine before final multiplier and budget checks. Preview reports distinguish structural and effective changes. A child's complete spec is absolute relative to the canonical graph; its parent records lineage, not another weight multiplier. Exploratory vision/memory/motor edits do not add sensory modalities, learning or action channels. See [UI_RESEARCH](docs/UI_RESEARCH.md) and [RESEARCH_API](docs/RESEARCH_API.md).

The MVP workspace publishes designs, research reports and verified replays. Authentication ships with local designer bearer mode and a live NyxID OIDC mode, including the same-origin Pages entry added in PR #84; the selected deployment reports its active mode from `/auth/config`. Static Pages mode uses the local bearer flow when no same-origin application origin is configured. Optional local registration gating uses `ARENA_INVITE_CODE`. Per designer there are limits of 100 designs, 12 pending matches and 12 unfinished research experiments. These are beta controls, not a complete production anti-abuse system.

## License and attribution

Project-authored code is released under the MIT license in [LICENSE](LICENSE).
MaleCNS data, FlyGym/NeuroMechFly assets, MuJoCo, fonts, generated examples,
and Python/npm dependencies are separate materials with their own terms; see
[NOTICE](NOTICE.md) and [ATTRIBUTION](docs/ATTRIBUTION.md). The code license
does not grant rights to redistribute third-party datasets or assets.

## Privacy and data retention

The read APIs are public by design for published designs (`GET /api/v1/flies`),
matches and replay artifacts (`GET /api/v1/matches` and its replay routes), and
research experiments (`GET /api/v1/experiments` and
`GET /api/v1/experiments/{id}`). Public life, catalog, leaderboard and
connectome metadata reads support the same preview. Bearer tokens, NyxID
sessions, owner-only saved views, and write operations are not public reads.
The service stores published records, replay evidence, and research reports in
its configured SQLite/object roots; there is no automatic deletion or
user-facing retention schedule in this preview, so operators must define and
apply retention before treating it as a production data service. Do not submit
personal data or secrets as design names, descriptions, or experiment fields.

## Inspect your fly’s brain during replay

Replays with bound anatomical graph snapshots open directly in spatial view.
You can also choose **Anatomical space · 3D / 解剖空间 · 3D** in the neural theatre.
Drag to rotate, scroll to zoom, or use the XY/XZ views. The gray cloud uses actual
MaleCNS soma coordinates. The default foreground shows all recorded circuit neighborhoods; choose a
circuit to focus it. Unrecorded neighbors appear around the selected neuron. Select a node to inspect connection direction,
your actual model weights and its activity history; **Go to recorded peak** seeks
the body and brain together. Changing circuits keeps the spatial view open.

Missing coordinates are omitted from the spatial view, but the neuron remains
available in the selector and activity records. Gray background points and hollow
neighbors do not imply zero activity. Straight links join connected cell bodies;
they are not traced axon shapes. Coordinates retain source units with a uniform
display scale, not a claimed conversion to micrometers.

The API serves `/api/v1/connectome/anatomy` from prepared metadata without running
a simulation. For static replay deployments, publish the same data alongside the
frontend, using the connectome identity already recorded in the replay:

```sh
uv run python scripts/bundle_anatomy.py --data data --output web/dist/examples/anatomy
```

The viewer rejects a different connectome and keeps the existing connection and
activity inspection usable when spatial data or WebGL is unavailable.

## Training sandbox

Open **Train / 训练沙箱** to evolve a chosen fly or compare random search. Configure circuits, scene, objective, population, generations and an evaluation budget. Sessions persist across reloads, support pause/resume/stop, and show actual scores, parents and neural/behavior replays. Save an evaluated descendant and send it to the Arena. Training evaluations do not affect the public leaderboard.

Start small: 2 individuals × 2 generations × 1 second, with a budget of 4 solo evaluations. Mirrored competition requires twice as many evaluations. These searches make no promise of improvement.

[Training contracts and limits](docs/TRAINING.md) describe the shared browser/AI API. Run `uv run python scripts/train.py --save-best` with `ARENA_URL` and `ARENA_TOKEN` set to try the same bounded flow from your own agent or terminal. For your own optimization algorithm, choose **Your own optimizer · API** and run `scripts/custom_strategy.py --run SESSION_ID`; replace its `propose()` function to submit custom candidates within the same evaluation budget. The web page can branch training from an evaluated descendant and export results and lineage as JSON.

## Scientific status and competition limits

**Existing `legacy-v1` competitions remain available; `sensorimotor-research-v2` competition is unqualified and unavailable.** Match and tournament requests carry a bridge profile; omitted historical fields retain legacy-v1 semantics. An unavailable v2 request returns HTTP 422 without falling back to v1. The Arena displays server readiness and reasons, and rankings keep bridge/runtime/scenario/mode scopes separate.

The **historical bounded v4 cohort failed 3 of 15 unchanged gates**: heldout-left long approach and both bifurcation choice-and-food gates. Its recorded motor candidate is an engineering preview, with reliable approach, feeding and retention still unproven. Internal v2 solo/dual arena diagnostics are not admitted competitions or leaderboard evidence. That historical cohort does not establish qualification for subsequently changed sources; current admission requires independently verified evidence bound to the current profile. See [SCIENCE_MOTOR_V4](docs/SCIENCE_MOTOR_V4.md) for the bounded result and [QUALIFICATION_V4](docs/QUALIFICATION_V4.md) for the admission contract.

The chemical fixture is analytic and penetrates walls; it is not odor diffusion or line-of-sight transport. In odor-only mode, body contact reflexes do not add neural contact input. Experimental sensory profiles explicitly add engineered visual/contact currents; they are not calibrated sensory receptor models. Game energy is an accounting proxy, not metabolism. Persistence after a cue does not prove memory. Biological navigation, learning, memory and CUDA execution remain unqualified; calibrated neural output and visible movement alone do not establish those capabilities.

## Architecture and engineering decisions

The trusted path is **FlySpec → validation/compilation → immutable artifact → worker execution → evidence → independent verdict → replay**. Player code never runs inside a match. The application exposes `ArtifactRepository`, `ResearchRepository`, `IdentityProvider` and `ExperimentExecutor` ports. Local immutable storage, transactional admission with idempotency and fenced leases, and whole-trial subprocess execution implement the local research path. Provider, authentication and HTTP concerns stay outside physics, neural dynamics, compilation and judging.

External integration ports are explicit, with availability reported by the catalog: **chrono-bucket** has a disabled transport adapter for immutable, digest-verified objects; **Ornn** supports pinned local package references; **CMA** supports an explicit user-launch descriptor with no configured public trigger; **NyxID** retains its opt-in OIDC adapter. Heca/Aevatar outer orchestration, Talos simulation execution and Athena as a neural backend are unavailable. Talos lease fencing and Athena qualification/preflight are reusable engineering patterns. These interfaces do not activate external services or place network calls inside the neural timestep. Pinned source research and exact boundaries are in [CHRONO_REUSE](docs/CHRONO_REUSE.md).

Python orchestrates the system; Numba compiles the sparse neural loop to native CPU code; MuJoCo already provides a native physics engine. Start with these measured components, then move verified hotspots to C++20/CUDA if profiling justifies it. Rewriting the full platform in C++ at the outset would not solve the uncertain sensory/motor bridge.

- [Architecture and mechanisms](docs/ARCHITECTURE.md)
- [Research, original sources and prior hardware observations](docs/RESEARCH.md)
- [Acceptance gates and future work](docs/ROADMAP.md)
- [NyxID login interface and deployment](docs/NYXID_LOGIN.md) — OIDC + server-side sessions, enabled when the deployment supplies its registered client configuration.
- [Operations and deployment](docs/OPERATIONS.md)
- [Validation evidence and limitations](docs/VALIDATION.md)
- [MVP delivery audit](docs/MVP_ACCEPTANCE.md)
- [Data and software attribution](docs/ATTRIBUTION.md)
- [License](LICENSE) and [third-party notices](NOTICE.md)

```sh
uv run pytest -q
npm run build --prefix web
uv run arena verify var/runs/MATCH_ID/ATTEMPT
```

[PR #1](https://github.com/the-omega-institute/fly-arena/pull/1) remains historical reference. This implementation uses platform-executed connectome mutations rather than arbitrary remote controllers.
