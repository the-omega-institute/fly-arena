# Phenotype Lab API and local execution

The research API is additive under `/api/v1`. Legacy matches, receipts, neural profile, readout files and competition routes retain their v1 interpretation. Research experiments are independent solo trials and never enter match standings. The service tests use explicit fake probe fixtures for orchestration assertions; those fixtures are not biological evidence.

`GET /research/catalog` returns `schema_version`, the scientific module's implemented `probes`, its non-calibrating `profile_manifest`, frozen server references, executor descriptors and inactive integration descriptors. A missing or unprepared profile is reported unavailable. Reading the catalog does not calibrate, activate credentials, launch external designers, or run a simulation. Canonical reference artifact initialization can occur on first read.

`POST /experiments` accepts an authenticated owner's design:

```json
{"fly_id":"0123456789abcdef0123456789abcdef","probe_id":"gradient-v2","seeds":[42],"duration_seconds":3}
```

The fly ID above is illustrative. The requested ID must exist and belong to the authenticated owner. Supported probe IDs come from the catalog, seeds are distinct nonnegative int32 values (one to eight), and duration is an integer from 1 to 30 seconds. Unknown fields, user-selected reference subjects and privileged provenance are rejected. A caller can supply `Idempotency-Key` (1–128 characters). Retrying the identical request returns its existing experiment, including after completion or an availability change; reusing the key with a different request fails with 422. Admission runs in a SQLite immediate transaction and permits at most 12 unfinished experiments per owner. Match and experiment idempotency namespaces are separate.

The 202 response is an experiment with `id`, `owner`, `status`, `error`, `spec`, `subjects`, `reports`, `comparison`, `created`, and diagnostic generation/condition fields. `subjects` is the server-frozen ordered wildtype/official/design triplet; each new entry contains `role`, `fly_id`, `name`, `artifact_id`, and a copy of `parent_id` (from the saved spec), `reference_kind`, `submission_channel`, and `release_id`, including explicit nulls. Existing experiment JSON, idempotent responses, artifacts and results are not rewritten. Frozen UI details use only this snapshot: an absent field means “Not recorded in this experiment”; explicit null means unknown provenance/channel or no supplied parent/release. Current fly metadata never fills a missing frozen field. `GET /experiments` lists the latest 100 public experiments; `GET /experiments/{id}` returns one or 404. Published research designs and reports have the same public workspace visibility as the existing MVP.

`POST /flies` persists the compiled artifact and design, then idempotently admits one gradient-v2 / seed 42 / 3 second triplet. The Fly response contains `experiment_id`, `experiment_status` and `experiment_error`. Admission failures produce explicit `experiment_status: "error"` and a diagnostic, while retaining the saved design. The internal `schedule_saved` use case can retry the same design with its stable automatic idempotency key. Queued experiments do not execute inside HTTP handlers. `arena serve` starts a queue dispatcher that launches `python -m flyarena.services.research_job` as a separate process; `--no-worker` leaves jobs durably queued. The child renews its lease while executing whole trials.

Queue generations are monotonically increasing; heartbeat and terminal writes require the current unexpired lease and generation. An expired first attempt is retried once, an expired second attempt fails. Stale completions are rejected. Each generation writes a distinct evidence directory under `research/runs/{experiment}/{generation}/{seed}/{role}`. Errors retain completed reports and an explicit failed status with no synthesized comparison. A crash leaves recoverable queue state rather than a successful placeholder report.

## Conditions, receipts and comparisons

Application `ConditionSpec` freezes the complete probe catalog definition, actual seeded scene, profile manifest, runtime closure, seed and duration. Its `condition_key` excludes subject, artifact and provenance. `run_key` adds the artifact digest to that condition identity. The scientific receipt has its own deterministic condition key for profile/runtime/scene/seed/horizon/probe/ablation/stimulus/decoder; the service reconstructs that exact key and requires equality. Source files, dependency closure and embodiment assets represented by the scientific runtime are frozen at admission; a changed closure fails execution instead of silently changing the experiment.

