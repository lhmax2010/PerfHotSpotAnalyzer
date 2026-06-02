# M0.5 Test Report

Date: 2026-06-02

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

Updated after v1.0.6 expansion:

```bash
.venv/bin/python -m pytest tests/functional/test_golden_fixtures.py -q
```

Result: 23 passed.

```bash
.venv/bin/python -m pytest
```

Result: 32 passed.

Updated after v1.0.6 expansion:

```bash
.venv/bin/python -m pytest
```

Result: 53 passed.

```bash
.venv/bin/python tools/check_schema_copies.py
```

Result: pass. Canonical SHA-256 values:

- `performance-findings.schema.json`: `afe4c16209b7e20eaee442bc16d4eaff9c2be449950780d9e7683778d36cb037`
- `suggestion-patch.schema.json`: `7739cfe1e50cfa391480a9c70627a6b35e04cdaea8e65198c783bd08b6b8a7c6`

```bash
bash tools/check_no_llm_sdk_imports.sh
```

Result: pass.

```bash
python3 -m compileall tests/functional common cli perf_hotspot_analyzer perf_suggestion_patch perf_optimization_pipeline
```

Result: pass.

Updated compileall command included `tools` and `tests/security`; result: pass.

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

```bash
.venv/bin/python -m perf_hotspot_analyzer validate \
  --document-type capture-bundle \
  --input tests/fixtures/golden/positive/13-capture-bundle-10-piece/manifest.json \
  --output-dir /tmp/m05_v106_bundle
```

Result: exit 0 with trace and run report.

```bash
.venv/bin/python -m perf_hotspot_analyzer validate \
  --input tests/fixtures/golden/negative/23-actionable-third-party-missing-attribution/performance-findings.json \
  --output-dir /tmp/m05_v106_negative
```

Result: exit 1; rejected by `actionability-consistency`,
`attribution-completeness`, and `function-hotspot-anchoring`.

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
| positive/13-capture-bundle-10-piece | pass | pass |
| positive/14-ownership-profile | pass | pass |
| positive/15-attribution-third-party-owned | pass | pass |
| positive/16-attribution-no-owned-not-actionable | pass | pass |
| positive/17-effective-anchor-prefers-attribution | pass | pass |
| positive/18-generic-llm-default-advisory | pass | pass |
| positive/19-generic-llm-deterministic-anchor | pass | pass |
| positive/20-allocation-reduction-local-diff | pass | pass |
| positive/21-allocation-reduction-shared-advisory | pass | pass |
| positive/22-binary-size-top-n-informational | pass | pass |
| negative/23-actionable-third-party-missing-attribution | reject | reject |
