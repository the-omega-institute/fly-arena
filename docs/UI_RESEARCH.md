# Research UI integration and verification

This frontend implements the coordinator-approved interface and integration additions from the `<workspace-root>/fly-upgrade-interface.md` snapshot. The integration UI slice owns `web/` and this document. It does not alter scientific sources, decoders, sensors, training identity, stored experiments, immutable artifacts, or backend admission rules.

## Scientific reports and scene rendering

The Phenotype Lab consumes real experiment reports and frozen subject identities. `report.scene` supplies the arena boundary, obstacles, spawn markers and initial food/source markers. Source labels retain exact IDs and coordinates in accessible SVG titles. Food markers describe initial sources, not remaining food. The plot does not synthesize scene geometry from a probe catalog or retrofit historical reports that lack a scene.

Both axes use one physical pixels-per-millimeter scale. The extent includes the scene, obstacles, food and every reported trajectory point, including positions outside the scene boundary. Full-horizon trajectories remain visible beneath the scrubbed paths. Start circles, end squares, role symbols, solid/dashed/dotted paths and a shared reported-time marker supplement color. WT is white on a deliberately dark plot surface in **both** light and dark themes. Playback and interpolation stop at the recorded interval and do not extrapolate missing positions.

All three frozen names, full subject IDs, full artifact hashes, lineage, release and submission channel are readable and selectable. Missing historical metadata remains **Not supplied**. `Your design` appears for a Lab subject only when the authenticated viewer ID equals `experiment.owner`; other viewers see **Submitted design**. Cached local bearer identities are resolved through `/me` before being displayed as authenticated. NyxID session/CSRF handling remains in place. Neither names nor client specifications grant trusted provenance.

The UI requires all frozen subject/artifact pairs, complete report statuses, receipt references, identical condition keys, horizons and time grids before showing paired inference. It displays server deltas without inventing measurements. Zero deltas mean **Null effect**; missing latency means **Missing / censored**; `branch_choice = 0` is explicitly **No choice**. Censor flags remain separately visible when supplied. Neural activity alone does not establish useful steering or biological validity.

The catalog's reason, limitations and unavailable capabilities are visible. Motor/protocol IDs, backend/model/sensor/readout/embodiment IDs and dependency hashes are inspectable. Report receipts retain their own frozen profiles, independently of the currently advertised catalog profile.

## Design, metadata and trial admission

The initial editor is an explicitly **Unsaved canonical draft**, with no stored fly highlighted. Choosing a collection fly creates an unsaved draft from that parent. Arena participant selection does not change the editor's parent highlight. JSON import/export, unknown extension fields, exact large neuron IDs, nested parameters, edge deltas, interventions and pending drafts across login are preserved.

Olfactory/projection/local/readout/descending controls remain primary. Vision, memory and motor edits live in a collapsed **Exploratory edits** disclosure. The UI states that these edits do not enable vision, memory tasks, learning or extra motor action channels. The model has two bilateral locomotion action channels; CUDA, biological validation and memory qualification are not asserted. No live NyxID configuration or activation was performed.

Advanced pre/post class, type and side fields query:

```
GET /api/v1/connectome/annotations?field=class|type|side&q=...&limit=50
```

Discovery is debounced and cancels stale requests. Search text is limited to 128 characters. Suggestions use the exact returned metadata strings and neuron counts; each response's actual `metadata_sha256` is displayed. Expanded suggestions are clickable as well as available in native datalists. Only contract-supported `L`/`R` side values are selectable; other actual metadata side values remain visible as disabled evidence. No invented `ORN` class or remapping is used. Unknown selectors still require server validation. Loading, unavailable endpoints and failed queries are displayed explicitly.

Compiler preview consumes the agreed **`interventions`** field, alongside structural/effective changed edges, affected neurons, synaptic contacts and authoritative budget. Edits invalidate previous preview results. The frontend admits **1–8 distinct nonnegative int32 seeds** and an **integer horizon of 1–30 seconds**, with English and Chinese validation errors. Duplicate seeds are rejected instead of silently deduplicated.

## Match profiles and navigation

