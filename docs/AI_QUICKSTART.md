# Fly Arena AI quickstart

This guide describes a small, reviewable AI contribution through the public API. Arena validates every `FlySpec` and runs the selected supported LIF or continuous-rate runtime. It does not host arbitrary user code, run an uploaded neural model, or perform online learning.

The app serves this guide at `GET /api/v1/agent-guide` and the schema at `GET /openapi.json`. Use the current origin supplied by the web app; do not hard-code a private deployment URL.

## Discover before computing

These reads do not create work and do not require a token:

```sh
export ARENA_URL="http://127.0.0.1:18080"
curl "$ARENA_URL/api/v1/season"
curl "$ARENA_URL/api/v1/flies"
```

The season response contains the pinned connectome hash, budget and available bridge profiles. Find the canonical starting design in the flies response by selecting `reference_kind: "wildtype"` (the current UI names it `Wild Type / 原型`). Use that record's `id` as `founder_id`; do not assume the name is an ID.

## Validate and publish one design

Validation calculates the authoritative budget and does not publish or run a match:

```sh
curl -H "Authorization: Bearer $ARENA_TOKEN" \
  -H 'Content-Type: application/json' \
  -X POST "$ARENA_URL/api/v1/flies/validate" --data @flyspec.json
```

After review, publish with `POST /api/v1/flies`. This stores an immutable design and does not start a simulation unless the caller explicitly requests `?compare=true`:

```sh
curl -H "Authorization: Bearer $ARENA_TOKEN" \
  -H 'Content-Type: application/json' \
  -X POST "$ARENA_URL/api/v1/flies" --data @flyspec.json
```

Keep `ARENA_TOKEN` in the caller's environment. Never put it in a prompt, source file, URL, log or committed example. Tokens are private even though published designs and verified evidence are public.

## Small external optimization session

The optimizer runs on the user's machine; Arena receives and evaluates validated candidates. Start with population 2, two generations, four evaluations, one second per match, one map and one seed. Replace `FOUNDER_ID` with the wildtype ID discovered above:

```json
{
  "name": "Small external search",
  "strategy": "external",
  "founder_id": "FOUNDER_ID",
  "circuits": [],
  "population": 2,
  "generations": 2,
  "max_evaluations": 4,
  "duration_seconds": 1,
  "map_id": "orchard",
  "mode": "forage",
  "seed": 42,
  "bridge_profile": "legacy-v1"
}
```

Creation is authenticated and enqueues bounded work. When the user has already authorized this finite example, proceed with the request; ask for direction only if the task or budget is missing. Reuse an idempotency key only for an identical request; a retry after a lost response returns the original session:

```sh
KEY="a-new-random-key-for-this-request"
curl -H "Authorization: Bearer $ARENA_TOKEN" \
  -H 'Content-Type: application/json' -H "Idempotency-Key: $KEY" \
  -X POST "$ARENA_URL/api/v1/training" --data @training.json
```

Observe or control only sessions owned by the authenticated identity:

```sh
curl -H "Authorization: Bearer $ARENA_TOKEN" "$ARENA_URL/api/v1/training"
curl -H "Authorization: Bearer $ARENA_TOKEN" "$ARENA_URL/api/v1/training/SESSION_ID"
curl -H "Authorization: Bearer $ARENA_TOKEN" -H 'Content-Type: application/json' \
  -X POST "$ARENA_URL/api/v1/training/SESSION_ID/control" --data '{"action":"pause"}'
```

The existing CLI reads `ARENA_URL` and `ARENA_TOKEN` from the environment and defaults to a small session:

```sh
python scripts/train.py --founder FOUNDER_ID --population 2 --generations 2 --budget 4 --seconds 1
python scripts/custom_strategy.py --founder FOUNDER_ID --population 2 --generations 2 --budget 4 --seconds 1
python scripts/custom_strategy.py --run SESSION_ID
```

`custom_strategy.py` runs its `propose()` hook locally. Arena still validates each candidate and runs the fixed evaluator. `--save-best` is an explicit publication action and should be used only after review.

For a direct candidate submission, first read the owned session. Use its `proposal_generation`, `open_slots`, and the founder/parent identity from the session's `spec` and `members`; do not invent a generation or slot:

```sh
curl -H "Authorization: Bearer $ARENA_TOKEN" "$ARENA_URL/api/v1/training/SESSION_ID"
```

Submit a complete candidate envelope using those returned indices. The first generation reserves slot 0 for the baseline; the first external proposal normally uses generation 0, slot 1:

```json
{
  "generation": 0,
  "slot": 1,
  "spec": {
    "schema_version": "flyspec/v1",
    "name": "Small olfactory proposal",
    "description": "One bounded weight change from the discovered wildtype parent",
    "color": "mint",
    "parent_id": "FOUNDER_ID",
    "connectome_sha256": "SEASON_CONNECTOME_SHA256",
    "model_profile": "malecns-lif-cpu-v1",
    "weight_mutations": [{"selector": "olfactory", "scale": 1.05}],
    "edge_deltas": [],
    "neuron_parameters": {"tau_scale": 1, "threshold_shift_mv": 0},
    "plasticity": "none"
  }
}
```

Use the discovered WT spec as the starting point, retain its schema, graph and model identity, and apply your intended edits. Set `parent_id` to the founder for the first generation; later generations use an evaluated member of the previous generation. Replace both placeholder strings in the example with discovered values. Validate a constructed spec with `/flies/validate`; the example's one weight change is intentionally small and still subject to the authoritative budget. Submit it only to the owned session:

