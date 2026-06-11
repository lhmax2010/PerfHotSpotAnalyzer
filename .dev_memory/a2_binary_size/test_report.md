# A2 Test Report

## A2 Unit + Functional

```bash
pytest tests/unit/test_a2_binary_size_parser.py tests/unit/test_a2_binary_size_large.py tests/unit/test_a2_binary_size_regression.py tests/unit/test_a2_binary_size_cli.py tests/functional/test_a2_binary_size.py -q
```

Result: 19 passed.

## Full Suite

```bash
pytest -q
```

Result: 159 passed, 1 skipped.

## Coverage

```bash
uv run --with pytest --with pytest-cov --with jsonschema pytest --cov=common --cov=skills --cov=cli --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 159 passed, 1 skipped, total coverage 81.01%.

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

- `topn.elf` emits five `binary-size-large` findings.
- All top-n findings default to `informational`.
- Section bytes match `size -A`.
- `after.elf` vs `before.elf` emits `.inflate` `binary-size-regression`.
- `.inflate` delta is 6144 bytes / 300% increase.
- Regression finding is `owned` and `actionable`.
- All outputs validate with canonical schema and semantic checks.
