# M0 Schema Test Guide

## Scope

M0 validates repository skeleton, JSON Schema contracts, semantic validation,
tracing skeleton, and CLI entrypoints. It does not run perf, touch Tizen devices,
generate patches, or apply patches.

## Prerequisites

- Linux host with Python 3.11+.
- `uv` or another way to install `requirements-dev.txt`.
- No Tizen, GBS, `sdb`, debuginfo, or `perf` setup is required for M0.

## Setup

```bash
uv venv .venv --python python3
uv pip install --python .venv/bin/python -r requirements-dev.txt
```

If using a system Python with pip available:

```bash
python3 -m pip install -r requirements-dev.txt
```

## Unit Validation

```bash
.venv/bin/python -m pytest
```

Expected result:

```text
20 passed
```

## CLI Smoke Validation

Create or reuse a valid `performance-findings.json` and `patches.json`, then run:

```bash
.venv/bin/python -m perf_hotspot_analyzer validate \
  --input performance-findings.json \
  --output-dir out/m0-a

.venv/bin/python -m perf_suggestion_patch validate \
  --input patches.json \
  --output-dir out/m0-b

.venv/bin/python -m perf_optimization_pipeline validate \
  --document-type performance-findings \
  --input performance-findings.json \
  --output-dir out/m0-pipeline
```

Expected result:

- Exit code `0` for valid documents.
- `out/<run>/run-report.json` exists.
- `out/<run>/run-<trace_id>.jsonl` exists.

## Debugging

- Set `PERF_SKILL_LOG_LEVEL=DEBUG` or pass `--verbose` to raise trace detail.
- Validation failures print schema and semantic errors to stderr.
- Missing input files return exit code `3`.
- Invalid JSON or contract violations return exit code `1`.

## Pass Criteria

- JSON Schema per-kind and per-status positive and negative tests pass.
- `common/schema_validate.py` semantic rules 1-6 each have passing positive and failing negative coverage.
- A and B contain byte-identical `performance-findings.schema.json` copies.
- Skill directories do not import each other.
