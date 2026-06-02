# B3 Patch Generation Review Package

## Scope

B3 implements Skill B patch generation and full Gate/status behavior. It produces
schema-validated `patches.json`, `patch-report.md`, and run-report Gate decisions.

This stage does not apply patches, run validation commands, integrate Cline or
Compiling Agent, or touch capture/Tizen logic.

## Key Files

- `skills/perf-suggestion-patch/scripts/make_patch.py`
- `skills/perf-suggestion-patch/scripts/ingest.py`
- `cli/perf_suggestion_patch.py`
- `tests/unit/test_b3_make_patch.py`
- `.dev_memory/b3_patch_gen/*`
- `docs/test-guides/b3-patch-gen.md`

## Behavior

- `diff-ready` and `needs-review` patches contain `diff` and `chosen_anchor`.
- `chosen_anchor` is derived with `schema_validate.derive_effective_anchor`.
- `advisory-only` patches contain no `diff`.
- `measured_impact` is always null.
- `validation_status` is always `not-run`.
- `verification_plan` is recorded but not executed.
- `patch-report.md` includes one section per patch with finding, expected impact,
  side effects, apply guidance, and verification commands.

## Gate Summary

- Non-actionable, missing/low-confidence anchors, benchmark latency without budget,
  default generic-llm, risky patch categories, shared allocation ownership, and
  file-policy violations become advisory-only.
- `local-micro-optimization` can be diff-ready.
- `build-flag` can produce a diff but is needs-review due package-wide blast radius.
- local allocation reduction can be diff-ready.
- shared cache/object pool/lifetime/thread-visible allocation reductions are advisory-only.

## Validation

```bash
.venv/bin/python -m pytest -q
```

Result: 107 passed.

```bash
.venv/bin/python -m pytest tests/unit/test_b1_ingest.py tests/unit/test_b2_google_benchmark.py tests/unit/test_b2_folded_stacks.py tests/unit/test_b2_generic_llm.py tests/unit/test_b2_anchor_search.py tests/unit/test_b3_make_patch.py tests/functional/test_b1_analyzer_json.py \
  --cov=cli.perf_suggestion_patch \
  --cov=skills/perf-suggestion-patch/scripts \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

Result: 54 passed, total coverage 88.26%.

Additional guardrails:

- `.venv/bin/python tools/check_schema_copies.py` passed.
- `bash tools/check_no_llm_sdk_imports.sh` passed.

## Review Checklist

- [x] diff-ready/needs-review patches include diff and chosen_anchor.
- [x] advisory-only patches omit diff.
- [x] generated diffs pass `git apply --check` in sample repos.
- [x] file touched policy enforces allow/deny lists.
- [x] build-flag policy records package-wide blast radius.
- [x] allocation-reduction local/shared split is covered.
- [x] negative fixtures #10 and #11 remain rejected by schema_validate.
- [x] no Python code imports or calls LLM SDKs.

## Next Stage

Wait for B3 review. Do not continue to M-final until review is complete.
