# B3 Test Report

## Full Suite

```bash
.venv/bin/python -m pytest -q
```

Result: 107 passed.

## B-Line Coverage Suite

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/unit/test_b2_google_benchmark.py tests/unit/test_b2_folded_stacks.py tests/unit/test_b2_generic_llm.py tests/unit/test_b2_anchor_search.py tests/unit/test_b3_make_patch.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

Result: 54 passed, total coverage 88.26%.

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

- #07 diff-ready patch contract remains valid.
- #20 allocation-reduction local diff contract remains valid.
- #21 allocation-reduction shared advisory contract remains valid.
- Negative #10 and #11 remain rejected by schema_validate in the golden fixture suite.
- B1/B2 advisory paths remain schema-valid after B3 Gate integration.
