# Electronic-life sample ledger

The Life archive joins existing designs and experiments into an inspectable individual history. It adds one append-only notes table; it does not create another simulator or rerun historical evaluations.

A user can open any accessible sample, inspect its birth parameters and optimizer origin, follow parents and children, read its recorded experiences, open behavior/neural replay, export the record, and prepare a new training branch or WT comparison. Preparing a plan starts no computation. Original full FlySpecs remain available, including edge interventions.

## Facts and interpretation

Facts come from the existing fly, training and match records: immutable birth design, parent, algorithm and proposal round, environment, seed, horizon, simulator context, original score, saved-from-training action, descendants, and replay evidence. An evaluation failure has a null score; unavailable evidence has an explicit status.

Researcher notes are separate: retain, investigate, stop exploring, hypothesis, or correction. Only the designer can append them. Each correction references an earlier note on the same life. There is no edit/delete route. Decisions are descriptive: recording “stop exploring” does not cancel an active job; recording “retain” does not qualify a champion. Existing pause/stop/save controls still perform those actions.

Notes follow sample visibility. Private candidates and their notes are owner-only until saved or published. Saving a candidate alone does not expose its private training origin, evaluations, linked notes or correction chains. Publishing the completed trajectory makes those facts accessible. Current MVP public designs/notes are public; there is no team/private-library feature.

## Reading the zero-score example

In the published random-search demonstration, each round contains two independent candidates. The final round scores are 0.4032 and 0; that round's best is 0.4032 and the best observed through that round remains 1.3984. A candidate's zero never overwrites the historical best. Random search uses “round,” not inherited generation.

Match `7803a95f436a44669e2e555b1190955a` recorded one simulated second, 101 frames, about 14.91 mm sampled thorax travel and 1,960,853 neural spikes, with no intake event. This is evidence of no food intake within that window, not no activity or an implementation failure. The first-intake timestamp is an event batch timestamp; path length is a sampled lower bound, and mouth-to-food distance was not recorded. Summaries expose final recorded population activity, while replay retains the temporal traces.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/lives` | Latest 200 accessible individuals |
| `GET /api/v1/lives/{id}` | Birth, origin, up to 24 ancestors, 100 direct descendants and 100 recent experiences, all visible notes |
| `GET /api/v1/lives/{id}/experiences/{match}` | Existing evidence summary; no simulation |
| `POST /api/v1/lives/{id}/notes` | Owner-only append, required Idempotency-Key, up to 200 notes per life |

Notes linked to accessible older experiences remain visible even outside the 100-experience window. Idempotent retries return the same note. A reused key with changed content is rejected. Identity uses the existing platform layer; no identity service is added to scientific execution.

## Research scope

This takes the useful Trureturing distinction between proposed claims and evidence-backed results: preserve unsuccessful candidates, fix evaluation conditions, inspect counterexamples, and revise interpretations explicitly. It does not add a voting system, multiple reviewer roles, formal-proof gates or per-file governance.

The current biological scaffold is the public connectome; synaptic multipliers and intrinsic parameters are a modeled design space. Runtime can be LIF or experimental continuous rates, with no within-match plasticity. Branches inherit parameter designs, not the parent's final neural state. A single short training condition is not generalization or biological equivalence. Future rate/spiking models and learning rules must record their own runtime and conditions in the same ledger.
