# Contact v8 presentation correction r3

Latest display entrypoint: [`viewer-r3.html`](../var/presentation-correction-v8/viewer-r3.html).
This supersedes only the display in `var/contact-v8/viewer-r2.html`.
The original r0/r1/r2 reporters, registration, figures, derived reports and
scientific evidence remain immutable. See
[`correction-manifest.json`](../var/presentation-correction-v8/correction-manifest.json)
for original/new hashes, exact replacements, payload equality and provenance;
[`validation.json`](../var/presentation-correction-v8/validation.json) records checks.
The final [`hash-manifest.json`](../var/presentation-correction-v8/hash-manifest.json)
binds the current helper, validation harness, portability hook, documentation and
all correction outputs. The generation manifest retains source hashes as they
were when the viewer was written. Subsequent harness-only assertion and
documentation changes are recorded in validation, with initial bytes preserved
under `generation-sources/`; the generated viewer was not rewritten.

`python3 scripts/report_contact_v8_r3.py` makes a one-pass checked transformation
of the hash-pinned original viewer, writing a new directory exclusively. It does
not run scientific reporting, simulation, metric reduction or figure generation.
Every replacement must have exactly one matching anchor outside the embedded
payload. The payload is copied verbatim and checked byte-for-byte afterward.
Existing output directories cause refusal rather than overwrite.

The current chart shows 100 zero-order-held engineered voltage-equivalent input
intervals, in mV. Interval k uses recorded `current[k+1]` over
`input_time[k]` to `time[k+1]`. Contrasts subtract the two recorded currents on
identical checked clocks. Each interval is a separate horizontal SVG segment;
there is no sloping interpolation, fabricated final sample or array mutation.
The other endpoint plots retain their 101 samples. WT RF state 42 neutral input
first reaches 48 mV at 0.21 s; its first differential spike endpoint is 0.22 s.

The paired-subject phenotype heading explicitly states **neutral odor (.55,.55),
both states, independent of selected plot context**. It stays neutral when OFF
is selected. Official/submitted OFF remains NOT RUN; no OFF A/B/C inference is
supported. The unaffected original neutral scientific PNG is linked and hashed,
without rerendering.

The minimal `tests/conftest.py` collection hook marks only
`test_contact_v8.py::test_authoritative_binary_loader_rest_only` as an explicit
resource SKIP when the entire `var/contact-v8/inputs` path is absent. Its frozen
test source is unchanged. Existing empty/partial/corrupt paths, files, broken
symlinks and permission failures are not resource skips. A source-only checkout
therefore has 8 passing contract tests and 1 resource skip; with the archive,
all 9 tests run. These are different coverage levels. A skip is not physical
validation, scientific admission or a lowered safety/science gate. The 4
architecture tests remain unchanged and run in either checkout.

`node scripts/validate_contact_v8_r3.cjs` executes the actual generated JavaScript
with a minimal DOM, inspecting every valid selector combination and actual SVG
segments. It is a JavaScript/SVG validation harness, **not browser visual QA**.
Python caches and test outputs should be redirected outside the evidence tree:

```sh
PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/fly-v8-presentation-fix/cache/numba MPLCONFIGDIR=/tmp/fly-v8-presentation-fix/cache/matplotlib XDG_CACHE_HOME=/tmp/fly-v8-presentation-fix/cache PYTHONPATH=src /Users/lexa/Desktop/lexa/omega/fly-arena/.venv/bin/python -m pytest -p no:cacheprovider tests/test_contact_v8.py tests/test_architecture.py -ra
```

No scientific deviations, new conditions, changed thresholds or new physical/
neural runs are introduced. Browser/device/remote QA, free walking, bilateral
foreleg qualification, historical gates and the broader Fly Arena goal remain
unmet or outside this bounded correction.
