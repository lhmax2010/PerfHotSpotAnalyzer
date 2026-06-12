# perf-optimization-pipeline Workflow

This directory is a workflow orchestrator, not a triggerable skill.  It must not
contain `SKILL.md`, frontmatter trigger text, or skill-discovery descriptions.
It coordinates the existing Skill A and Skill B command-line entrypoints and
writes review artifacts under a workflow run directory.

## Modes

### full

Run Skill A, review findings, run Skill B, review patches, and deliver the
review package.

```bash
python3 -m perf_optimization_pipeline pipeline run \
  --config workflows/perf-optimization-pipeline/config.example.yaml \
  --mode full
```

CI and offline reviews can set `a.bundle_dir` to a pre-captured Capture Bundle.
Live device runs can set `a.capture_job` instead.

### b-only

Skip Skill A and run Skill B from an external `performance-findings.json` or
other supported report.

```bash
python3 -m perf_optimization_pipeline pipeline run \
  --config workflows/perf-optimization-pipeline/config.example.yaml \
  --mode b-only
```

Use this mode when another profiler or analyzer already produced a supported
report.

### a-only

Run Skill A only and stop after `performance-findings.json` and
`analysis-report.md`.

```bash
python3 -m perf_optimization_pipeline pipeline run \
  --config workflows/perf-optimization-pipeline/config.example.yaml \
  --mode a-only
```

Use this mode when the desired output is a deterministic hotspot report rather
than patch suggestions.

## Gates

The workflow has two human gates:

- Gate 1: review Skill A findings before running Skill B.
- Gate 2: approve the Skill B patch review package for handoff.

By default, both gates prompt on stdin with `Y/n`.  In `--non-interactive` mode,
the workflow records PASS for the gates and writes artifacts only.  It never
applies generated patches, commits user code, or pushes branches.

## Output Layout

Each run writes to:

```text
.perf-skill/runs/<run_id>/
├── state.json
├── run-report.json
├── merged-report.md
├── a_capture/
├── a_analyze/
├── a_report/
└── b_run/
```

Only stages needed by the selected mode are present.  The `state.json` file is
used for recovery: rerunning with the same `run_id` skips successful stages and
continues from the most recent incomplete or failed stage.

## Key Artifacts

- `a_report/performance-findings.json`
- `a_report/analysis-report.md`
- `b_run/patches.json`
- `b_run/patch-report.md`
- `merged-report.md`
- `run-report.json`
- `state.json`

Generated patches remain review suggestions.  The workflow does not modify the
profiled repository outside its configured run directory.
