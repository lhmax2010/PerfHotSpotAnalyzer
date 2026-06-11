# A2 binary-size Review Package

## Scope

A2 adds static ELF binary-size findings to Skill A:

- `binary-size-large` from one ELF.
- `binary-size-regression` from current/baseline ELF.
- CLI `perf-hotspot-analyzer binary-size`.

Out of scope: perf live capture, ssh/sdb/Tizen transport, workflow
orchestration, B-line changes, and LLM/API calls.

## Key Files

- `skills/perf-hotspot-analyzer/scripts/binary_size.py`
- `cli/perf_hotspot_analyzer.py`
- `tests/unit/test_a2_binary_size_parser.py`
- `tests/unit/test_a2_binary_size_large.py`
- `tests/unit/test_a2_binary_size_regression.py`
- `tests/unit/test_a2_binary_size_cli.py`
- `tests/functional/test_a2_binary_size.py`
- `tests/fixtures/golden/live-perf/binary-size/`

## Behavior

- Uses `readelf -S --wide` to parse section headers.
- Considers only SHF_ALLOC sections.
- Top 5 large-section findings default to `informational`.
- Section-ratio, absolute, and user-budget large findings are actionable only
  when the current ELF path resolves to owned.
- Regression findings trigger on >= 5% or >= 1024 bytes delta.
- Regression delta direction is recorded as `increase` or `decrease`.
- Outputs pass canonical schema and semantic validation.

## Validation

```bash
pytest -q
```

Result: 159 passed, 1 skipped.

```bash
uv run --with pytest --with pytest-cov --with jsonschema pytest --cov=common --cov=skills --cov=cli --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 159 passed, 1 skipped, total coverage 81.01%.

```bash
python3 tools/check_schema_copies.py
python3 tools/check_no_llm_sdk_imports.py
bash tools/check_no_llm_sdk_imports.sh
```

Result: all passed.

## Review Checklist

- [x] Single ELF path emits `binary-size-large`.
- [x] Current/baseline path emits `binary-size-regression`.
- [x] Top-n findings default to `informational`.
- [x] Owned ratio/absolute/regression findings can be `actionable`.
- [x] Unknown/non-owned actionable defaults are downgraded.
- [x] Section bytes match `size -A` in E2E tests.
- [x] Delta calculation is correct.
- [x] No Python code imports LLM SDKs.

## Next Stage

Wait for A2 review. Do not continue to A3 until review is complete.
