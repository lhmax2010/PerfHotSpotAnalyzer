# M0.5 Fixtures Memory

Status: completed locally, pending review.

Branch: `stage/m0.5-fixtures`

Base: `stage/m0-schema` at `5d7f09b`. `main` did not yet contain M0 when this
stage started, and the user explicitly requested continuing with M0.5 from the
current M0 baseline.

## Completed

- Added DESIGN §10.4 golden fixtures:
  - Positive ① hotspot + binary-size mixed
  - Positive ② Google Benchmark before/after
  - Positive ③ Google Benchmark single report latency
  - Positive ④ binary-size-regression
  - Positive ⑤ low-confidence generic-llm
  - Positive ⑥ advisory-only patch
  - Positive ⑦ diff-ready patch
  - Negative ⑧ binary-size-regression missing baseline
  - Negative ⑨ benchmark-regression missing `comparison.baseline_report`
  - Negative ⑩ advisory-only with diff
  - Negative ⑪ diff-ready missing `chosen_anchor`
  - Negative ⑫ binary-size-large missing threshold
- Added `tests/functional/test_golden_fixtures.py` to validate every fixture via
  `common/schema_validate.py`.
- Added M0.5 test guide and review package.

## Key Details

- Fixture root: `tests/fixtures/golden/`.
- Each fixture has `README.md`, `notes.md`, `expected.json`, and the document to
  validate.
- Positive benchmark fixtures include small raw Google Benchmark JSON files for
  future parser milestones, while M0.5 validates only the normalized contract
  document.
- Negative fixtures assert expected validation rule names where M0 schema
  validation and semantic validation overlap.
- No schema or runtime business logic was changed.

## Tests

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/functional/test_golden_fixtures.py -q` | 12 passed |
| `.venv/bin/python -m pytest` | 32 passed |
| `python3 -m compileall tests/functional common cli perf_hotspot_analyzer perf_suggestion_patch perf_optimization_pipeline` | pass |
| `git diff --check` | pass |
| CLI positive fixture smoke | exit 0 |
| CLI negative fixture smoke | exit 1, rejected missing threshold |

## Next Entry

After M0.5 review and merge, A1 and B1 may start from reviewed main. A3 remains
deferred until x86 fixture mainline passes.
