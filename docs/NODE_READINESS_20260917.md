# Verified node readiness — 17 September 2026

Live read-only checks on 17 September, approximately 07:42–07:53 Singapore time, established access to both designated machines. The RTX 4060 is reachable through NyxID. A subsequent review of existing delivery artifacts recovered the already accepted real-device tiny CUDA validation from 16 September. Full-graph and embodied CUDA qualification remain incomplete. This updates the initial hardware observations in [RESEARCH.md](RESEARCH.md) and the deployment assumptions in [ARCHITECTURE.md](ARCHITECTURE.md).

## Observed state

| Property | Mac Studio | RTX 4060 node |
|---|---|---|
| NyxID directory | Online and dispatchable | Online and dispatchable |
| Working SSH service / principal | `macstudio-ssh` / `macstudio` | `deepevo-4060-ssh` / `root` |
| Heca | Existing remote relay reports connected | Not found in the queried Linux PATH or limited `.local/bin` paths |
| Arena service / task environment | Existing health endpoint reports `ok`, graph and readout ready, version `0.1.0` | Existing isolated CUDA task at `/tmp/fly-arena-cuda-device-v1`; no production Arena service established |
| GPU | Not re-queried in this inspection | NVIDIA GeForce RTX 4060 Laptop GPU |
| VRAM and driver | Not re-queried | 8,188 MiB total; NVIDIA driver 592.82 |
| Linux runtime | Not applicable | WSL2, kernel `6.18.33.1-microsoft-standard-WSL2`, x86_64, glibc 2.39 |
| System Python | Not re-queried | `/usr/bin/python3`, version 3.12.3 |

At the GPU query, 7,956 MiB VRAM was free and utilization was 0%. Linux reported 16,189,108 KiB total memory, 15,306,988 KiB available memory, and approximately 1.00 TB available on the filesystem containing `/tmp`. These are point-in-time readings, not a resource reservation or a throughput benchmark.

Python distribution metadata for that system interpreter contained no `torch`, `numpy`, `scipy`, `numba`, `mujoco`, or `flygym`. `uv`, `nvcc`, and `heca` were absent from its PATH. The limited path check covered `/home/*/fly-arena*`, `/root/fly-arena*`, `/opt/fly-arena*`, and `/home/*/.local/bin/heca` plus `/root/.local/bin/heca`. It did not inspect all virtual environments, containers, directories, or the Windows host. These observations do not establish that the software is absent everywhere.

The follow-up read-only check found the retained task environment at `/tmp/fly-arena-cuda-device-v1/venv/bin/python`. Its metadata matches the earlier validation: Python 3.12.3, NumPy 2.5.3, Numba 0.67.0, llvmlite 0.49.0, and NVIDIA compilation/runtime wheels 12.9.86 / 12.9.79. Reuse this isolated environment after checking its full identity; the system-interpreter observation is not a reason to reinstall it.

## Existing CUDA evidence

[PR #8](https://github.com/the-omega-institute/fly-arena/pull/8), published at `436bcad264705d4d5d5fe6bb07ed7e9ccc962f8f`, retains the [real-device report](https://github.com/the-omega-institute/fly-arena/blob/436bcad264705d4d5d5fe6bb07ed7e9ccc962f8f/docs/CUDA_DEVICE_VALIDATION.md). The executed optional ordered Numba CUDA adapter is pinned to `312a71145ef3a813ec744e06226d941b210bcbbc` on a separate source branch; it is not yet integrated into this branch's application.

The RTX 4060 executed seven four-neuron, 48-tick fixtures with exact event/counter/refractory comparisons, FP64 `atol=1e-10` / `rtol=1e-12`, and exact repeat/chunk/restore checks. The independent verifier passed normally and under `python -O`; three independent reviews approved that bounded evidence. Emitted PTX was inspected for explicit FP64 operations without floating FMA/MAD contraction. On 17 September, all 69 entries of the durable delivery manifest were rechecked for byte length and SHA-256 without rerunning the experiment.

That result is **EXECUTED / UNQUALIFIED**. Full retained-graph WT/mutant 800-tick comparisons, measured throughput and peak allocation, longer horizons, and decoder/body/scenario admission remain unperformed. The 100 additional contract tests use CPU paths and are not 100 GPU tests. Public CUDA availability remains false.

## Access diagnosis

The GPU service explicitly lists `zwlexa`, `lexa`, `ubuntu`, and `root` as allowed principals. Queries using the first three failed before remote execution with HTTP 404, `ssh_node_key_missing`, error 1011. The same fixed, read-only command succeeded using the already allowed `root` principal:

```sh
nyxid ssh exec deepevo-4060-ssh --principal root -- \
  'nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'
```

```text
NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 592.82
```

Generic service flags reported connected, no missing credentials, and no stale node keys even when individual principals failed. Use an actual operation through the selected principal to establish execution readiness. An earlier transient `Node owner replica is unavailable` response also did not establish that the GPU itself was offline. No keys, permissions, bindings, or routes were changed to obtain access.

The `deepevo-4060-local-bridge` catalog returned an empty OpenAPI endpoint list. No execution endpoint was guessed or invoked. Mac checks used the existing Heca `daemon relay-status` command and a GET of `http://127.0.0.1:8080/api/v1/health`. Local workstation Heca was not running and was not started.

## Implementation consequence

The GPU hardware-access dependency is resolved, and the optional adapter plus isolated environment already exist. The next CUDA step is the prospectively frozen full-graph WT/mutant differential experiment using that reviewed implementation. Preserve the frozen neural equations, delayed events, reset/restore semantics, and declared numerical tolerances. Measure full-graph memory and throughput on this actual 8 GiB laptop GPU rather than assuming desktop performance from the model number. Passing that stage still does not confer embodied or application admission.

The 17 September discovery and follow-up checks performed no package installation, GPU computation, simulation, deployment, service restart, or remote file write; the CUDA execution above is the separately retained 16 September experiment. These checks do not modify the registered CPU mechanical experiment or qualify its walking behavior. The Mac health response also does not establish the current deployed source revision, queue state, new phenotype behavior, or readiness to replace its existing service.
