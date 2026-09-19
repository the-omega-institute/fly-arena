# Training sandbox

Open **Train / 训练沙箱**, choose a starting fly and a small budget, then start a session. The server evaluates actual embodied matches. Closing the page does not cancel work; return to the session tab to inspect progress. Pause and Stop let the current evaluation finish before preventing further admissions. Resume continues the same session.

Each generation shows individuals, parents, circuit multipliers, mutation budget, scores and links to behavior/neural replays. Save publishes an evaluated individual to the fly library; Compete saves it and selects it in the Arena. Hidden candidates stay out of the library until saved. Training matches never enter public standings, even after an individual is saved. Hidden library entries are not private storage: the MVP's fly-by-ID and match/replay endpoints remain public.

## Strategies and scores

- **Evolution**: retain the previous generation's best individual and generate legal circuit mutations around it. Ties retain the earlier individual. Generation one starts from the chosen founder.
- **Random search**: every generation retains the original founder and explores new mutations around it. This is a useful comparison against selection across generations.
- Circuit changes are sampled in log space using the session seed; the compiler enforces the normal mutation budget. Existing edge interventions and intrinsic parameters are preserved. Proposals that exceed the budget are reduced; if no actual legal mutation is found, the session reports failure.
- **Collect food**: fitness is mean food consumed across the configured evaluation conditions.
- **Compete for food**: each condition uses two matches against a fixed opponent with swapped spawn slots. Its score is their mean food advantage; fitness is the equal-weight mean of all complete condition scores.

The map/seed conditions stay fixed across individuals and generations. By default there is one condition. Scores describe these training environments, not held-out generalization. A zero score or no improvement is a valid result. These searches optimize parameters between matches; they do not add within-match plasticity, learning or a new sensory modality.

## Compare sessions

Expand **Compare training strategies / 比较训练策略** in Train and select up to
three of your sessions. The shared chart shows each generation's best food score;
hollow points and dashed segments indicate partially evaluated generations, and
missing results stay blank. The table reports the starting score, best observed
score (including the baseline), absolute change, completed/planned evaluations,
admitted evaluations and the configured limit. It never converts a zero baseline
into a percentage improvement or replaces negative contest scores with zero.

Condition cards show the founder, map, objective, opponent, seed, duration,
population and mutation settings. Differences in evaluation conditions or the
recorded runtime are called out; missing runtime metadata cannot count as a
confirmed match. Even matching conditions describe individual training runs,
not statistical evidence that one optimizer generalizes better. Search budgets
and mutation settings remain visible when they differ.

Click a session name to open its individuals and replays. **Export comparison**
downloads the selected summaries, conditions and generation history as JSON.
Comparison uses the existing owner-only training endpoints and starts no jobs.
`evaluation_context` is the session's existing immutable runtime identifier;
older responses lacking it remain readable. Evaluated time budget means
`completed evaluations × seconds per evaluation`, not queue time, wall time,
recovery attempts or GPU billing; evaluations may finish before their configured horizon.

Plans have 2–6 individuals, 1–8 generations, 1–10 seconds per evaluation, and at most 96 evaluations. Required evaluations are `population × generations × conditions × (1 for solo, 2 for competition)` and must fit the explicit budget. At most two unfinished sessions per account; stop unused sessions to release a slot. The existing queue executes simulations in child processes, one at a time per worker. The budget counts admitted evaluation matches; existing recovery attempts can repeat an interrupted match. It is not a GPU-hour or billing limit.

## Multiple maps and seeds

The main environment and seed in the web form define condition 1. **Add evaluation
condition / 添加评测条件** adds up to three more map/seed pairs. The same map with a
different seed is allowed; identical pairs are rejected. The evaluation budget
updates before submission. All candidates in every strategy use the same list.

