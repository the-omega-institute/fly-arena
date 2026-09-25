# Operations · Genesis Alpha

The deployment target is supplied at run time through `ARENA_DEPLOY_PATH`,
`ARENA_DEPLOY_HOST`, and `ARENA_DEPLOY_PRINCIPAL`. `scripts/sync_mac.py`
fails clearly when any of these values is unset; do not commit their deployment
specific values. Confirm the configured host and path before changing them. An
isolated `.bootstrap` environment provides uv; `.venv` holds the locked
application dependencies. No GitHub account credentials are copied to the
node.

`python scripts/sync_mac.py` sends an explicit source + built-web archive through NyxID exec, checks its SHA256 remotely, then extracts it. It does not transfer raw data, credentials, user databases or node configuration. Run `npm run build --prefix web` first. The remote directory is a deployment copy, not a Git checkout; the reviewable source lives on the feature branch in GitHub.

To make a real replay visible on a source-only deployment, first create a
read-only bundle from a verified match:

```bash
python scripts/bundle_replay.py --match-id <verified-match-id>
python scripts/sync_mac.py var/research/replay-gallery-v1
```

The bundle contains the match request/result and the four browser artifacts
(`scene`, `frames`, `events`, `receipt`). The command verifies the receipt's
recorded hashes before copying anything. It deliberately excludes SQLite,
accounts, compiled artifacts and full `brain-*.npz`/`physics.npz` checkpoints.
The API lists these immutable records alongside database matches, so an empty
deployment database can still open the selected replay. Keep the bundle under
the same maintenance window as the source update; it is a read-only showcase,
not a replacement for the private research ledger.

Use a maintenance window for core updates: allow the queue to drain, stop the service, synchronize, and restart. A match admitted under an old runtime hash intentionally fails if a new runtime tries to execute it. Do not overwrite a running core and claim continuity. MVP updates are not transactional rolling releases.

Back up `var/arena.sqlite3` via SQLite's backup API, plus `var/artifacts`, `var/runs`, and the frozen `data/connectome` directory. A DB-only backup cannot restore immutable weight artifacts or replay evidence. Source data may be redownloaded, but its hashes must agree. Do not recalibrate the readout in the middle of a season. A runtime hash includes source, lockfile, Python/platform, model and rules; cross-hardware bitwise equivalence is not promised.

The server contains one queue coordinator and launches one match child process at a time. SQLite leases fence late results; expiry retries an infrastructure failure up to two attempts. A stopped coordinator lets its current child finish. On restart the coordinator reconciles expired leases. Runs preserve log files and evidence under `var/runs/<match>/<attempt>/`.

Browser viewing renders actual compiled mesh geometry with recorded MuJoCo poses. It does not need server-side OpenGL or a named GPU worker. The configured deployment host runs the full graph on CPU; optional GPU profiling remains separate, and no CUDA backend is claimed in this release.

Public hosting should terminate HTTPS in front of the loopback API. A temporary Cloudflare tunnel is suitable for this private beta demonstration, but its random URL is not a production domain or uptime guarantee. Use a configured named tunnel/domain, persistent identity, external quotas and a front-end service before broad launch. Never expose a node SSH service or local credential manager through the app tunnel.

## Running deployment

The app-only service `${ARENA_LAUNCHD_LABEL_PREFIX:-fly-arena}-app` can be installed with `python deploy/install_services.py`. Its definition lives inside the project `deploy/` directory, with logs under `var/log/`. The script defaults to **no public tunnel**. It can be inspected with `launchctl print gui/$(id -u)/${ARENA_LAUNCHD_LABEL_PREFIX:-fly-arena}-app`. The GUI login session must remain active; full machine reboot/login persistence has not been tested.

The optional `--public-tunnel` flag is staged only. Automatic approval review rejected public exposure; do not enable it until the user explicitly approves making the web app, published designs/replays and beta registration API reachable to anyone with the URL. The tunnel does not expose SSH, raw local folders or a credential manager.

Remote smoke examples are created by `scripts/remote_smoke.py`; the token stays inside the script’s environment. All five initial API runs and its AI paired series completed successfully. A copy of their receipts/results/timings is under `docs/evidence/`.

Selected bundles also include the contestants' saved FlySpecs and mutation
budgets, matched to the receipt's participant order and artifact identities.
The neural theatre and observation export prefer these snapshots over the live
fly library. The receipt's canonical ID (`source.receipt_sha256`) and the hash
of its file bytes (`source.receipt_file_sha256`) are recorded separately.
