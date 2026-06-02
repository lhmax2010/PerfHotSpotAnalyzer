# B1 Ingest Anchor Review Package

## Scope

B1 implements the Skill B analyzer-json path only: ingest canonical
`performance-findings.json`, validate it with `common/schema_validate.py`, derive and
score effective anchors, run the actionability/effective-anchor Gate, and emit only
advisory suggestion patches plus `run-report.json`.

This stage does not implement google-benchmark, folded-stacks, generic-llm, patch
generation, diff generation, runtime patch application, or Tizen device logic.

## Key Files

- `skills/perf-suggestion-patch/scripts/ingest.py`
- `cli/perf_suggestion_patch.py`
- `tests/unit/test_b1_ingest.py`
- `tests/functional/test_b1_analyzer_json.py`
- `.dev_memory/b1_ingest_anchor/*`
- `docs/test-guides/b1-ingest-anchor.md`

## Behavior

- Input source reports are preserved in output `patches.json` and `run-report.json`.
- `effective_anchor` is derived by `common.schema_validate.derive_effective_anchor`.
- Anchor confidence is scored by DESIGN section 6.4 rubric.
- Caller-attribution uses the B1 two-tier scoring: 0.80 for confident mapped caller attribution, 0.65 for ambiguous/manual/low evidence.
- Every emitted patch has `status=advisory-only`, `validation_status=not-run`, `measured_impact=null`, and no `diff`.
- Every finding has one `gate_decisions` entry with a reason.

## Validation

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/functional/test_b1_analyzer_json.py -q
```

Result: 27 passed.

```bash
.venv/bin/python -m pytest -q
```

Result: 80 passed.

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

Result: 27 passed, total coverage 94.94%.

Additional guardrails:

- `.venv/bin/python tools/check_schema_copies.py` passed.
- `bash tools/check_no_llm_sdk_imports.sh` passed.

## Fixture Coverage

- #01 hotspot + binary-size mixed: two advisory patches, one B1 downgrade and one missing-anchor gate.
- #06 advisory-only patch: reused as the schema contract baseline.
- #15 third-party hot frame attributed to owned caller: effective anchor uses attribution anchor.
- #16 no owned frame: gate reason `actionability=not-actionable`.
- #17 attribution preferred over code anchor: effective anchor points to `src/signal_adapter.c`.

## Review Checklist

- [x] analyzer-json adapter validates through canonical schema.
- [x] source_reports metadata is preserved.
- [x] effective_anchor derivation is delegated to schema_validate.
- [x] Gate writes one decision per finding with reason.
- [x] No B1 output contains patch `diff`.
- [x] No Python code imports or calls an LLM SDK.
- [x] B2/B3 work is not implemented.

## Next Stage

Wait for B1 review. Do not continue to B2 until review is complete.