```sh
curl -H "Authorization: Bearer $ARENA_TOKEN" -H 'Content-Type: application/json' \
  -X POST "$ARENA_URL/api/v1/training/SESSION_ID/candidates" --data @candidate.json
```

To explicitly publish an evaluated best individual after reviewing the session, use its returned `best_fly_id`:

```sh
curl -H "Authorization: Bearer $ARENA_TOKEN" -H 'Content-Type: application/json' \
  -X POST "$ARENA_URL/api/v1/training/SESSION_ID/save" --data '{"fly_id":"BEST_FLY_ID"}'
```

## Analyze actual replay evidence

Listing and reading match state is observation-only:

```sh
curl "$ARENA_URL/api/v1/matches"
curl "$ARENA_URL/api/v1/matches/MATCH_ID"
```

After a match is `verified`, retrieve server-produced artifacts; a non-verified match returns `409`:

```sh
for artifact in scene frames events receipt; do
  curl "$ARENA_URL/api/v1/matches/MATCH_ID/$artifact" -o "MATCH_ID-$artifact.json"
done
```

Use `frames` for positions, scores, drives and recorded neural traces, `events` for event timing, and `receipt` for the pinned runtime and replay policy. Report observations and uncertainty; do not infer improvement from neural activity alone.

## API boundaries

`POST /api/v1/matches` submits a competition match. `POST /api/v1/experiments` is a separate authenticated research workflow, not a match endpoint. `POST /api/v1/training/{id}/candidates` accepts proposals for an owned external session; it does not execute arbitrary code. Compute creation is explicit and bounded by server-side validation.

For matched-condition scoring, use the same `map_id`, `seed`, `duration_seconds`, `mode`, and `bridge_profile` for every compared subject. The training service reports condition results and evaluation counts; compare only completed, verified matches with the same condition key. A neural trace or score from a different map, seed, duration, slot assignment, or runtime is not a matched comparison.

## Inspect and annotate a life

`GET /api/v1/lives` lists public samples plus your own private candidates when authenticated. `GET /api/v1/lives/{fly_id}` returns the birth FlySpec, optimizer origin (when accessible), ancestors, descendants, evaluation conditions, original scores, replay IDs and researcher notes. Read `/api/v1/lives/{fly_id}/experiences/{match_id}` for existing motion, intake and neural observations; this starts no computation. A failed evaluation has no score, and zero food intake does not imply no movement or no neural activity.

Only the designer can append a note. Send an `Idempotency-Key` header when posting `/api/v1/lives/{fly_id}/notes`:

```json
{"action":"investigate","reason":"Test this candidate with a longer horizon and additional seeds.","match_id":null,"supersedes":null}
```

Actions are `retain`, `investigate`, `stop_exploring`, `hypothesis` and `correction`. A correction names the earlier note ID in `supersedes`; it preserves the original. Notes do not alter scores, stop jobs or change rankings. They follow sample visibility; saved/public samples have public notes, but private linked experiences stay hidden until their trajectory is published.

To branch, use the sample ID as a new training plan's `founder_id`, choose an optimizer and explicit evaluation budget, then submit the plan. The child inherits a birth design, not an acquired neural state. See [the life ledger contract](LIFE_LEDGER.md).

## Select brain dynamics

`GET /api/v1/season` now includes `models`. Set `FlySpec.model_profile` to `malecns-lif-cpu-v1` or experimental `malecns-rate-cpu-v1`. Each training session retains its founder model. The latter is a continuous-rate network, not a spiking model, and supports the legacy arena bridge only. Its full-connectome Adam response trainer is documented in [RATE_MODEL.md](RATE_MODEL.md). Teaching loss and embodied fitness must be reported separately.

## Inspect a design before running an embodied match

`POST /api/v1/flies/preview` accepts the same authenticated `FlySpec` as submission.
The paired preview implementation returns `neural-design-preview/v2`: four fixed
odor conditions (left, right, bilateral, background only), each starting from
rest, with 120 ms of model activity sampled every 10 ms. The odor pulse occupies
20–80 ms. The encoder retains 8 mV tonic input on each side and adds 40 mV on the
stimulated side; "background only" does not mean zero injected current.

`stimuli[].samples[]` contains `time_ms`, the input over the preceding interval,
`circuits` for the submitted design, and `reference_circuits` for the unmodified
WT of the same model. `spec` and `reference.spec` identify both designs. Inspect
all samples, including response decay; the final sample alone is insufficient.
The LIF model includes spike totals; the continuous-rate model returns null for
spike totals. Neural activity differences are not fitness or biological validity.
Use an embodied match to evaluate behavior.

Check the response schema: an older running backend may still return v1, which
has no paired WT or time course. Do not invent those missing observations. The
current local static site also offers a precomputed Nectar example at
`/examples/neural-preview-nectar-v2.json`; it belongs to that recorded FlySpec,
not to any new draft. The paired API requires deployment of the updated backend.

## Evaluate a saved research offspring

Read `/season` for compatible `sensory_profiles` and `sandbox_ready` on each match profile. To compare a saved offspring with WT or a public fly, POST `/matches` with `sandbox: true`, both `fly_ids`, and the same `bridge_profile`, `sensory_profile`, map and duration used in training. Use a new seed to evaluate outside training. `/tournaments` also accepts `sandbox: true` and swaps positions; sandbox series support 1–180 seconds per match, while ranked tournaments retain their 1–30 second limit. Sandbox results have replays and local series standings but do not earn public leaderboard points. Training accepts 1–30 seconds per evaluation; 1–2 seconds is only a workflow trial.