The worker executes WT, official and design independently for every requested seed. Reference trials alone can be reused by the full condition+artifact key. The cached record must still identify the same reference fly and pass all receipt and evidence checks. Design trials always execute. Tampered/missing cached files cause a fresh reference trial. A reference artifact equal to a user's weights does not transfer reference provenance.

A complete report requires a canonical receipt digest, all receipt-bound evidence file digests, an evidence/report match, a subject/artifact match and the scientific `verify_evidence` check, including recomputed metrics and its complete time grid. Verified application envelopes are also placed in the local immutable object repository. The weight artifact identity remains separate from these provenance and evidence envelopes.

Comparisons require exactly one complete report per subject per seed, identical scientific condition keys, profiles and horizons. Trajectories must have the same complete time grid and horizon; divergence is the time integral of Euclidean separation divided by horizon. Per-seed official-minus-WT and design-minus-WT metric deltas retain null when either input is missing/null. Failed, partial, incomplete or mismatched trials never become zeros or a successful comparison. `ComparisonReport` exposes `schema_version`, `paired` (seed, fly_id, reference_fly_id, deltas, trajectory_divergence_mm) and `conditions`. A mutation can produce a genuine zero effect; the server makes no improvement claim from motion or neural activity.

## Interventions and lineage

`FlySpec` remains `flyspec/v1`, with an additive `interventions` list, default empty:

```json
{
  "selector": {
    "pre": {"class":"olfactory", "side":"L"},
    "post": {"ids":["123456"]}
  },
  "scale": 1.1
}
```

The neuron ID is illustrative and must be replaced with an actual canonical decimal ID. Endpoint fields are exact `class`, `type`, `side` (`L` or `R`) and distinct `ids`; present fields intersect, while pre and post constrain the corresponding edge endpoints. Omitted endpoints impose no constraint. Side follows the imported metadata's `rootSide` falling back to `somaSide`; unknown side never silently becomes bilateral. Metadata must match the pinned `neurons.json` hash and canonical graph order. Unknown annotations/IDs, empty endpoint selectors, empty results, ROI, regex and executable selectors reject.

All interventions, outgoing circuits and explicit edge deltas sum in canonical log space. The compiler rounds final deltas to 12 decimals, checks final per-edge multipliers [0.5, 2], and budgets final structural log changes plus intrinsic parameters. Overlap and cancellation are evaluated after summation. Structural edges with zero baseline weight retain their original v1 structural budget cost; effective-change previews separately identify the edges with nonzero weight. Existing budget constants and phenotype hashing are retained. Reports include structural/effective edge counts, affected/effective neurons, structural/effective synaptic contacts, intervention summaries and metadata digest. `changed_edges` remains the structural final-delta count for compatibility.

Published new artifacts store sparse resolved edge indices and log deltas with format `resolved-log-delta/v2`. Loading verifies artifact identity, model/budget, mutation file and reconstructed weight digest. Legacy `node_delta`/`edge_idx`/`edge_delta` artifacts still load unchanged. Existing artifacts are never rewritten. Parent links require the same graph and model profile and record lineage only: a child's entire spec is absolute relative to canonical baseline, never an implicit multiplier on parent weights.

## Reference and submission identity

`reference_kind` is server-owned: `wildtype`, `official`, `user`, `ai`, or null when provenance was not recorded. `release_id` identifies the canonical server seed release, otherwise null. `submission_channel` is `seed`, `web`, `api`, or null when provenance was not recorded. For a saved fly with no `fly_provenance` row, detail and list responses return explicit null for `reference_kind`, `submission_channel` and `release_id`. Reads do not insert provenance or backfill historical records. Clients must accept these nullable fields instead of assuming user/web; older responses may omit them. Recorded rows and new submission behavior are preserved. The deterministic registry derives references from trusted seed definitions, graph/profile and validated compiled artifacts. It does not migrate an existing record based on name or `owner="arena"`; legacy records retain their saved IDs, owners, specs and artifacts without reattestation. Same-name records and cloned official weights gain no reference authority. Ownership is independent of provenance: an authenticated owner can still select and admit their legacy saved design. Cards and selectors show saved-record IDs alongside names, trusted-reference or ownership labels, and “Provenance not recorded” where applicable. Neither user/ai labels nor web/api channels prove human or AI authorship.

