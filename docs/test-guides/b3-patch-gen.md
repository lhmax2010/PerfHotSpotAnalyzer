# B3 Patch Generation Test Guide

## Run Tests

```bash
.venv/bin/python -m pytest tests/unit/test_b3_make_patch.py -q
```

```bash
.venv/bin/python -m pytest -q
```

## Coverage

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/unit/test_b2_google_benchmark.py tests/unit/test_b2_folded_stacks.py tests/unit/test_b2_generic_llm.py tests/unit/test_b2_anchor_search.py tests/unit/test_b3_make_patch.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

## CLI Smoke

Run Skill B on any canonical `performance-findings.json`:

```bash
rm -rf out/b3-smoke
.venv/bin/python -m perf_suggestion_patch analyze \
  --input tests/fixtures/golden/positive/01-hotspot-binary-size-mixed/performance-findings.json \
  --format analyzer-json \
  --output-dir out/b3-smoke
```

Expected outputs:

- `out/b3-smoke/patches.json`
- `out/b3-smoke/run-report.json`
- `out/b3-smoke/patch-report.md`

Validate the generated contract:

```bash
.venv/bin/python -m perf_suggestion_patch validate \
  --input out/b3-smoke/patches.json \
  --document-type suggestion-patch
```

## Guardrails

```bash
.venv/bin/python tools/check_schema_copies.py
bash tools/check_no_llm_sdk_imports.sh
```

Generated diffs are review suggestions only. Do not automatically apply, commit, or push them.
