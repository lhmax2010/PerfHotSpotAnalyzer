# M-final Workflow Memory

## Status

M-final is implemented on `stage/mfinal-workflow`.

## Implemented

- `workflows/perf-optimization-pipeline/orchestrate.py`
  - Non-triggerable workflow orchestrator.
  - Supports `full`, `b-only`, and `a-only` modes.
  - Calls Skill A and Skill B through their CLI modules via subprocess.
  - Writes all stage artifacts under `.perf-skill/runs/<run_id>/` or configured
    `output_dir`.
  - Records `state.json` for stage recovery.
  - Implements Gate 1 findings review and Gate 2 patch approval.
  - Supports `--non-interactive` auto-pass without applying, committing, or
    pushing any generated patch.
  - Generates `merged-report.md`.
- `cli/perf_optimization_pipeline.py`
  - Adds `pipeline run --config <yaml>`.
  - Supports `--mode`, `--non-interactive`, and `--run-id`.
  - Keeps the existing validate path.
- `workflows/perf-optimization-pipeline/WORKFLOW.md`
  - Documents modes, gates, output layout, and non-triggerable boundary.
- `workflows/perf-optimization-pipeline/config.example.yaml`
  - Provides user-facing config shape.
- Tests
  - Functional coverage for all three modes.
  - Unit coverage for non-interactive safety and stage resume.

## Handoff Notes

- The workflow does not contain `SKILL.md`.
- Generated patches remain review artifacts only.
- M-integ remains the next milestone for Cline / Compiling Agent integration.
