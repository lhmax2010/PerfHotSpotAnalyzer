# B1 Test Report

## Unit and Functional Tests

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/functional/test_b1_analyzer_json.py -q
```

Result: 27 passed.

```bash
.venv/bin/python -m pytest -q
```

Result: 80 passed.

## Coverage

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

Result: 27 passed, total coverage 94.94%.

## Guardrails

```bash
.venv/bin/python tools/check_schema_copies.py
```

Result: passed.

```bash
bash tools/check_no_llm_sdk_imports.sh
```

Result: passed.

## Fixture Coverage

B1 end-to-end tests cover M0.5 fixtures #01, #15, #16, and #17 as analyzer-json inputs.
Fixture #06 is reused as the advisory-only suggestion-patch contract baseline.