For example, two individuals × one generation × two conditions × two spawn
positions requires **8 evaluations**. Each individual has condition cards showing
its map, seed, completed evaluation count, score, and **behavior and neural replay**
links. A condition remains unscored until its entire pair completes; a candidate
remains unscored until all conditions complete. Failed conditions preserve prior
results and stop the session without manufacturing a fitness value.

Add this optional field to a training request:

```json
"evaluation_conditions": [
  {"map_id": "orchard", "seed": 42},
  {"map_id": "scarcity", "seed": 7}
]
```

The explicit list replaces `map_id`/`seed` for evaluation. The top-level `seed`
still controls built-in mutation sampling. When the list is absent or null, old
sessions and clients retain exactly their single `map_id`/`seed` behavior. Old
idempotency keys remain usable with their original plans. No database migration
is required. Conditions use raw food units (or food-margin units), with equal
weight per condition; scores are not normalized by food availability.

The ordinary training client can create the same plan:

```sh
uv run python scripts/train.py --population 2 --generations 1 --budget 8 \
  --opponent OPPONENT_ID --seconds 1 \
  --condition orchard:42 --condition scarcity:7
```

For your own optimizer, create an external-strategy session with these conditions
in the web form or through `POST /training`, then run
`python scripts/custom_strategy.py --run SESSION_ID`. The existing proposal API
is unchanged. Responses add `members[].condition_results`, containing each
condition, its fitness (or null), completed/total evaluations, and the actual
match records. Existing aggregate fitness, lineage, save and replay fields remain.
These are environments used during training; evaluating them is not a held-out test.

## Shared human/AI API

Browser sessions and Arena bearer tokens use the same endpoints. `GET /training` returns only the authenticated owner's sessions; another owner receives 404 for a session's detail and controls. Prefix all paths below with `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/training` | Submit a bounded plan; optional `Idempotency-Key` prevents duplicate creation |
| GET | `/training` | List your sessions, newest first |
| GET | `/training/{id}` | State, generations, ancestry, scores and evaluation matches |
| POST | `/training/{id}/control` | `{"action":"pause"}`, `"resume"`, or `"stop"` |
| POST | `/training/{id}/save` | `{"fly_id":"…"}` publishes an evaluated individual |
| GET | `/matches/{id}/{artifact}` | `scene`, `frames` (including neural traces), `events`, or `receipt` |

Example plan:

```json
{
  "name": "Two generations",
  "founder_id": "REPLACE_WITH_32_CHARACTER_FLY_ID",
  "strategy": "evolution",
  "circuits": ["olfactory", "projection", "descending"],
  "mutation_strength": 0.08,
  "population": 2,
  "generations": 2,
  "max_evaluations": 4,
  "map_id": "orchard",
  "mode": "forage",
  "duration_seconds": 1,
  "seed": 42,
  "bridge_profile": "legacy-v1"
}
```

The runnable client creates a session, observes it, downloads actual evidence, and optionally saves its best individual:

```sh
# Set ARENA_TOKEN in your environment using the API token shown in the app.
export ARENA_URL=http://127.0.0.1:18080
uv run python scripts/train.py --population 2 --generations 2 --budget 4 --save-best
uv run python scripts/train.py --run RUN_ID --control pause
uv run python scripts/train.py --run RUN_ID --control resume
```

The client prints its creation key before submission; reuse `--key KEY` after a transport failure with the identical plan. `--run ID` observes an existing run without creating another. `--opponent ID --budget 8` evaluates the same small plan with mirrored competition. Credentials are read from the environment and excluded from exported results.

User-hosted optimization can use `/flies/validate`, `/flies`, `/matches` and `/tournaments`; [ai_designer.py](../scripts/ai_designer.py) shows this existing lower-level path. These ordinary matches enter normal standings. Publishing a fly alone does not schedule Lab work; `POST /flies?compare=true` explicitly requests the existing comparison. Use the external proposal interface below for custom optimization within training sessions. Arbitrary strategy code is not executed on the service.

