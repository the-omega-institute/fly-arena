# Recoverable paired competition series

A series is a durable tournament, identified by its tournament ID. Open
`#tab=arena&series=<id>` to recover it after a reload, or use
`GET /api/v1/tournaments/<id>`. Arena lists the authenticated user's recent series;
`GET /api/v1/tournaments?owner=<owner-id>` filters before the 30-series limit.
These reports retain the existing public-read policy. Filtering is not authorization.

The `paired-series/v1` report derives its expected schedule from the saved tournament
specification: each seed, each unordered pair of entrants, and both spawn orders.
It does not infer completeness from the number of surviving match records. Admission
uses that same schedule builder. Existing tournaments need no migration. Profile
fields omitted from historical specifications retain legacy-v1 / odor-only-v1 /
non-sandbox semantics.

Each `schedule` row reports its seed, spawn order (1 or 2), slot-ordered fly IDs,
match IDs, status, issue codes, recorded errors, and per-fly leg outcomes when valid.
`matches` still exposes the underlying records, including duplicates and unexpected
matches. `unexpected_match_ids` identifies records outside the schedule. A failed
or missing result is never replaced by zero, a draw, or a successful comparison.
The UI exposes verified replay links and inspection links for unfinished records.

- `complete`: every expected leg exists exactly once, is verified with valid scores
  and a winner/draw verdict, and satisfies the saved conditions and shared evidence.
- `running`: all expected records exist with matching conditions; at least one is
  queued or running, with no failed or invalid leg.
- `incomplete`: a missing, duplicate, failed, unexpected, invalid, or mismatched leg
  prevents a conclusion. This takes precedence even when other legs still run.

Checks include participants and seed; scenario, mode, duration, bridge and sensory
profiles, sandbox flag and season; tournament ownership/membership; common runtime;
and consistent immutable artifacts for each fly across swapped slots. Runtime and
artifact identities are checked against the durable match records, not a separately
pinned tournament-level runtime manifest. This projection consumes independently
verified worker verdicts; it does not rerun physics or replace replay verification.
Unqualified sensory profiles cannot produce non-sandbox competition standings.
Sandbox outcomes remain modeled experimental outcomes.

`standings` is empty until the series is complete. Once complete, it reports each
fly's played legs, wins, draws, losses, and points (3 per win, 1 per draw, 0 per loss),
using the existing `ranking/v1` arithmetic. A slot win is credited to the fly occupying
that slot in that leg. Equal points remain equal: display order by ID is not a
scientific tiebreak. Leg scores use the selected mode's metric and are not pooled
across different metrics. A first-leg win remains a first-leg result.

A complete series establishes the recorded outcomes of those modeled flies under
those declared conditions and seeds, with starting-position exchange. It does not
establish a global ranking, statistical significance, general improvement across
scenarios, natural behavior, learning, memory, or biological intelligence. More
seeds do not turn the simplified sensory, neural, motor, or body models into
validated biology. Replay and failure inspection remain part of interpreting the
result. No simulation, steering, body pose, or activity is synthesized by this report.

Solo runs and contact `duel` pairs currently use individual match submissions, not
the tournament API; this protocol does not retroactively invent durable series for
those submissions. Their existing partial-submission errors and match records remain
visible. No CI, admission qualifications, or global leaderboard policy is changed.
