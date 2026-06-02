# B1 Decisions

## Analyzer-json Adapter

- Treat the canonical `performance-findings.json` document as the B1 analyzer-json input.
- Validate through `common/schema_validate.py` before any output generation.
- Preserve source report dictionaries verbatim in both `patches.json` and `run-report.json`.

## Anchor Scoring

- Effective anchor derivation is delegated to `common.schema_validate.derive_effective_anchor`.
- The skill only wraps the derived anchor with rubric scoring.
- The original input anchor confidence is retained as `reported_anchor_confidence` when present.
- Caller-attribution receives 0.80 when it has a source location, reported confidence at least 0.70, and no ambiguity markers in evidence; otherwise it receives 0.65.

## Gate

- B1 gate order is: non-actionable first, missing effective anchor second, anchor confidence below 0.70 third, then B1 advisory-only downgrade.
- All B1 outputs are `advisory-only`; no `diff` field is emitted.
- `chosen_anchor` is included on advisory patches when a scored effective anchor exists so reviewers can audit the anchor used by the gate.

## Coverage

- Added `pytest-cov` to dev dependencies so the B1 coverage check is reproducible.
- Coverage is measured over the B1 CLI and ingest script, avoiding unrelated M0 placeholder entrypoints.
