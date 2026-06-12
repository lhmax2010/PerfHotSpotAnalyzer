# M-integ Test Report

## M-integ Tests

```bash
pytest tests/integration/test_cline_examples.py tests/unit/test_compiling_agent_adapter.py -q
```

Result: 7 passed.

## Full Suite

```bash
pytest -q
```

Result: 183 passed, 1 skipped.

## Coverage

```bash
.venv/bin/python -m pytest --cov=common --cov=skills --cov=cli --cov=workflows --cov=integrations --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 183 passed, 1 skipped, total coverage 82.92%.

## Guardrails

```bash
python3 tools/check_no_llm_sdk_imports.py
python3 tools/check_schema_copies.py
bash tools/check_no_llm_sdk_imports.sh
```

Result: all passed.

## Integration Coverage

- Cline B-only demo script runs end-to-end and validates `patches.json`.
- Compiling Agent adapter success path parses workflow stdout artifacts.
- Compiling Agent adapter non-zero exits degrade for exit codes 1, 2, and 3.
- Compiling Agent adapter timeout degrades to exit code 124.
- `apply()` remains review-only and does not apply generated patches.
