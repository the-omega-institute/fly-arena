# FIX2 report-consistency correction

The user explicitly authorized this additional bounded source correction after the FIX1 correction reviews: architecture approved; quality and tests rejected the same remaining report-consistency gap (`FIX1-Q-ADMISSION`, `FIX1-T2-remaining`). The FIX1 archive remains frozen. This work changes the added admission boundary and source fixtures/receipts only; it grants no scientific execution or author review approval. `ready=false`; `full_goal_complete=false`.

`checked_report` now rejects an active candidate or comparator report when `primary.invalid_interior_phase_episodes > 0` while both `primary.recovery_passed` and `primary.support_slip_passed` remain true. The original immutable metric already makes an invalid swing or stance episode fail at least its corresponding gate. A report that claims both gates passed therefore contradicts its retained primary evidence.

A coherent report with either original physical gate false remains readable and failed. Such a candidate blocks panel admission. An ordinary comparator physical failure does not independently veto otherwise valid candidate admission. Zero-invalid-episode full panels still pass the existing complete identity, verification, retention, original/realized gate and dose checks.

The exact two-line consistency guard is the only runtime implementation change. All 195 accepted files, original metric algorithms, controller laws, thresholds, physical/call limits and fixed schedule remain unchanged.

Targeted validation uses the original interpreter, one numeric thread, disabled bytecode/plugin autoload and the existing scientific import/call/read guards:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python \
  tests/contact_mechanics_v1/run_fix2_fixtures.py
```

The guarded run passed all 14 tests: five focused FIX2 tests and nine selected existing regressions. The focused tests cover the exact candidate and comparator contradictions, a valid full panel, and both choices of one failed original physical gate for each profile. The selected regressions retain lawful and illegal hold behavior, the accepted compound release, incomplete-candidate rejection, comparator evidence checks, emergency-prefix retention, missing panel IDs and dose rejection. The earlier broad 77-test suite was not rerun because the correction affects only report consistency.

`fix2-fixture-report.json` and `fix2-fixtures.txt` contain the current targeted receipt. The earlier `fixture-report.json`, `source-flight-report.json` and `FIX1.md` remain historical FIX1 records. `fix2-source-flight-report.json` records this correction's exact changed-source hashes and immutable-source comparison; the refreshed `source-closure.json` binds the current payloads. The leaf table was regenerated only to refresh changed verifier source hashes/call-site line references; its 55 categories, 33 source files and every call capacity are unchanged.

Full independent architecture, quality and tests FIX2 reviews remain required. Actual native compatibility, mechanical gait, native restoration, downstream causal phenotypes and the complete Fly Arena user goal remain unmeasured or incomplete.
