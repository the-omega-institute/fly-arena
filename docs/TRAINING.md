# Training sandbox

Open **Train / 训练沙箱**, choose a starting fly and a small budget, then start a session. The server evaluates actual embodied matches. Closing the page does not cancel work; return to the session tab to inspect progress. Pause and Stop let the current evaluation finish before preventing further admissions. Resume continues the same session.

Each generation shows individuals, parents, circuit multipliers, mutation budget, scores and links to behavior/neural replays. Save publishes an evaluated individual to the fly library; Compete saves it and selects it in the Arena. Hidden candidates stay out of the library until saved. Training matches never enter public standings, even after an individual is saved. Hidden library entries are not private storage: the MVP's fly-by-ID and match/replay endpoints remain public.

## Strategies and scores

- **Evolution**: retain the previous generation's best individual and generate legal circuit mutations around it. Ties retain the earlier individual. Generation one starts from the chosen founder.
- **Random search**: every generation retains the original founder and explores new mutations around it. This is a useful comparison against selection across generations.
- Circuit changes are sampled in log space using the session seed; the compiler enforces the normal mutation budget. Existing edge interventions and intrinsic parameters are preserved. Proposals that exceed the budget are reduced; if no actual legal mutation is found, the session reports failure.
- **Collect food**: fitness is food consumed in one solo match.
- **Compete for food**: fitness is mean food advantage against a fixed opponent over two matches with swapped spawn slots. Both evaluations use the same map and seed.

The scene seed stays fixed across individuals and generations. Scores describe this environment, not generalization to unseen maps. A zero score or no improvement is a valid result. These searches optimize parameters between matches; they do not add within-match plasticity, learning or a new sensory modality.

Plans have 2–6 individuals, 1–8 generations, 1–10 seconds per evaluation, and at most 96 evaluations. Required evaluations are `population × generations × (1 for solo, 2 for competition)` and must fit the explicit budget. At most two unfinished sessions per account; stop unused sessions to release a slot. The existing queue executes simulations in child processes, one at a time per worker. The budget counts admitted evaluation matches; existing recovery attempts can repeat an interrupted match. It is not a GPU-hour or billing limit.

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

User-hosted optimization can use `/flies/validate`, `/flies`, `/matches` and `/tournaments`; [ai_designer.py](../scripts/ai_designer.py) shows this existing lower-level path. These ordinary matches enter normal standings and publishing a fly requests the existing Lab comparison. The first sandbox release hosts only the two named strategies; arbitrary strategy code is not executed on the service. An external proposal interface that keeps custom evaluations inside training sessions is a follow-up.

When the operator enables [node execution](COMPUTE.md#route-the-apps-match-queue-to-a-nyxid-compute-node), the same training plans use that node through the ordinary queue. The recorded runtime belongs to the machine executing the match. A short connection loss does not submit another evaluation, and replay data returns to this application's normal endpoints.