The Arena reads `season.match_profiles` and `season.default_bridge_profile`. It defaults new requests to **`sensorimotor-research-v2` when advertised ready**; otherwise it displays the server's advertised default explicitly. If the profile contract is absent, setup remains unavailable. Every web match **and tournament** request includes the selected `bridge_profile`. A server rejection leaves that selection intact and shows the error; the UI never retries under another profile.

Historical replay labels come from `match.request.bridge_profile`. A missing field retains **Legacy v1** semantics, regardless of today's default. Current scientific readiness never relabels an old replay. Legacy and experimental labels are translated while scientific IDs remain unchanged. Map labels use English or Chinese consistently for the selected locale.

Routes use `#tab=design|lab|arena|code`, optionally `experiment=...` or `match=...`. Existing `#experiment=ID` links remain valid. Tab navigation, returned experiment IDs and replay selection update browser history; `hashchange` and `popstate` restore the corresponding view. Both same-document deep links and browser back/forward are tested.

## Verification on 2026-09-16

The final production build and 14 Node contract tests pass. The build retains the existing non-fatal React/Three.js bundle-size warning (approximately 1.21 MB minified JS).

Actual browser QA served the production build directly from the isolated **127.0.0.1:8082** API, with `--no-worker` and:

```
ARENA_VAR="${ARENA_VAR:?Set ARENA_VAR to an isolated run directory}"
```

The real read-only experiment is **`9320e8fad58f4e59bf50b91f1ff4e38b`**, complete with three independent frozen reports. Its returned receipt references are:

- `c329e81d3dcb24e406379b904a6344e7ef6723795f84636cbb1c1aaa56377ac6`
- `c5df31ee55c25300672dcc080dc507caddd6bce4c0a12964dcdfd28ae534eae0`
- `f589b8766530b9414e5e06b01be806f2364895eed9f09a76b2b185c24fbb95ec`

The real run checked the anatomical preview, initial draft identity, collapsed exploratory controls, actual annotation search/count/hash, anonymous ownership labels, all three frozen identities and trajectories, full horizon scrubber, English/Chinese, light/dark, 390px layout, browser history and real profile readiness. It recorded **zero page exceptions, console errors, failed requests and API mutations**. No experiment or match was created in this run, and it is not claimed as new scientific simulation or receipt re-verification.

Actual pinned annotation discovery returned **`olfactory` (2639 neurons)** and metadata SHA-256 **`1959c63507960e79531f098afcaee54869f4deed064fd448372c5b409e0bcd5c`**. The available class list also contained `ALPN`, `ALLN` and `Kenyon_Cell`.

The existing immutable real experiment predates `report.scene` and has no scene on any of its three reports. Its UI correctly states that geometry is unavailable and fits only recorded positions. Real food/wall overlay evidence requires a newly produced report carrying the agreed scene field. The slice deliberately did not mutate historical evidence or inject synthetic geometry into the real API.

At the observed QA point the service advertised v2 match readiness as false because its engine qualification file was not yet available. The UI displayed that exact reason and explicitly selected Legacy v1. Successful v2/legacy request payloads and the rejection-without-fallback behavior are covered by the separate synthetic contract suite, not claimed as real match submissions.

## Labeled fixture regression and reproduction

`web/tests/ui-fixtures.mjs` uses `TEST-` identities, synthetic geometry and deliberately non-scientific receipt strings. Every fixture mutation is intercepted in the isolated browser. Fixture coverage includes scene food/walls with correct physical proportions, owner and non-owner labels, unavailable profile reasons, missing/censored/no-effect data, partial/failed/mismatched trials, strict admission errors, bounded annotation suggestions and hashes, compiler intervention details, complete spec round trips, save navigation, same-color replay identity, explicit match/tournament profiles, server rejection without fallback, authenticated local identity verification, locales/themes/mobile and deep-link history.

`web/tests/real-ui-smoke.mjs` uses the actual HTTP API, does not inject auth or response fixtures, and blocks non-GET/HEAD API requests. The fixture suite and real suite write separate evidence JSON. Set `QA_OUTPUT` to an isolated run directory; it contains `fixture-checks.json`, `real-smoke.json`, real comparison screenshots for both locales/themes, mobile screenshots, annotation design evidence and the real Arena profile state. Desktop/light, fixture scene and real mobile screenshots were visually reviewed.

