# v11 distal-foot audit entry points

Read [the frozen registration](BEHAVIOR_V11_REGISTRATION.md) and
[the complete results](BEHAVIOR_V11_RESULTS.md) before interpreting a figure.
This work adds an offline audit only. It does not change motor/neural/product
runtime behavior or admit a controller.

## Evidence map

The exclusive evidence root is `var/behavior-v11/audit-01`.

| Artifact | Purpose |
|---|---|
| `registration.json`, `registration-addendum.json` | All28 inventory, parser/measurement specification, hashes and budget. Addendum corrects a pre-outcome start-epoch/deadline clerical error; no measurement change. |
| `inputs.json`, `native.json` | Read-only raw/source/asset fingerprints, native axes/transmissions and hashed material-point vertices. |
| `implementation-seal.json` | Exact audit source/tests frozen before new audit outcomes. |
| `execution-terminal.json` | Complete/skipped cases, independent primary/retention errors, resource receipt. |
| `cases/<id>/dense/chunk-*.npz` | Only `ticks` int64 and `values` float64. A separately fsynced `.npz.json` receipt binds each accepted chunk. |
| `cases/<id>/dense/start.json` | Column widths/shapes, record order, raw trial identity and registration reference. |
| `cases/<id>/parsed.json` | Every record/leg phase cell, PEP/AEP, tie, reversal, partial and diagnostic interval. |
| `cases/<id>/paired.json` | All three records on the actual record's intervals. |
| `cases/<id>/original-bouts.json` | Every contact run; original qualification flag; missing/single/multiple sparse samples; additional dense measurements. |
| `cases/<id>/summary.json` | Source/frame validation, all-case metrics and realization/decomposition summaries. |
| `report/` | All-condition CSVs, scientific figures, aggregate facts and artifact manifest. |
| `cross-tabs.json` | Paired-reference timing, contact flag versus normal support and dense original stance cross-tabs. |
| `verification.json` | Independent re-read of every saved chunk and interval partition plus fixed explicit world-vertex checks. |
| `tests-final.xml` | 17 contract tests; no physical qualification. |

Dense column layout is fixed: link clearances(90: record×leg×5), world material
centroids(54), thorax material centroids(54), actual native velocity
contributions(54: leg×root/active/passive×xyz), positive ground normal force per
link(30), and positive ground normal force restricted to contacts with
distance<=0(6). Record order is actual, command, unit_r1; leg order is
LF,LM,LH,RF,RM,RH. No source qpos/qvel/control arrays are redundantly copied.
The raw trial path and hash manifest permit independent reconstruction.

PEP/AEP refer to posterior/anterior extremes of the tarsus5 material-point AP
trace in the thorax frame. Body-frame extreme positions distinguish foot
protraction/retraction from incidental contact chatter. This choice is also
consistent with the PEP-bounded step-extraction documentation in the installed,
hash-bound `flygym_demo/complex_terrain/preprogrammed.py`. That documentation
explains the operational definition; this audit uses the compatible
NeuroMechFly asset, never substitutes the separate FlyBody asset. Phase cells
make the prospective choice deterministic, and retained ambiguity prevents a
complex or incomplete trajectory from being called a clean gait cycle.

## Execution and review

The wrapper fixes the exact interpreter, target PYTHONPATH, disabled bytecode,
owned scratch/cache and one-thread math libraries:

```sh
sh scripts/behavior_v11.sh -m pytest tests/test_behavior_v11.py -q -p no:cacheprovider
sh scripts/behavior_v11.sh -m flyarena.experiments.realization_v11 seal
sh scripts/behavior_v11.sh -m flyarena.experiments.realization_v11 run
sh scripts/behavior_v11.sh scripts/report_behavior_v11.py
sh scripts/behavior_v11.sh scripts/verify_behavior_v11.py
sh scripts/behavior_v11.sh scripts/summarize_behavior_v11.py
```

These are the executed stages, not an instruction to overwrite this completed
run. Scientific/evidence outputs are exclusive: a second `seal`/`run` or final
receipt write must fail on existing files. Reproduction in a fresh, separately
registered directory must preserve the complete fixed inventory, formulas,
source binding and parser rather than reuse changed-source historical receipts.
Individual source functions and the explicit raw/compiled-model references also
allow read-only review without any new physical trial.

The audit modules never import the old recorder, correction runner, body builder
or motor runner. They use qpos kinematics, native Jacobians, and mj_forward only
to reconstruct a diagnostic observer. Native phase and controller state are read
from retained rows; no controller is constructed or advanced. Existing services,
identity/Chrono ports, neural policy and API qualification behavior remain intact.