When the operator enables [node execution](COMPUTE.md#route-the-apps-match-queue-to-a-nyxid-compute-node), the same training plans use that node through the ordinary queue. The recorded runtime belongs to the machine executing the match. A short connection loss does not submit another evaluation, and replay data returns to this application's normal endpoints.

## Bring your own optimizer

Choose **Your own optimizer · API** in the training page, or create a session with `"strategy":"external"`. The server prepares and evaluates an exact founder copy at **generation 0, slot 0**. Your own program supplies the remaining candidates and chooses parents using actual results. No custom optimizer code is uploaded or executed by the service.

The session response adds `proposal_generation` and `open_slots`. Both use zero-based indices. Proposals are accepted only for missing slots in the current generation; the next generation opens after all previous-generation individuals have been evaluated. The baseline can run while the server waits for proposals. The state `awaiting_candidates` means the optimizer needs to submit more individuals, not a stalled simulation.

```http
POST /api/v1/training/SESSION_ID/candidates
Authorization: Bearer ARENA_TOKEN
Content-Type: application/json

{
  "generation": 0,
  "slot": 1,
  "spec": {
    "name": "My proposal",
    "parent_id": "FOUNDER_ID",
    "connectome_sha256": "PINNED_CONNECTOME_SHA256",
    "weight_mutations": [{"selector":"olfactory","scale":1.08}]
  }
}
```

A proposal is a complete ordinary FlySpec, including any supported edge/type interventions or intrinsic parameters. The normal compiler budget and model limits apply. `circuits` and `mutation_strength` configure only the built-in search; external sessions normalize `circuits` to an empty list and the optimizer determines its interventions. Within-match plasticity remains unsupported.

The parent must be the session founder or an evaluated member of an earlier generation in the same session. Parameters are absolute relative to the canonical graph; parentage records lineage rather than applying the parent's edits again. Multiple children can branch from the same parent, or your optimizer can restart from the founder. The server does not replace your parent selection with its own best individual.

`(session, generation, slot)` is the proposal's stable identity. An identical retry returns the existing fly; different content for an occupied slot is rejected. Terminal sessions reject new candidates, and a stop racing with compilation prevents admission. Proposals may be prepared while paused, but evaluation does not resume until the user resumes the session. Finite population/generation limits prevent extra slots from consuming additional evaluations.

Candidates remain hidden from the library, do not schedule Lab experiments, and their training matches do not enter standings. Save an evaluated candidate explicitly when you want to publish it. The web page shows external sessions, the baseline, proposal status, scores, parents and replay. **Branch training from this fly** saves the selected individual and opens a new training plan rooted in it. **Export results and lineage** downloads the session and complete FlySpecs as JSON for sharing or analysis. A bookmarked session URL requires its owner's login; it is not a public sharing permission.

Run the working coordinate-search example:

```sh
export ARENA_URL=http://127.0.0.1:18080
# Set ARENA_TOKEN from the app's AI / API panel.
uv run python scripts/custom_strategy.py --population 2 --generations 2 --budget 4 --save-best
# Or attach to the session created in the browser:
uv run python scripts/custom_strategy.py --run SESSION_ID
```

Replace `propose()` to implement your own optimizer using any library on your machine, or call the same HTTP endpoints from another language or AI agent. The example retains an incumbent and explores deterministic circuit coordinates; it makes no promise of improved fitness. It exports the observed training history and submitted proposals. Use `scripts/train.py --run SESSION_ID` to additionally download scene, frames, events and receipts for its evaluations. Pausing in the browser stops the example's optimization loop; after resuming the session, rerun it with the same `--run` ID. An observation timeout leaves server work intact and prints the ID needed to reattach.

### Scarce-resource training

Choose **Last Oasis / 最后的绿洲** (`scarcity`) in the sandbox or pass `--map scarcity` to either training client. Its smaller arena has one shared patch with only **2 food units total**, compared with 50 across five patches in Amber Orchard. Food never replenishes and the existing odor signal weakens with the remaining amount. Train alone for collection or use a fixed opponent with mirrored spawn evaluations for competition. Scores remain actual food consumed; a scarce-map score is not directly comparable to an orchard score.


The `terrarium` map (Rotting Fruit Grove / 腐果林地) is available to both forage and contest evaluations, including multi-condition sessions and external optimizers. Select it in the web map selector or pass `--condition terrarium:42` / `--map terrarium`. Its low ramps and raised passage are physical collision geometry; food remains on the ground and odor is the existing analytic field. Changing terrain alone does not add vision or online learning.

## Choose an algorithm or bring a model

The Evolution page now provides four choices:

| Choice | Candidate generation | What learns |
| --- | --- | --- |
| Evolution | Retain the highest-scoring previous individual; Gaussian mutations of its log circuit multipliers | Selection updates the parent |
| Random search | Independent Gaussian perturbations around the founder; slot 0 repeats the founder | No learned search distribution; a useful control |
| Cross-entropy (CEM) | Fit a diagonal Gaussian to the top half of the previous generation and sample it; keep the best parent | Log-weight mean and standard deviation, smoothing α=0.7, σ floor=0.01 |
| Custom algorithm / model | Your local program submits each open candidate slot | Whatever your optimizer implements, using completed scores and valid FlySpecs |

All three built-ins share selected circuits, mutation strength, bounds `[0.5,2]`, compiler mutation budget, deterministic generation/slot seeds and evaluation accounting. CEM's initial generation uses the same proposals as the other built-ins. Later CEM distributions are reconstructed from completed generations after restart. Illegal mutations are shrunk toward the retained parent; the effective search distribution near a budget boundary is therefore constrained. These are black-box weight optimizers, not different biological neural dynamics. The evaluated fly still uses `malecns-lif-cpu-v1`; within-match plasticity is `none`.

Choose **Custom algorithm / model** in the browser, label the model, and start a finite session. Set `ARENA_URL` and your own `ARENA_TOKEN` locally, then attach a plugin:

```sh
python scripts/custom_strategy.py --run SESSION_ID --plugin my_optimizer.py --config config.json
```

A plugin exports:

```python
def propose(founder, history, generation, slot, config):
    # history contains completed scores, FlySpecs, lineage and replay match IDs.
    # Choose founder or an evaluated earlier-generation member as parent.
    spec = dict(founder['spec'])
    spec.update(name=f'My model G{generation+1}.{slot+1}', parent_id=founder['id'])
    spec['weight_mutations'] = [{'selector': 'olfactory', 'scale': 1.08}]
    return spec
```

The CLI loads this file on **your machine**. It never uploads/executes Python, model weights or config on the Arena service. The return value is a validated, absolute FlySpec relative to the canonical graph. Cached proposal files are written before network submission, so resuming a stochastic optimizer resends the exact proposal. Use one optimizer process per session. A browser JSON form also accepts `{generation, slot, spec}` for manual/API experimentation.

Without `--plugin`, the driver uses the included deterministic coordinate-search example. For a real learned optimizer example, install PyTorch locally and use:

```sh
python scripts/custom_strategy.py --run SESSION_ID --plugin examples/optimizers/torch_surrogate.py
```

This example fits a small MLP to observed log circuit multipliers and fitness, ranks a sampled candidate pool, and retains the best evaluated parent. It warms up with random proposals until four observations have distinct scores. It is a surrogate-assisted optimizer, not PPO, a differentiable simulator or a replacement fly-brain model. Its `config.json` can specify `seed`, `sigma`, `steps` and `pool`. A proposal exceeding the mutation budget is rejected; adapt your optimizer to handle constrained designs.

## Public evolution gallery

Visitors can open Evolution without logging in and compare explicitly published, completed sessions. Charts retain flat and worsening scores. Each generation exposes candidate weights, parents, budget, actual scores and neural/behavior replays. **Save a copy and prepare training** asks you to sign in, saves an owned copy of the full published design, then selects it in a new training plan. The copy preserves its public parent and the source environment, seed, duration and sensory profile. Only **Start training** submits computation. Deployments that do not advertise `gallery_copy_available` show the gallery as read-only.

`POST /api/v1/training/{id}/publish` shares the completed session's designs, scores and replay references; only the owner may publish. `GET /api/v1/training-showcase` and `GET /api/v1/training-showcase/{id}` require no login. Unpublished training remains owner-only. Publication removes account identifiers and operational fields from the response. Local model configuration is never uploaded. Users choose publication explicitly after completion.

For useful comparisons, keep the founder, runtime, objective, maps/seeds, duration, population and evaluation limit the same. Short examples illustrate the workflow; they do not establish algorithm superiority, long-term learning or held-out performance.

## Brain model and neural gradient training

Choose LIF or experimental continuous-rate dynamics in Studio before saving the founder. All built-in optimizers work with either model. Each session retains that model; different models are explicitly flagged in comparisons. The custom [rate Adam trainer](RATE_MODEL.md) fits neural responses using backpropagation through the full connectome, then submits candidates for actual embodied scoring. It does not backpropagate through MuJoCo or learn within a match.

The `enclosure` map (Enclosed Orchard / 封闭果园) adds a physical perimeter,
leaves and fruit husks around five shared food patches. It is selectable in
matches, tournaments, training conditions and both agent CLI examples. Contact
with the wall is resolved by MuJoCo; it does not reset the fly or supply an
automatic turn. Compare sustained movement and feeding as well as scores:
remaining inside the habitat can also mean that a design got stuck.


## Sensory conditions in evolution

Choose **Sensory input profile / 感觉输入模式** when creating a session. Every generation, map/seed condition and mirrored contest position uses the recorded profile. Opening a saved candidate for competition carries the session's bridge, senses and first evaluation condition into the arena. Branching a candidate or public example also restores its sensory/environment settings.

`TrainingSpec.sensory_profile` accepts the same IDs as matches. Its historical default is `odor-only-v1`. Experimental vision/touch profiles currently require `legacy-v1`; incompatible combinations are rejected before evaluation. The API binds the selected profile to the actual compute node runtime. Different sensory profiles are shown as different conditions when comparing algorithms.

Both agent clients accept the same option:

```bash
python scripts/train.py --founder FLY_ID --map enclosure --seconds 3 --sensory-profile engineered-touch-response-v1
python scripts/custom_strategy.py --founder FLY_ID --map enclosure --seconds 3 --sensory-profile engineered-touch-response-v1 --plugin my_optimizer.py
```

For a direct API request, add `"sensory_profile":"engineered-touch-response-v1"` to `POST /api/v1/training`. Reattaching with `--run` uses the recorded plan and does not change conditions. This makes sensory conditions available to optimization; it does not establish that a profile or algorithm improves behavior. The 8 mV profile is an engineering experiment, not biological calibration.

`GET /api/v1/season` advertises `training_sensory_profiles`. Older servers without that field show only odor training in the new UI, and the UI omits the new request field for compatibility. No selected experimental input is silently replaced with an odor-only request.

### Continue from a portable public specimen

`POST /api/v1/training-showcase/{run_id}/flies/{fly_id}/copy` requires an Arena identity. It accepts the published run and specimen IDs, compiles the complete FlySpec, and returns a new owned fly whose `spec.parent_id` is the public specimen. Repeating the same request for the same identity returns the same copy; another identity gets its own copy. No training, match or Lab experiment is scheduled by copying. Use the returned `id` as `founder_id` in a separate training request.

The public specimen remains read-only. Its life record exposes the published training origin, available ancestors and recorded experiences even when the deployment has only portable gallery files and no source database. A specimen page links to the source trajectory for saving a copy before training or competition. The saved copy does not inherit unrecorded within-match state.
