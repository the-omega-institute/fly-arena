# Grounded Chrono reuse boundaries

This implementation uses a modular monolith with provider-independent contracts, SQLite research admission, local whole-trial execution, and immutable artifact storage. It activates no external service or credentials. Integration fixtures use `httpx.MockTransport`; passing those tests establishes wire handling, not a working production account or a live service qualification.

The source snapshots inspected for this slice are under `<workspace-root>/chrono-research`. Each source link below is pinned rather than referring to a changing branch.

| Component | Inspected source pin | Reuse boundary |
|---|---|---|
| NyxID | [afdb3ef0](https://github.com/ChronoAIProject/NyxID/tree/afdb3ef06a4e14a86d810a14982de3be01252090) | Existing opt-in OIDC adapter behind `IdentityProvider`; no research code discovers or activates credentials. |
| chrono-bucket | [4087662e README](https://github.com/ChronoAIProject/chrono-bucket/blob/4087662e2a65e3747b3203ba619eca7342089272/README.md), [object routes](https://github.com/ChronoAIProject/chrono-bucket/blob/4087662e2a65e3747b3203ba619eca7342089272/src/routes/objectRoutes.ts) | Real fenced whole-artifact upload and authenticated raw digest-checked download adapter, disabled unless explicitly configured. |
| Ornn | [0041cfe1](https://github.com/ChronoAIProject/Ornn/tree/0041cfe1ad08517e3407eed984138e0a187ccd7e), [API stability](https://github.com/ChronoAIProject/Ornn/blob/0041cfe1ad08517e3407eed984138e0a187ccd7e/docs/API_STABILITY.md) | Versioned designer skill/package inputs. Alpha compatibility is not guaranteed; local resolution requires exact version and artifact digest. |
| CMA | [b147d749 trigger contract](https://github.com/ChronoAIProject/cma/blob/b147d74944cf2363b4a32fae5a1cdc8e04989079/docs/CMA_Trigger.md), [REST](https://github.com/ChronoAIProject/cma/blob/b147d74944cf2363b4a32fae5a1cdc8e04989079/docs/API_REST.md) | Explicit user entry to an external designer in the visitor's sandbox; no automatic launch on app/catalog read. |
| Heca | [9bcbef63](https://github.com/getheca/heca/tree/9bcbef63326582ecf25771af5ba3e992482f2083) | Optional future outer orchestration around whole experiment requests. Unavailable here. |
| Aevatar | [1df08db0](https://github.com/aevatarAI/aevatar/tree/1df08db0d88627eb47c2e8a9a44b5df806ee293d) | Optional actor/agent orchestration around the application. Unavailable here. |
| Talos | [4d52e58e](https://github.com/ChronoAIProject/talos/tree/4d52e58e1acc3677b23b34e44f60d11c2191c4ad), [OpenAPI](https://github.com/ChronoAIProject/talos/blob/4d52e58e1acc3677b23b34e44f60d11c2191c4ad/specs/talos-openapi.yaml) | Borrow lease token/capability admission concepts. Its browser operator is not advertised as a scientific worker. |
| Athena | [059ec150](https://github.com/ChronoAIProject/athena/tree/059ec1502fc9826df138861320eaaefaefe0136c) | Borrow hardware/toolchain/artifact preflight and explicit qualification patterns. Its training stack is not a fly neural backend. |
| chrono-sandbox | [f3fbe0d9](https://github.com/ChronoAIProject/chrono-sandbox/tree/f3fbe0d9d4ce65195578d0e27501b067f1ffe0a9) | Potential whole-trial environment placement only; unavailable. |
| developer platform | [c7a0ec1c](https://github.com/ChronoAIProject/chrono-developer-platform/tree/c7a0ec1caf8f5ff90c49f82dac8ceed507222451) | Future build/test/deploy/activate outer pipeline; not invoked. |

The `chrono-storage` repository did not provide a usable implementation in the inspected inventory. The implemented adapter is based on **chrono-bucket**, whose object routes actually call `putObject` with resolved mutation transport and stream raw downloads. This distinction prevents claiming storage support from an empty repository.

## Executed ports

`services/ports.py` declares `ArtifactRepository`, `ResearchRepository`, `IdentityProvider`, and `ExperimentExecutor`. `LocalArtifactRepository` implements atomic `put_if_absent` with an exclusive hard-link publication and verifies SHA-256 on reads; corrupt existing content fails without replacement. Research receipt envelopes exercise this repository in actual worker execution. `ExperimentRepository` implements transactional admission, stable idempotency, quota checks and generation/lease fencing. `LocalProbeExecutor` invokes the scientific `run_probe` for an entire solo trial with explicitly supplied data and artifact roots. The API dispatcher puts that adapter in a subprocess. No per-neural-tick network calls exist.

`NyxIDClient` implements the identity-provider interface without changing its existing OIDC security behavior. `AuthBoundary` continues to own browser sessions, CSRF and application agent tokens. Offline tests with actual RSA signatures still exercise this adapter. Core neural/body/backend/judge/compiler/contracts/research modules have a source import guard against provider, auth and HTTP dependencies.

`UnavailableExecutor` and `preflight` fail explicitly when a requested adapter or capability is unqualified. Integration discovery advertises CUDA, Talos-as-simulation, remote orchestration and other unconfigured services as unavailable. An installed Python class or passing mock test never changes a real capability badge to qualified.

## chrono-bucket wire behavior

`ChronoBucketRepository` accepts an explicitly supplied transport and defaults to disabled. It creates immutable content-addressed logical keys using SHA-256. Uploads call:

```text
POST /buckets/{bucket}/objects
?key={sha256}&contentType=application/octet-stream
&mutationGeneration=1&contentSha256={sha256}
```

The body is the exact artifact bytes. Generation one is permanently fixed for an immutable digest key. The caller does not increment a generation after a conflict, request tombstone recreation, or mix query and `X-Chrono-*` header transports. This matches the pinned server's all-or-none mutation transport. A late/stale upload cannot justify rewriting a deleted logical object. Retrying the same generation and digest is safe under the server's documented fence contract; a 409 propagates as failure.

Reads call `GET /buckets/{bucket}/objects/download?key={sha256}`, hash the raw bytes and reject mismatches. Upload verification downloads through that same authenticated service route rather than following a server-returned arbitrary URL. The offline fixture asserts exact query fields, no mixed headers, idempotent retries, conflict handling and corruption rejection. Authentication belongs in an explicitly configured transport outside scientific code. No live transport was configured for this repair.

## Ornn designer package pins

The inspected Ornn documentation says its 0.x alpha permits breaking minor releases despite `/api/v1`. Its concrete pinning examples are `ornn-sdk==0.7.3` and `@chronoai/ornn-sdk@0.7.3`; these are documented examples, not a claim that either package was downloaded or installed here. `OrnnPackageReference` records a reviewed registry commit, one of those exact SDK references, a skill ID, exact numeric skill version, and SHA-256 package digest. Its executable local path resolves bytes through `ArtifactRepository.get_verified`; mutable `latest` selectors and unreviewed SDK pins reject. Remote skill installation/execution is unavailable.

A future designer skill can read the catalog, produce a strict full FlySpec, validate it, publish under its owner's Arena agent token and request experiments. It cannot attest official provenance or inject arbitrary scientific versions. Its output remains subject to the same selector/budget checks and its API submission channel does not prove AI authorship.

## CMA explicit launch

A trigger links to `/api/v1/triggers/public/{public_id}/open/{placement}` and the published descriptor also supplies its badge URL, label and immutable content/revision information. `CMATriggerDescriptor` validates an HTTPS descriptor and returns the supplied launch link only when `user_requested=True`. It makes no launch request itself. No real public trigger is configured; `pub_example` in fixtures is illustrative.

The inspected contract separates read-only preview/open routes from visitor admission. Provisioning is `POST /api/v1/triggers/public/{public_id}/launches` with a caller-persisted `Idempotency-Key`, placement and `start_if_ready`, authenticated as the visitor. The browser's deliberate click can retain short-lived entry intent; a generic catalog read, prefetch or OAuth callback alone is not authorization. Future UI wiring must use an explicit user launch, preserve the server descriptor and target exact published profile revisions. Publisher credentials must never provision a visitor's resources. Profile authoring skill references use the source's ID and exact selectable version strings; an empty catalog is distinct from `503 profile_skills_unavailable`.

Heca and Aevatar can eventually orchestrate these outer designer and experiment requests. Talos lease tokens motivate fenced admission and late-result rejection but do not supply a MuJoCo/neural runtime. Athena's preflight checks motivate verifying profile readiness and execution capability before admitting an expensive trial; training performance or model support does not qualify this simulator. Whole-trial placement keeps transport latency and provider availability outside the neural timestep.

Run `tests/test_integrations.py` for local storage, Ornn pin resolution, CMA explicit links, fenced HTTP fixture calls, identity/executor port conformance and unavailable preflight. Run `tests/test_architecture.py` for source boundaries and incompatible-ranking isolation. No external activation or credentials are required.
