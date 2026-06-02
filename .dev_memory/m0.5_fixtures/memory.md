# M0.5 Fixtures Memory

Status: completed locally after v1.0.6 refresh, pending review.

Branch: `stage/m0.5-fixtures`

Base: `stage/m0-schema` at `5d7f09b`. `main` did not yet contain M0 when this
stage started, and the user explicitly requested continuing with M0.5 from the
current M0 baseline.

v1.0.6 refresh: merged `main` at `160a842` into `stage/m0.5-fixtures` before
adding incremental fixtures and contract checks.

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
- Added v1.0.4-v1.0.6 incremental contract fixtures:
  - Capture Bundle manifest sample with 10 artifact files and concrete
    `perf-script.txt` content.
  - ownership.yaml template with `/usr/lib`, `/usr/lib64`, `/lib`, and `/lib64`
    patterns plus owned/third-party/system/unknown examples.
  - attribution_anchor positive and no-owned-stack not-actionable examples.
  - effective_anchor derivation example preferring attribution_anchor over
    code_anchors.
  - generic-llm default advisory-only and deterministic re-anchor Gate shapes.
  - allocation-reduction local diff and shared/cache advisory examples.
  - binary-size-large top-n informational example.
  - actionability negative fixture rejected by §6.6 rules 7/8/9.
- Added canonical schemas in `common/schemas/` and SHA-256 copy checks for skill
  schema copies.
- Added LLM SDK grep scanning script and intentional-violation test.
- Added M0.5 test guide and review package.

## Key Details

- Fixture root: `tests/fixtures/golden/`.
- Each fixture has `README.md`, `notes.md`, `expected.json`, and the document to
  validate.
- Positive benchmark fixtures include small raw Google Benchmark JSON files for
  future parser milestones, while M0.5 validates only the normalized contract
  document.
- Negative fixtures assert expected validation rule names where JSON Schema and
  semantic validation overlap.
- `schema_validate.py` now includes v1.0.6 semantic rules for actionability,
  attribution completeness, function-hotspot anchoring, and effective_anchor
  derivation. This is contract infrastructure, not A/B business logic.
- CI checks canonical schema copy SHA-256 and production LLM SDK imports.

## Tests

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/functional/test_golden_fixtures.py -q` | 23 passed |
| `.venv/bin/python -m pytest` | 53 passed |
| `.venv/bin/python tools/check_schema_copies.py` | pass |
| `bash tools/check_no_llm_sdk_imports.sh` | pass |
| `python3 -m compileall common cli perf_hotspot_analyzer perf_suggestion_patch perf_optimization_pipeline tools tests/unit tests/functional tests/security` | pass |
| `git diff --check` | pass |
| CLI capture-bundle smoke | exit 0 |
| CLI actionability negative smoke | exit 1, rejected by rules 7/8/9 |

## Next Entry

After M0.5 review and merge, A1 and B1 may start from reviewed main. A3 remains
deferred until x86 fixture mainline passes. Do not continue A/B lines before
review.
