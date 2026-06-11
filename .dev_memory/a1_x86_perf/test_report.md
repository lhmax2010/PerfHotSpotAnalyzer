# A1 Test Report

## A1 Unit Tests

```bash
pytest tests/unit/test_a1_device_runner.py tests/unit/test_a1_preflight.py tests/unit/test_a1_capture.py tests/unit/test_a1_postprocess.py tests/unit/test_a1_build_report.py -q
```

Result: 30 passed.

## A1 Unit + Functional Chain

```bash
pytest tests/unit/test_a1_device_runner.py tests/unit/test_a1_preflight.py tests/unit/test_a1_capture.py tests/unit/test_a1_postprocess.py tests/unit/test_a1_build_report.py tests/functional/test_a1_x86_perf.py -q
```

Result: 33 passed, 1 skipped.  The skipped test is live perf capture, gated by
`PERF_SKILL_ENABLE_LIVE_PERF=1`.

## Full Suite

```bash
pytest -q
```

Result: 140 passed, 1 skipped.

## Coverage

```bash
uv run --with pytest --with pytest-cov --with jsonschema pytest --cov=common --cov=skills --cov=cli --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 140 passed, 1 skipped, total coverage 80.09%.

## Guardrails

```bash
python3 tools/check_schema_copies.py
```

Result: passed.

```bash
python3 tools/check_no_llm_sdk_imports.py
```

Result: passed.

```bash
bash tools/check_no_llm_sdk_imports.sh
```

Result: passed.

## Fixture Coverage

- Pre-captured x86 fixture validates against `capture-bundle.schema.json`.
- CLI `analyze -> report` produces schema-valid `performance-findings.json`.
- Top-1 hotspot is `busy_loop`.
- `callgraph_mode=fp` and `run_context.cpu_governor=performance` are preserved.
- Ownership paths cover owned, third-party, system, and unknown.
- Third-party hotspot with owned caller produces `attribution_anchor`.
- System hotspot without owned frame is `not-actionable`.
- Unknown hotspot is `informational`.
