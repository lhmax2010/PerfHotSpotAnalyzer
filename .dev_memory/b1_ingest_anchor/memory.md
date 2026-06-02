# B1 Ingest Anchor Memory

## Scope Completed

- Implemented the Skill B analyzer-json adapter in `skills/perf-suggestion-patch/scripts/ingest.py`.
- Validates input `performance-findings.json` with canonical `common/schema_validate.py`.
- Preserves `source_reports` metadata, including `source_format`, `parser`, and `confidence`.
- Derives `effective_anchor` by calling `common.schema_validate.derive_effective_anchor`.
- Scores anchor confidence with the DESIGN section 6.4 rubric, including caller-attribution tiers at 0.80 and 0.65.
- Applies the B1 actionability/effective-anchor gate and emits advisory-only suggestion patches.
- Writes `run-report.json` with one `gate_decisions` record per finding and a reason for each decision.
- Added Skill B `analyze` CLI entrypoint while preserving the M0 `validate` flow.

## Scope Intentionally Not Done

- No google-benchmark adapter.
- No folded-stack adapter.
- No generic-llm adapter.
- No patch generation, diff generation, auto-apply, commit, or push behavior for analyzed target repositories.
- No Tizen device capture or symbolization logic.

## Outputs

- `patches.json`: schema-validated suggestion-patch document; every patch is `advisory-only`, `validation_status=not-run`, and `measured_impact=null`.
- `run-report.json`: trace metadata, source reports, finding counts, anchor confidence distribution, and gate decisions.
- `run-<trace_id>.jsonl`: structured trace events written by `common.tracing`.

## Next Step

Wait for B1 review. Do not continue to B2 until review is complete.
