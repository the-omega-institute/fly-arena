# First comparison after saving a design

Saving from the design editor keeps the visitor in Design. It publishes the immutable design, selects that exact saved fly and brings the comparison panel into view. A NyxID round trip resumes only the save the visitor requested. Saving does not submit a match or open Arena/Train.

The panel offers the server-owned compatible WT reference and a selectable public fly owned by another designer. References, the visitor's own flies and designs with incompatible graphs or neural models are not presented as other designers' alternatives. If a reference is unavailable, the panel explains the absence and permits an available alternative; it never invents a competitor.

The initial observation window is **10 simulated seconds per match**. Visitors can select 2, 5, 10, 30, 60, 120 or 180 seconds. Two seconds is explicitly a workflow/initial-response trial. A longer window provides more opportunity to observe later behavior, but costs more computation and does not guarantee feeding, recovery, improvement or learning. Simulation time is not wall-clock waiting time.

Each selected reference produces one existing sandbox tournament: orchard food competition, seed 42, Legacy v1 and bilateral odor input, with the saved fly in each starting position once. The panel displays the number of matches and total simulated seconds before submission. WT plus another designer means **four matches**; at 180 seconds each this is **720 simulated seconds**, not a 180-second wait.

Only the explicit Start comparison action submits work. Progress and the result remain in Design. A mean food-intake summary requires the server's complete, verified two-match protocol and joins scores by fly ID across swapped positions. Partial, missing, failed or mismatched records do not become zero or a successful comparison. The result describes those conditions; it is not evidence of learning, general superiority or a public leaderboard ranking. The explicit next action opens Arena to inspect the recorded body/brain replay and prepare further experiments.

Submission keys, immutable request bodies and acknowledged series IDs are stored under the current owner and saved-fly IDs in this browser's local storage. Refresh or reopening reads existing reports without automatically submitting work. If a response is lost, explicit retry reuses its original key; acknowledged series are skipped. Local-storage failure cannot cancel server-side work; existing records remain available in Arena's series list. Resetting the panel is offered only after every acknowledged series has no queued/running legs.

## Duration boundaries

- The Arena web planner accepts 1–180 whole seconds for all its modes; the duration control presents the choices above and can display valid imported shorter values.
- Sandbox tournaments now accept up to 180 seconds per match, using the existing atomic admission, worker, long-replay sampling and verification path.
- Ranked tournaments retain a 30-second maximum. Training and phenotype probes retain their own 30-second API limits.
- Existing standalone match and observation-series APIs retain their 300-second limit so historical requests and research tooling continue to work. The new 180-second maximum is the public web interaction limit and the sandbox tournament limit.

## Verification scope

The DOM journeys test the saved-design handoff, WT/public eligibility, 180-second request construction, complete versus partial evidence, correct slot aggregation and refresh/retry recovery. Backend tests create durable 180-second sandbox pairs, verify atomic and idempotent admission, recover records after reopening the database and check that sandbox results earn no leaderboard points.

Real Chromium checks exercise the actual frontend at 1440 and 390 pixels in English and Chinese, including the login-return handoff, saved-design identity, explicit compute start, reload, results-before-Arena and horizontal overflow. These browser checks use synthetic API responses in an isolated context; their scores are UI fixtures, not new scientific results or a live NyxID-provider validation. No new 180-second physical study is claimed by these checks.
