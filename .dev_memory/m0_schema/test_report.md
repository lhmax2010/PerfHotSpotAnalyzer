# M0 Test Report

Date: 2026-05-25

## Environment

- Host path: `/home/linhao/Toolchain/development/PerfHotsptAnalyzer`
- Python: 3.12.3
- Test runner: pytest 9.0.3 in `.venv` created by `uv`
- `python` command was not present; commands used `python3` / `.venv/bin/python`.

## Commands

```bash
python3 -m compileall common cli perf_hotspot_analyzer perf_suggestion_patch perf_optimization_pipeline tests/unit
```

Result: pass.

```bash
cmp -s skills/perf-hotspot-analyzer/schemas/performance-findings.schema.json \
  skills/perf-suggestion-patch/schemas/performance-findings.schema.json
```

Result: pass.

```bash
.venv/bin/python -m pytest tests/unit
```

Result: 20 passed.

```bash
.venv/bin/python -m pytest
```

Result: 20 passed.

```bash
.venv/bin/python -m perf_hotspot_analyzer validate --input /tmp/m0_perf.json --output-dir /tmp/m0_cli_a
.venv/bin/python -m perf_suggestion_patch validate --input /tmp/m0_patch.json --output-dir /tmp/m0_cli_b
.venv/bin/python -m perf_optimization_pipeline validate --document-type performance-findings --input /tmp/m0_perf.json --output-dir /tmp/m0_cli_pipeline
```

Result: all returned exit code 0 and emitted trace/run-report files.

## Coverage Matrix

| Requirement | Test |
| --- | --- |
| §6.2 `function-hotspot` conditions | `test_function_hotspot_requires_*` |
| §6.2 `binary-size-large` threshold | `test_binary_size_large_requires_threshold` |
| §6.2 `binary-size-regression` baseline/delta | `test_binary_size_regression_requires_baseline_and_delta` |
| §6.2 `benchmark-regression` baseline report | `test_benchmark_regression_requires_comparison_baseline_report` |
| §6.2 `benchmark-latency` metric/value | `test_benchmark_latency_requires_latency_metric` |
| §6.3 per-status patch rules | `test_per_status_*` |
| §6.6 rule 1 | `test_rule_1_confidence_upper_bound_positive_and_negative` |
| §6.6 rule 2 | `test_rule_2_report_types_consistency_positive_and_negative` |
| §6.6 rule 3 | `test_rule_3_per_status_consistency_positive_and_negative` |
| §6.6 rule 4 | `test_rule_4_v1_invariants_positive_and_negative` |
| §6.6 rule 5 | `test_rule_5_source_ref_validity_positive_and_negative` |
| §6.6 rule 6 | `test_rule_6_benchmark_regression_baseline_positive_and_negative` |
| A/B schema identity | `test_skill_performance_schemas_are_identical` |
| Skill import independence | `test_skills_do_not_import_each_other` |
