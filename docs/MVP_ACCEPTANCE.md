# MVP delivery audit

Verified 2026-09-25 against the requested first usable version. The public
preview exists at <https://fly.omega.gift>; the complete scientific and
production programme in ROADMAP.md remains a future plan, and its unpassed
gates are recorded in VALIDATION.md. This delivery is a usable research MVP,
not a claim of biological fidelity or production readiness.

| User requirement | Delivered behavior | Evidence |
|---|---|---|
| Use a real fruit-fly connectome | Official MaleCNS v1.0 retained graph: 165,122 neurons, 25,563,197 edges; frozen provenance and hashes | Latest real match receipt in `evidence/auth-release-check.json`; `connectome.py` and `ATTRIBUTION.md` |
| Make network weights a central design capability | Circuit multipliers, per-edge log deltas and intrinsic parameters compile into immutable artifacts with overlap-aware mutation budgets | `compiler.py`, `contracts.py`, compiler tests; published web design and AI mutation described in `VALIDATION.md` |
| Humans design flies on the web | Anatomical Three.js workbench, parameter controls, budget validation, design publication, JSON import/export | `screenshots/design.png`; recorded Safari design → validation → publication workflow |
| AI submits its own flies | Same FlySpec and API contract, bearer identity, runnable designer script; actual mutated design and paired matches | `scripts/ai_designer.py`; remote AI tournament `836ddf7654554deaa413a400fef74d90` and `evidence/remote-matches.json` |
| Multiple maps and competition formats | Orchard, obstacle garden and ring; solo foraging, shared-resource competition, physical sumo and paired series with exchanged slots | Actual three-map matches in `evidence/remote-runtime.json`; shared-body contact tests. Sumo is a game rule, not natural aggression |
| Usable results and replay | Async queue, independent verdict, scores, leaderboard, anatomical playback and neural traces | Safari replay screenshot and workflow in `VALIDATION.md`; latest remote match verified with 41 frames |
| Architecture and trureturing research | Scientific core separated from platform identities; immutable inputs, fenced worker execution and independently checked evidence | `ARCHITECTURE.md`, `RESEARCH.md` with pinned upstream sources |
| Decide whether to start in C++ | Python orchestration plus native Numba and MuJoCo; defer a C++/CUDA backend until profiling and numerical comparison justify it | Actual Mac timings in `evidence/remote-runtime.json`; language decision in `ARCHITECTURE.md` |
| Find Mac Studio and 4060 resources; keep remote synchronized | The configured Mac Studio deployment runs the private service; a 4060 Laptop 8 GB was discovered through NyxID. Browser GPU renders meshes; no server GPU backend is required for this MVP | Node observations in `RESEARCH.md`, deployment configuration in `OPERATIONS.md`; latest source/build/runtime synchronization in `evidence/auth-release-check.json` |
| Prepare simple NyxID login interfaces; actual integration later | Single-button login, code + PKCE, server sessions, draft restoration and separate revocable agent tokens. Disabled until configured by the owner | `NYXID_LOGIN.md`, `.env.example`, 18 offline auth tests; all 30 tests pass locally and on Mac Studio |

Local entry: `http://127.0.0.1:8080`; API explorer: `/docs`. The public
preview exists at <https://fly.omega.gift>. Its API and simulation deployment
remain separately configured and are not evidence of production readiness.

Known limits remain visible in the product: engineered odor encoder and motor readout, simplified LIF dynamics, primitive navigation, no vision, online plasticity, natural aggression or CUDA neural backend. These do not prevent the implemented weight-design → embodied match → verdict → replay workflow. Full biological/strategic validation, production abuse protection, upstream session-revocation integration and the later ROADMAP gates are not represented as complete.