Session submission is `web`. Local browser bearer submissions are also `web` when Fetch Metadata reports `Sec-Fetch-Site: same-origin`, or when the client explicitly sends `X-Arena-Submission-Channel: web`. The only accepted declared channels are `web` and `api`; these labels grant no reference authority. Other bearer submissions default to `api`. An Arena-issued registered agent token remains `ai`/`api` even if a caller declares `web`. This is a registered submission-channel assertion, not proof that an AI authored a design. Legacy bearer API tokens remain user/API. Public `provenance`, `scientific_version`, `reference_kind`, `release_id` and `submission_channel` claims are forbidden. The OIDC `IdentityProvider` port retains the existing discovery, PKCE, nonce, signature, CSRF, session and revocation behavior and remains inactive by default.

Ranking lives in `services/ranking.py` as `ranking/v1`. It scopes by season/runtime/scenario/mode/bridge profile; unqualified legacy requests project the latest compatible scope, never a mixture. `/leaderboard` accepts optional `runtime_hash`, `scenario_id`, `mode`, `season_id` and `bridge_profile`. The returned rows identify their ranking policy and scope.

Local verification:

```sh
.venv/bin/pytest -q tests/test_core.py tests/test_auth.py tests/test_evidence.py \
  tests/test_research_service.py tests/test_interventions.py \
  tests/test_integrations.py tests/test_architecture.py
```


## Arena bridge dispatch and discoverable metadata

`MatchRequest` and `TournamentRequest` accept `bridge_profile: "legacy-v1" | "sensorimotor-research-v2"`. An omitted field means legacy v1, including historical receipts. V2 dispatch instantiates the actual CPU backend, unclipped bilateral encoder, frozen descending kernel readout, and separately versioned neural motor transfer. It never falls back to v1. `GET /season` adds `default_bridge_profile` and `match_profiles: [{id,name,ready,reason?}]`. V2 match admission requires the source-bound held-out body qualification in addition to decoder calibration. A failed or stale qualification returns an explicit 422. Research trials remain available for measuring an unqualified transfer without admitting it to competition.

Admission freezes the selected runtime hash; the durable job checks that same selected profile, and the receipt binds it, the actual CPU backend, readout metadata, complete Python sources, package versions and FlyGym assets. Tournament schedule entries preserve the requested profile. Ranking separates profile scopes even if a caller supplies an equal runtime label. `GET /leaderboard?bridge_profile=...` can select a profile explicitly. Historical verification compares recorded identities internally instead of requiring today's source hashes.

`GET /connectome/annotations?field=class|type|side&q=&limit=50` returns `{field,items:[{value,count}],metadata_sha256,total}`. Limits are 1–100; search is a bounded case-insensitive substring match, with exact pinned values returned in sorted order. `total` counts matching distinct values before truncation. Counts are canonical neuron counts. Class examples in the installed graph include `olfactory`, `ALPN`, `ALLN`, and `Kenyon_Cell`; `ORN` is not an invented class alias. Null/empty annotations are excluded.

Every new `probe-report/v2` includes a required typed `scene` containing actual size, x/y/yaw spawns, obstacle positions/sizes, food IDs/positions/initial amounts, mirror and cue timing. The scene equals the receipt condition and emitted scene file. The independent verifier rejects substituted geometry, mismatched conditions, modified metrics and incomplete time grids. Reports retain censored food latency and branch no-choice values.

Match and tournament idempotency retries resolve before mutable profile availability. Typed normalization of additive default fields preserves keys whose stored requests predate `bridge_profile`. A retry returns the original immutable resource; it never readmits its old runtime. Reusing a key across resource kinds or changed request semantics fails.
