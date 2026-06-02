# B2 Benchmark Folded Generic Review Package

## Scope

B2 extends Skill B ingest beyond analyzer-json:

- Google Benchmark single and before/after reports.
- Folded stack aggregation.
- Generic free-form report handoff through prompt/output files.
- Deterministic repo-root anchor search for symbols and benchmark names.

This stage still emits advisory-only suggestion patches. It does not implement B3 patch generation, diffs, validation execution, capture/preflight, DeviceRunner, or Tizen logic.

## Key Files

- `skills/perf-suggestion-patch/scripts/ingest.py`
- `cli/perf_suggestion_patch.py`
- `tests/unit/test_b2_google_benchmark.py`
- `tests/unit/test_b2_folded_stacks.py`
- `tests/unit/test_b2_generic_llm.py`
- `tests/unit/test_b2_anchor_search.py`
- `docs/DESIGN.md`
- `.dev_memory/b2_benchmark_folded/*`

## Behavior

- GB with `--baseline-report` emits `benchmark-regression` with baseline and delta.
- GB without baseline emits `benchmark-latency` and Gate records no-perf-budget advisory.
- Folded stacks aggregate leaf symbols into `function-hotspot` findings.
- Generic input writes `prompts/<id>-normalize.prompt.md` and waits for `outputs/<id>-normalized.json`.
- No Python code imports or calls LLM SDKs.
- Repo-root anchor search records rubric-scored anchors:
  - `ctags` 0.75
  - `compile-db` 0.75
  - `grep` 0.65
  - `bench-name-map` 0.50

## Validation

```bash
.venv/bin/python -m pytest -q
```

Result: 99 passed.

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/unit/test_b2_google_benchmark.py tests/unit/test_b2_folded_stacks.py tests/unit/test_b2_generic_llm.py tests/unit/test_b2_anchor_search.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

Result: 46 passed, total coverage 87.87%.

Additional guardrails:

- `.venv/bin/python tools/check_schema_copies.py` passed.
- `bash tools/check_no_llm_sdk_imports.sh` passed.

## Fixture Coverage

- #02 Google Benchmark before/after.
- #03 Google Benchmark single latency.
- #05 generic-llm freeform report handoff.
- #18 generic-llm default advisory output contract.
- #19 generic-llm deterministic-anchor output contract.

## Review Checklist

- [x] GB baseline path produces `benchmark-regression`.
- [x] GB no-baseline path produces `benchmark-latency`.
- [x] Folded stacks produce function-hotspot findings and degrade without anchors.
- [x] Generic handoff writes prompt and waits for host output.
- [x] No LLM SDK import is present.
- [x] Run report contains source reports and gate decisions.
- [x] B3 patch generation is not implemented.

## Next Stage

Wait for B2 review. Do not continue to B3 until review is complete.
