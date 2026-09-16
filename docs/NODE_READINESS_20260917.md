# Verified node readiness — 17 September 2026

Live read-only checks on 17 September, approximately 07:42–07:53 Singapore time, established access to both designated machines. The RTX 4060 is reachable through NyxID. Its simulation environment and CUDA backend have not been qualified. This updates the initial hardware observations in [RESEARCH.md](RESEARCH.md) and the deployment assumptions in [ARCHITECTURE.md](ARCHITECTURE.md).

## Observed state

| Property | Mac Studio | RTX 4060 node |
|---|---|---|
| NyxID directory | Online and dispatchable | Online and dispatchable |
| Working SSH service / principal | `macstudio-ssh` / `macstudio` | `deepevo-4060-ssh` / `root` |
| Heca | Existing remote relay reports connected | Not found in the queried Linux PATH or limited `.local/bin` paths |
| Arena service | Existing health endpoint reports `ok`, graph and readout ready, version `0.1.0` | No Arena directory in the limited task paths queried |
| GPU | Not re-queried in this inspection | NVIDIA GeForce RTX 4060 Laptop GPU |
| VRAM and driver | Not re-queried | 8,188 MiB total; NVIDIA driver 592.82 |
| Linux runtime | Not applicable | WSL2, kernel `6.18.33.1-microsoft-standard-WSL2`, x86_64, glibc 2.39 |
| System Python | Not re-queried | `/usr/bin/python3`, version 3.12.3 |

At the GPU query, 7,956 MiB VRAM was free and utilization was 0%. Linux reported 16,189,108 KiB total memory, 15,306,988 KiB available memory, and approximately 1.00 TB available on the filesystem containing `/tmp`. These are point-in-time readings, not a resource reservation or a throughput benchmark.

Python distribution metadata for that system interpreter contained no `torch`, `numpy`, `scipy`, `numba`, `mujoco`, or `flygym`. `uv`, `nvcc`, and `heca` were absent from its PATH. The limited path check covered `/home/*/fly-arena*`, `/root/fly-arena*`, `/opt/fly-arena*`, and `/home/*/.local/bin/heca` plus `/root/.local/bin/heca`. It did not inspect all virtual environments, containers, directories, or the Windows host. These observations do not establish that the software is absent everywhere.

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

The GPU hardware-access dependency is resolved. Later CUDA work still requires an isolated versioned environment, a real Arena backend adapter, and differential checks against the CPU reference before capability admission. Preserve the frozen neural equations, delayed events, reset/restore semantics, and declared numerical tolerances. Measure full-graph memory and throughput on this actual 8 GiB laptop GPU rather than assuming desktop performance from the model number.

These checks performed no package installation, GPU computation, simulation, deployment, service restart, or remote file write. They do not modify the registered CPU mechanical experiment or qualify its walking behavior. The Mac health response also does not establish the current deployed source revision, queue state, new phenotype behavior, or readiness to replace its existing service.
