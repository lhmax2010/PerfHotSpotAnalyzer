# B2 Test Report

## Tests

```bash
.venv/bin/python -m pytest -q
```

Result: 99 passed.

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/unit/test_b2_google_benchmark.py tests/unit/test_b2_folded_stacks.py tests/unit/test_b2_generic_llm.py tests/unit/test_b2_anchor_search.py tests/functional/test_b1_analyzer_json.py -q
```

Result: 46 passed.

## Coverage

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/unit/test_b2_google_benchmark.py tests/unit/test_b2_folded_stacks.py tests/unit/test_b2_generic_llm.py tests/unit/test_b2_anchor_search.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

Result: 46 passed, total coverage 87.87%.

## Guardrails

```bash
.venv/bin/python tools/check_schema_copies.py
```

Result: passed.

```bash
bash tools/check_no_llm_sdk_imports.sh
```

Result: passed.