Reproduce with an authorized isolated API serving `web/dist`:

```sh
npm --prefix web test
npm --prefix web run build
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:?Set PLAYWRIGHT_BROWSERS_PATH}" QA_BASE_URL=http://127.0.0.1:8082 npm --prefix web run test:ui
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:?Set PLAYWRIGHT_BROWSERS_PATH}" QA_BASE_URL=http://127.0.0.1:8082 npm --prefix web run test:ui:real
```

`QA_EXPERIMENT_ID`, `QA_OUTPUT` and `PLAYWRIGHT_MODULE` are configurable. For development, `ARENA_API_URL=http://127.0.0.1:8082 npm --prefix web run dev -- --port 5174 --strictPort` isolates the Vite proxy; the ordinary default remains port 8080. The UI worker stops its isolated API and Vite process before completion. No commits, pushes, deployment, live auth activation or external messages are part of this slice.

## Bounded v3 correction: selection and replay transitions

The Lab now stores its chosen design separately from the incoming collection. On mount, an intentional parent selection change, or an authenticated owner change, it initializes from an owned parent selection (otherwise the first owned design). A refreshed or reordered `flies` array only validates the current choice. Explicit B remains B when parent A is selected, including after submitting B and opening the newly created experiment; an explicit blank remains blank. If the chosen fly disappears or changes owner, the choice clears and **Run comparison** disables; a later refresh does not silently restore or substitute a design. This reconciliation happens before rendering, so the displayed choice and submitted ID agree.

Replay resources now carry the requested match ID and a loading/ready/error state. The render gate hides resources whose ID differs from the focused match even before effect cleanup. Focus changes clear scene, frames, scores, traces and playback; a loading or failed focused match does not display the anatomical preview as a replay. Scene and frames commit atomically only after both requests succeed. Cleanup aborts both requests, while an active-request guard also ignores late success and failure from transports that finish after cancellation. A failed endpoint aborts its sibling and leaves the requested match unavailable. Replay loading has its own status instead of owning the global action busy/error fields, so navigating to a queued match cannot leave setup busy or surface a superseded replay error. Loading and unavailable labels are translated in English and Chinese. Recorded match profiles and backend request/response interfaces are unchanged.

Validation for this correction:

- `npm --prefix web test`: **22 passing tests**, including eight executable transition tests for stable selection, explicit blank, context and identity changes, missing/transferred designs, partial replay loading, each endpoint failure, A→B→C cancellation, same-ID retry and empty frames. These execute production transition/request functions with deferred promises, including transports that ignore cancellation; they do not assert source strings.
- `npm --prefix web run build`: TypeScript and production Vite build pass. The existing large-chunk warning remains.
- `npm --prefix web run test:ui:transitions`: the actual production React/Three.js app runs in isolated Chromium. All HTTP requests are intercepted at the test origin, including static `web/dist` assets. The runner opens no listener, starts no backend, and performs no live authentication or API mutations. It requires the installed Playwright module and browser cache, configurable using the existing `PLAYWRIGHT_MODULE` and `PLAYWRIGHT_BROWSERS_PATH` conventions.
- Browser coverage confirms B survives two real 2.5-second refreshes and the comparison POST targets B; deletion clears and disables selection; a half-loaded replay remains empty; HTTP 503 from either endpoint leaves no prior replay; rapid pending A→B→C cancels A/B; queued navigation clears loading; browser back/forward preserves identity; and the unsaved canonical draft survives the sequence. A DOM mutation observer checks for transient match/scene mismatches. The English/light desktop and Chinese/dark 390px error state are covered, with no horizontal overflow.

Reproduce without starting a service:

```sh
npm --prefix web test
npm --prefix web run build
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:?Set PLAYWRIGHT_BROWSERS_PATH}" npm --prefix web run test:ui:transitions
```

Synthetic browser results and screenshots are written to the configured `QA_OUTPUT` directory: `transitions.json`, `slow-B.png`, `failed-B-dark-zh-mobile.png`, and `final-C-light-en.png`. They are UI regression evidence, not scientific trials or backend qualification. Earlier scientific and UI evidence remains preserved. The coordinator will issue the new source/build snapshot after this worker completes.
