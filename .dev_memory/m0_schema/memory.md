# M0 Schema Memory

Status: completed locally, pending review.

Branch: `stage/m0-schema`

## Completed

- Built the M0 repository skeleton from DESIGN §13 without implementing later A/B business logic.
- Added two JSON Schema contract types:
  - `performance-findings.schema.json`
  - `suggestion-patch.schema.json`
- Put byte-identical `performance-findings.schema.json` copies under both skills.
- Implemented `common/schema_validate.py` with JSON Schema validation plus DESIGN §6.6 semantic rules 1-6.
- Implemented `common/tracing.py` and `common/cli_base.py` skeletons for DESIGN §11 and §12.1.
- Added three CLI entrypoints:
  - `python -m perf_hotspot_analyzer validate`
  - `python -m perf_suggestion_patch validate`
  - `python -m perf_optimization_pipeline validate`
- Added unit tests for schema conditions, semantic validation, and skill import boundaries.
- Added M0 test guide and review package.

## Key Details

- `common/schema_validate.py`: central validation entrypoint. It detects or accepts document type, loads the appropriate skill schema, runs Draft 2020-12 validation, then enforces the six semantic rules from DESIGN §6.6.
- `skills/perf-hotspot-analyzer/schemas/performance-findings.schema.json`: analyzer copy of the shared findings contract. It enforces §6.2 per-kind requirements.
- `skills/perf-suggestion-patch/schemas/performance-findings.schema.json`: byte-identical findings contract copy for Skill B.
- `skills/perf-suggestion-patch/schemas/suggestion-patch.schema.json`: patch contract with per-status rules for advisory-only and diff-capable statuses.
- `common/tracing.py` and `common/cli_base.py`: minimal structured trace and run-report support. M0 CLI only validates input and writes `run-report.json` plus JSONL trace output.
- `tests/unit/`: validates positive and negative branches. No M0.5 golden fixtures were added.

## Tests

| Command | Result |
| --- | --- |
| `python3 -m compileall common cli perf_hotspot_analyzer perf_suggestion_patch perf_optimization_pipeline tests/unit` | pass |
| `cmp -s skills/perf-hotspot-analyzer/schemas/performance-findings.schema.json skills/perf-suggestion-patch/schemas/performance-findings.schema.json` | pass |
| `.venv/bin/python -m pytest tests/unit` | 20 passed |
| `.venv/bin/python -m pytest` | 20 passed |
| CLI smoke for A/B/pipeline validate | pass |

## Next Entry

After review and merge, start M0.5 on a new reviewed-main branch. M0.5 should create the golden fixtures listed in DESIGN §10.4 and must not change M0 contracts unless review requires it.
