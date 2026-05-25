# M0.5 Test Report

Date: 2026-05-25

## Environment

- Host path: `/home/linhao/Toolchain/development/PerfHotsptAnalyzer`
- Branch: `stage/m0.5-fixtures`
- Python: 3.12.3
- Test runner: pytest 9.0.3 in `.venv`

## Commands

```bash
.venv/bin/python -m pytest tests/functional/test_golden_fixtures.py -q
```

Result: 12 passed.

```bash
.venv/bin/python -m pytest
```

Result: 32 passed.

```bash
python3 -m compileall tests/functional common cli perf_hotspot_analyzer perf_suggestion_patch perf_optimization_pipeline
```

Result: pass.

```bash
git diff --check
```

Result: pass.

```bash
.venv/bin/python -m perf_hotspot_analyzer validate \
  --input tests/fixtures/golden/positive/01-hotspot-binary-size-mixed/performance-findings.json \
  --output-dir /tmp/m05_cli_positive
```

Result: exit 0 with trace and run report.

```bash
.venv/bin/python -m perf_hotspot_analyzer validate \
  --input tests/fixtures/golden/negative/12-binary-size-large-missing-threshold/performance-findings.json \
  --output-dir /tmp/m05_cli_negative
```

Result: exit 1; rejected with `json-schema at $.findings[0].evidence:
'threshold' is a required property`.

## Fixture Matrix

| Fixture | Expected | Result |
| --- | --- | --- |
| positive/01-hotspot-binary-size-mixed | pass | pass |
| positive/02-google-benchmark-before-after | pass | pass |
| positive/03-google-benchmark-single-latency | pass | pass |
| positive/04-binary-size-regression | pass | pass |
| positive/05-low-confidence-generic-llm | pass | pass |
| positive/06-advisory-only-patch | pass | pass |
| positive/07-diff-ready-patch | pass | pass |
| negative/08-binary-size-regression-missing-baseline | reject | reject |
| negative/09-benchmark-regression-missing-comparison-baseline | reject | reject |
| negative/10-advisory-only-with-diff | reject | reject |
| negative/11-diff-ready-missing-chosen-anchor | reject | reject |
| negative/12-binary-size-large-missing-threshold | reject | reject |
