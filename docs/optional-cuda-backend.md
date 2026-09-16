# Optional ordered CUDA neural backend (unqualified)

This isolated increment adds an opt-in neural backend, not application wiring or a
scientific admission. The existing CPU backend, connectome, compiler, sensor,
decoder, artifacts and public backend catalog remain unchanged. Real CUDA
compilation/execution and RTX 4060 qualification are **NOT RUN/UNQUALIFIED**.
Installed Numba and a runnable CPU simulator do not establish runnable CUDA.

`flyarena.optional_backend.create_backend` accepts `cpu`, `cuda`, or the explicitly
named `cuda-simulator-diagnostic`. CUDA selection rejects an enabled simulator or
missing device; it never falls back. The simulator selection requires
`NUMBA_ENABLE_CUDASIM=1` before Python imports and caps inputs at 64 neurons and
4096 edges. The public catalog continues to report CUDA unavailable.

The protocol covers prepare/reset/stimulate/advance/neural_output/checkpoint/
restore/metrics. Construction validates and copies graph inputs and compiled FP32
weights. `prepare(binding)` checks an already constructed scientific binding and
preserves live state. Scalar, step, seed, index and checkpoint types are checked;
booleans are not integer steps/seeds. A checkpoint envelope carries eight typed
arrays plus a scientific sidecar binding topology, neuron identities, groups,
weights, intrinsic parameters, model, oracle source, and v2 sensory semantics.
Every array is staged before restore. Cross-runtime restore is intentionally
possible only for the same binding. Runtime identity is recorded separately from
scientific identity and is not a readout/motor admission.

CPU evolution delegates to the unchanged `Brain.advance`. CUDA uses a neuron
kernel followed by a destination-owned incoming-edge kernel on the same stream.
Stable destination sorting preserves the canonical source/edge accumulation order;
there are no floating-point atomics. State is FP64, weights FP32, per-call counts
and refractory state int32; tick and total spike counters are range checked for
int64 checkpoint representation. A positive advance also requires
`tick + steps - 1 + 18 <= INT64_MAX`, reserving the final delayed-arrival
index before any CPU or CUDA state mutation. Restored counters outside that
positive-advance domain remain valid checkpoints; zero steps preserves all state,
even at maximum counters. Constants are calculated on the host from the
oracle equations. Fast math is disabled and actual CUDA uses explicit
`libdevice.dadd_rn`/`dmul_rn` operations to prevent fused multiply/add contraction.
PTX and device support for these operations remain unverified here.

The exact retained recurrence includes arrival on tick 18 (tick 0 spike), 19 delay
slots, 22 skipped refractory ticks, current decay and arrivals during refractory,
current reset on spike, and replacement v2 stimulus `48 * concentration` with zero
baseline. Input group overlap preserves the existing left-then-right assignment
semantics. No graph edge is pruned, and timestep/model constants are unchanged.

## Reproduce the bounded diagnostics

Use the existing environment; no dependency installation is needed. Set the cache
outside any shared environment. From the isolated checkout:

```sh
export PYTHONPATH=src
export NUMBA_CACHE_DIR=/tmp/fly-arena-cuda-v1/.numba-cache
.venv/bin/python -m pytest tests/test_optional_backend.py tests/test_cuda_evidence.py -q
.venv/bin/python scripts/run_cuda_differential.py --backend cpu --output var/cuda-contract-fix-v1/cpu.json
.venv/bin/python scripts/verify_cuda_differential.py var/cuda-contract-fix-v1/cpu.json
NUMBA_ENABLE_CUDASIM=1 .venv/bin/python -m pytest tests/test_optional_backend.py -q
NUMBA_ENABLE_CUDASIM=1 .venv/bin/python scripts/run_cuda_differential.py --backend cuda-simulator-diagnostic --output var/cuda-contract-fix-v1/simulator.json
.venv/bin/python scripts/verify_cuda_differential.py var/cuda-contract-fix-v1/simulator.json
.venv/bin/python -O scripts/verify_cuda_differential.py var/cuda-contract-fix-v1/cpu.json
.venv/bin/python -O scripts/verify_cuda_differential.py var/cuda-contract-fix-v1/simulator.json
```

