# B1 Ingest Anchor Test Guide

## Run Skill B Analyzer-json Path

```bash
rm -rf out/b1-smoke
.venv/bin/python -m perf_suggestion_patch analyze \
  --input tests/fixtures/golden/positive/01-hotspot-binary-size-mixed/performance-findings.json \
  --output-dir out/b1-smoke
```

Expected outputs:

- `out/b1-smoke/patches.json`
- `out/b1-smoke/run-report.json`
- `out/b1-smoke/run-<trace_id>.jsonl`

Validate the generated suggestion patch:

```bash
.venv/bin/python -m perf_suggestion_patch validate \
  --input out/b1-smoke/patches.json \
  --document-type suggestion-patch
```

## Run Tests

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/functional/test_b1_analyzer_json.py -q
```

```bash
.venv/bin/python -m pytest -q
```

## Coverage

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

## Guardrails

```bash
.venv/bin/python tools/check_schema_copies.py
bash tools/check_no_llm_sdk_imports.sh
```
