# RTX 4060 tiny recurrence validation

The actual RTX 4060 Laptop executed the frozen seven-fixture CUDA differential suite successfully on 2026-09-16. This supplies real device execution for the previously reviewed optional backend. Its status remains **EXECUTED / UNQUALIFIED**: full-graph 800-tick validation, throughput, peak-memory measurement and embodied behavior were not run. Public CUDA availability is unchanged.

The executed scientific source is commit `312a71145ef3a813ec744e06226d941b210bcbbc`. Seventeen selected source, fixture, policy, test and documentation files matched that commit before transfer and after execution. No kernel, scientific parameter, fixture or tolerance was changed to obtain this result. These additive receipts preserve their original source and runtime identities.

## Executed scope

The seven four-neuron cases are silence, delayed/self/inhibitory edges, ordered cancellation, exact threshold, threshold above rest, stimulus replacement, and mutant intrinsic parameters. Each has 48 per-tick oracle/candidate/repeat observations, uneven chunks and a restored suffix. Counts, refractory state, tick and total spikes must match exactly; FP64 arrays use `atol=1e-10`, `rtol=1e-12`. Same-runtime repeat, chunk and restore checks are array-exact.

The unchanged independent verifier passes both normally and under `python -O` in the recorded Linux environment. The additional 100 passing contract/evidence tests execute their CPU path with simulator mode absent. **Actual GPU recurrence coverage is the seven-fixture runner, not 100 GPU tests.** The stimulus-replacement and mutant-intrinsic fixtures remain subthreshold in this short horizon; they do not establish a spiking mutant phenotype.

## Bound runtime

| Component | Recorded value |
|---|---|
| Device | NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, compute capability 8.9 |
| Driver | 592.82; driver API 13.1 |
| Python | 3.12.3, Linux WSL2 x86_64, glibc 2.39 |
| Numerical packages | NumPy 2.5.3, Numba 0.67.0, llvmlite 0.49.0 |
| CUDA compilation/runtime wheels | NVIDIA nvcc component 12.9.86 and runtime 12.9.79; runtime API 12.9 |
| Simulator | Environment variable absent, Numba flag false; real device available |

The task used an isolated temporary environment. NVIDIA wheel components provide Numba/NVVM compilation; no system toolkit, driver or service was installed or replaced. Retained wheel digests and compiler-library identities accompany the receipts. Runtime/compiler changes require a new differential check.

Three emitted `sm_89` PTX specializations were inspected: the neuron kernel contains six `add.rn.f64` and five `mul.rn.f64` instructions; each arrival layout contains five `add.rn.f64` instructions. No floating FMA/MAD contraction was found. PTX inspection and numerical comparisons support this specific execution; they do not establish future-toolchain or SASS equivalence.

## Evidence and reproduction boundary

- [Raw per-tick evidence](evidence/cuda-device-v1/cuda-evidence.json), SHA-256 `3a29ad2f183e086359a95ccab8de6a88ee32e540b3bc7e6947ea4cac14ee060f`.
- [Source identities](evidence/cuda-device-v1/source-manifest.json), [environment](evidence/cuda-device-v1/environment-manifest.json), [wheel digests](evidence/cuda-device-v1/wheel-manifest.json) and [compiler libraries](evidence/cuda-device-v1/compilation-libraries.json).
- [Frozen execution](evidence/cuda-device-v1/frozen-execution.json), [PTX inspection](evidence/cuda-device-v1/ptx-inspection.json) and [published-file hashes](evidence/cuda-device-v1/publication-manifest.json). The three inspected PTX files are in the same evidence directory.

Use the unchanged runner and verifier at the recorded source commit, with the exact recorded environment. The verifier intentionally rejects a different runtime identity; do not rewrite receipts to make them pass on a Mac or a different Linux environment. Existing reproduction commands and the next hardware gate are documented in [optional-cuda-backend.md](optional-cuda-backend.md).

The next bounded stage must freeze digest-verified full topology, actual WT and mutant weights, intrinsic parameters, identical input schedule, 800-tick horizon, checkpoints and repeat/chunk/restore comparisons before measurement. Warm-up, synchronized timing and allocated/peak memory are separate measurements. No acceleration, full-brain equivalence, decoder compatibility, walking or competition admission follows from this tiny suite.
