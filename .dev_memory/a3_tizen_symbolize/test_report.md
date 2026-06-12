# A3 Test Report

## A3 Unit And Fixture Tests

```bash
pytest tests/functional/test_a3_tizen_symbolize.py tests/unit/test_a3_cross_symbolize.py -q
```

Result: 6 passed.

## A-Line Regression

```bash
pytest tests/functional/test_a1_x86_perf.py tests/functional/test_a2_binary_size.py tests/functional/test_a3_tizen_symbolize.py -q
```

Result: 7 passed, 1 skipped.  The skipped test is live x86 perf capture, gated
by `PERF_SKILL_ENABLE_LIVE_PERF=1`.

```bash
pytest tests/unit/test_a1_device_runner.py tests/unit/test_a1_capture.py tests/unit/test_a1_postprocess.py tests/unit/test_a1_build_report.py tests/unit/test_a3_cross_symbolize.py -q
```

Result: 32 passed.

## Full Suite

```bash
pytest -q
```

Result: 171 passed, 1 skipped.

## Coverage

```bash
.venv/bin/python -m pytest --cov=common --cov=skills --cov=cli --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 171 passed, 1 skipped, total coverage 82.81%.

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

- Tizen-style Capture Bundle manifest validates against `capture-bundle.schema.json`.
- CLI `analyze -> report` produces schema-valid `performance-findings.json`.
- `target.platform.os=tizen` and `target.platform.arch=aarch64`.
- Top-1 hotspot is `tizen_hot`.
- Top-1 source anchor is `src/tizen_hot.c` with confidence 0.85.
- Third-party `g_signal_emit` is attributed to owned `tizen_hot`.
- `tizen.path_mapping` contains target path, host sysroot path, debuginfo path,
  source path, and build-id.
- ssh and sdb backend smoke coverage uses fake transport executables in unit
  tests; the live-device guide covers real board validation.
