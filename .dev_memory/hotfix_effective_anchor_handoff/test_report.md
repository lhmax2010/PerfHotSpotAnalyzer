# Hotfix Effective Anchor Handoff Test Report

## Targeted

- `pytest tests/unit/test_a1_build_report.py tests/unit/test_b1_ingest.py tests/unit/test_b3_make_patch.py -q`:
  35 passed.

## CI Parity

- `python3 tools/check_no_llm_sdk_imports.py`: passed.
- `bash tools/check_no_llm_sdk_imports.sh`: passed.
- `python3 tools/check_schema_copies.py`: passed.
- `python3 -m pytest tests/unit`: 164 passed.
- `python3 -m pytest tests/functional tests/security`: 47 passed, 1 skipped.

## Coverage

```bash
.venv/bin/python -m pytest tests/unit tests/functional tests/security tests/integration \
  --cov=common --cov=skills --cov=cli --cov=workflows --cov=integrations \
  --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 212 passed, 1 skipped, total coverage 83.03%.