The frozen fixture/policy files precede measurements. Seven four-neuron fixtures
cover silence, delayed self/excitatory and inhibitory edges, catastrophic
cancellation sensitive to accumulation order, exact and adjacent thresholds,
stimulus replacement, and mutant intrinsic parameters. Each records 48 per-tick
observations, a repeat, uneven chunks, and a restored suffix. The independent
verifier reruns the unchanged CPU oracle, checks analytical timing expectations,
checks all raw state arrays and counts, and checks source/policy/scientific/runtime
identities. Events/counters/refractory are exact; FP64 comparison uses atol 1e-10
and rtol 1e-12. Same-runtime repeat/chunk/restore is array-exact. It rejects
corrupted observations, provenance, policy, omitted fixtures and claimed hardware
qualification; a self-reported pass boolean is never authority. Identity,
completeness, type and analytical checks raise explicit validation exceptions,
including under `python -O` or `PYTHONOPTIMIZE=1`; numerical comparisons remain
explicit NumPy testing calls. Optimized subprocess regressions exercise valid
evidence, malformed evidence and independent analytical rejection. Verification
requires the recorded Python/package/platform environment; raw JSON is diagnostic
evidence, not a signed attestation of physical hardware.

The bounded contract fix preserves the original `var/cuda-diagnostic/` evidence
unchanged. Its pre-fix source/evidence archive and file hashes are
`var/cuda-contract-fix-v1/pre-fix-source-and-evidence.tar.gz` and
`pre-fix-identities.json`. Revised CPU/simulator runs and their identities live
under `var/cuda-contract-fix-v1/`; old source-bound receipts do not validate the
revised source. The recurrence, fixtures, acceptance policy, schema and runtime
family IDs are unchanged; source hashes identify the contract revision. Use a
fresh output directory for subsequent revisions rather than overwriting evidence.

A real CUDA run is labelled `EXECUTED/UNQUALIFIED` by the runner and still cannot
qualify itself. Current CPU and simulator artifacts are `NOT RUN/UNQUALIFIED`.
Wall-clock diagnostic duration includes orchestration, oracle and repeat work;
it is not a GPU throughput measurement.

## Deferred physical RTX 4060 gate

1. Pin source, policy, Python/NumPy/Numba/CUDA driver/toolkit, actual device UUID,
   compute capability, and graph/compiled WT and mutant weight identities. Ensure
   simulator mode is absent. Verify real device availability and compiled kernels.
2. Run the frozen tiny suite with `--backend cuda` and the independent verifier on
   the recorded runtime. Inspect generated PTX for the intended FP64 rounding and
   absence of FMA contraction. Any event/order mismatch blocks further admission.
3. Only then load digest-verified full graph and frozen WT plus one compiled mutant.
   Use their bound parameters and identical v2 input schedule, with an 800-tick
   horizon fixed before measurement. Compare CPU/device counts and every state
   array, including checkpoints; repeat, chunk and restore independently. Never
   execute a full graph in the simulator. Archive input and raw observation hashes.
4. Measure warm-up separately. Use device synchronization around bounded timing,
   capture actual allocated/peak memory, and compare identical CPU work. Record
   failure or lack of acceleration honestly. This implementation scans all incoming
   edges every tick and launches two kernels each tick; no speedup is assumed.
5. Longer horizons, decoder behavior, sensorimotor embodiment and scenario admission
   require separate evidence and review. Existing readout/motor admission cannot
   be inherited by a new runtime.

Static device-array storage is `204*N + 8*E + 8` bytes: 23 FP64 state vectors,
three int32 vectors (refractory/events/counts), incoming int64 pointers, int32
sources and FP32 weights. The retained manifest has N=165122, E=25563197, giving
238190472 bytes (227.156 MiB). This is **not measured peak memory**: it excludes
CUDA context/JIT/allocator overhead, transfer staging, transient restore copies,
and all host graph copies/sort buffers. No full graph allocation or GPU timing
was performed.

Remaining full-goal gaps include physical CUDA qualification, embodied
approach/retention, richer research scenarios, WT/official/user provenance and
Chrono integration. This backend increment makes no claim to solve those gaps.
