# B2 Benchmark Folded Generic Test Guide

## Google Benchmark Before/After

```bash
rm -rf out/b2-gb
.venv/bin/python -m perf_suggestion_patch analyze \
  --input tests/fixtures/golden/positive/02-google-benchmark-before-after/after.json \
  --baseline-report tests/fixtures/golden/positive/02-google-benchmark-before-after/before.json \
  --format google-benchmark \
  --repo-root /repo/demo \
  --output-dir out/b2-gb
```

Expected: `run-report.json` contains one `benchmark-regression` finding.

## Google Benchmark Single Report

```bash
rm -rf out/b2-gb-single
.venv/bin/python -m perf_suggestion_patch analyze \
  --input tests/fixtures/golden/positive/03-google-benchmark-single-latency/current.json \
  --format google-benchmark \
  --repo-root /repo/demo \
  --output-dir out/b2-gb-single
```

Expected: `run-report.json` contains `benchmark-latency-without-perf-budget`.

## Folded Stacks

```bash
rm -rf out/b2-folded
.venv/bin/python -m perf_suggestion_patch analyze \
  --input tests/fixtures/golden/positive/13-capture-bundle-10-piece/out.folded \
  --format folded-stacks \
  --repo-root /repo/demo \
  --output-dir out/b2-folded
```

Expected: function-hotspot findings are advisory when no repo-root source anchor is found.

## Generic LLM Handoff

```bash
rm -rf out/b2-generic
.venv/bin/python -m perf_suggestion_patch analyze \
  --input tests/fixtures/golden/positive/05-low-confidence-generic-llm/freeform-report.txt \
  --format generic-llm \
  --repo-root /repo/demo \
  --output-dir out/b2-generic
```

Expected first run: prompt written under `out/b2-generic/prompts/`, process exits pending/fatal because `outputs/<id>-normalized.json` is not present yet.

After the host Agent writes the normalized JSON, rerun the same command. Expected: advisory-only `patches.json` and `run-report.json`.

## Tests and Guardrails

```bash
.venv/bin/python -m pytest -q
.venv/bin/python tools/check_schema_copies.py
bash tools/check_no_llm_sdk_imports.sh
```
