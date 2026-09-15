# Operations · Genesis Alpha

The deployment lives in `/Users/macstudio/fly-arena-mvp` on `macstudio-ssh` (NyxID principal `macstudio`). Confirm the host and paths before changing them. An isolated `.bootstrap` environment provides uv; `.venv` holds the locked application dependencies. No GitHub account credentials are copied to the node.

`python scripts/sync_mac.py` sends an explicit source + built-web archive through NyxID exec, checks its SHA256 remotely, then extracts it. It does not transfer raw data, credentials, user databases or node configuration. Run `npm run build --prefix web` first. The remote directory is a deployment copy, not a Git checkout; the reviewable source lives on the feature branch in GitHub.

Use a maintenance window for core updates: allow the queue to drain, stop the service, synchronize, and restart. A match admitted under an old runtime hash intentionally fails if a new runtime tries to execute it. Do not overwrite a running core and claim continuity. MVP updates are not transactional rolling releases.

Back up `var/arena.sqlite3` via SQLite's backup API, plus `var/artifacts`, `var/runs`, and the frozen `data/connectome` directory. A DB-only backup cannot restore immutable weight artifacts or replay evidence. Source data may be redownloaded, but its hashes must agree. Do not recalibrate the readout in the middle of a season. A runtime hash includes source, lockfile, Python/platform, model and rules; cross-hardware bitwise equivalence is not promised.

The server contains one queue coordinator and launches one match child process at a time. SQLite leases fence late results; expiry retries an infrastructure failure up to two attempts. A stopped coordinator lets its current child finish. On restart the coordinator reconciles expired leases. Runs preserve log files and evidence under `var/runs/<match>/<attempt>/`.

Browser viewing renders actual compiled mesh geometry with recorded MuJoCo poses. It does not need server-side OpenGL or the RTX 4060. The Mac Studio runs the full graph on CPU. The RTX 4060 Laptop GPU (8 GB) is available for subsequent GPU profiling; no CUDA backend is claimed in this release.

Public hosting should terminate HTTPS in front of the loopback API. A temporary Cloudflare tunnel is suitable for this private beta demonstration, but its random URL is not a production domain or uptime guarantee. Use a configured named tunnel/domain, persistent identity, external quotas and a front-end service before broad launch. Never expose a node SSH service or local credential manager through the app tunnel.
