# M0 Schema Review Package

## Scope

M0 implements the repository skeleton, JSON Schema contracts, semantic validator,
tracing/CLI skeletons, and unit tests. It intentionally stops before M0.5
fixtures and all A/B business logic.

## Key Files

- `skills/perf-hotspot-analyzer/schemas/performance-findings.schema.json`
- `skills/perf-suggestion-patch/schemas/performance-findings.schema.json`
- `skills/perf-suggestion-patch/schemas/suggestion-patch.schema.json`
- `common/schema_validate.py`
- `common/tracing.py`
- `common/cli_base.py`
- `cli/*.py`
- `tests/unit/test_schema_conditions.py`
- `tests/unit/test_schema_semantics.py`
- `.dev_memory/m0_schema/*`
- `docs/test-guides/m0-schema.md`

## Validation

```bash
.venv/bin/python -m pytest
```

Result: 20 passed.

CLI smoke validation for all three entrypoints also passed with valid temporary
documents.

## Review Checklist

- [x] DESIGN §6.2 per-kind schema conditions have positive and negative tests.
- [x] DESIGN §6.3 per-status schema conditions have positive and negative tests.
- [x] DESIGN §6.6 semantic rules 1-6 each have positive and negative unit coverage.
- [x] A and B carry identical `performance-findings.schema.json` copies.
- [x] Skill code does not import the other skill.
- [x] CLI uses `common/schema_validate.py` before accepting output documents.
- [x] No Python code calls LLM APIs.
- [x] M0.5 and later business logic is not implemented.

## Next Stage

After review and merge to `main`, start M0.5 golden fixtures on a new branch.
