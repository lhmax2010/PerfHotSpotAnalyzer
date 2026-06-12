# M-final Test Report

## M-final Tests

```bash
pytest tests/functional/test_mfinal_workflow.py tests/unit/test_mfinal_orchestrate.py -q
```

Result: 5 passed.

## A/B Regression Slice

```bash
pytest tests/functional/test_a1_x86_perf.py tests/functional/test_a2_binary_size.py tests/functional/test_a3_tizen_symbolize.py tests/functional/test_b1_analyzer_json.py tests/unit/test_b1_ingest.py tests/unit/test_b2_google_benchmark.py tests/unit/test_b2_folded_stacks.py tests/unit/test_b2_generic_llm.py tests/unit/test_b2_anchor_search.py tests/unit/test_b3_make_patch.py -q
```

Result: 61 passed, 1 skipped.

## Full Suite

```bash
pytest -q
```

Result: 176 passed, 1 skipped.

## Coverage

```bash
.venv/bin/python -m pytest --cov=common --cov=skills --cov=cli --cov=workflows --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 176 passed, 1 skipped, total coverage 82.78%.

## Guardrails

```bash
python3 tools/check_no_llm_sdk_imports.py
python3 tools/check_schema_copies.py
bash tools/check_no_llm_sdk_imports.sh
```

Result: all passed.

## Coverage Notes

- full mode uses the A1 x86 pre-captured bundle and runs A -> Gate 1 -> B ->
  Gate 2 -> merged report.
- b-only mode uses the M0.5 mixed performance-findings fixture.
- a-only mode uses the A3 Tizen-style pre-captured bundle.
- Non-interactive safety test verifies no `git`, `apply`, `commit`, or `push`
  command is invoked and `.git/` is untouched.
- Resume test verifies a failed B stage can rerun with the same `run_id` while
  skipping completed A stages and Gate 1.
