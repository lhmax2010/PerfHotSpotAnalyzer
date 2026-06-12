# M-final Workflow Test Guide

## Scope

M-final validates the non-triggerable `perf-optimization-pipeline` workflow:

- `full`: Skill A report, Gate 1, Skill B patches, Gate 2, merged report
- `b-only`: external report into Skill B, Gate 2, merged report
- `a-only`: Skill A report only
- resumable stage state under `.perf-skill/runs/<run_id>/`

It does not apply generated patches, commit profiled repositories, push branches,
or integrate Cline / Compiling Agent.

## Prerequisites

- Python 3.11+ with test dependencies.
- Existing A/B fixtures from prior milestones.
- No live perf or Tizen board is required for the deterministic CI path.

## Deterministic CI Path

```bash
pytest tests/functional/test_mfinal_workflow.py tests/unit/test_mfinal_orchestrate.py -q
```

Expected result: 5 passed.

## Full Mode Smoke

Use a pre-captured A1 bundle:

```yaml
mode: full
run_id: mfinal-full-smoke
repo_root: .
output_dir: /tmp/mfinal-runs
non_interactive: true
a:
  bundle_dir: tests/fixtures/golden/live-perf/x86-hotspot/bundle
  ownership: tests/fixtures/golden/live-perf/x86-hotspot/.perf-skill/ownership.yaml
b:
  format: analyzer-json
  repo_root: .
```

Run:

```bash
python3 -m perf_optimization_pipeline pipeline run \
  --config /tmp/mfinal-full.yaml \
  --non-interactive
```

Pass criteria:

- `a_report/performance-findings.json` exists and validates.
- `b_run/patches.json` exists and validates.
- `state.json` records `gate_findings_review=pass` and
  `gate_patch_approval=pass`.
- `merged-report.md` includes Gate status, finding count, patch count, and the
  warning that patches were not applied, committed, or pushed.

## B-only Smoke

```yaml
mode: b-only
run_id: mfinal-b-only-smoke
repo_root: .
output_dir: /tmp/mfinal-runs
non_interactive: true
b:
  input: tests/fixtures/golden/positive/01-hotspot-binary-size-mixed/performance-findings.json
  format: analyzer-json
  repo_root: .
```

Expected: only `b_input`, `b_run`, `gate_patch_approval`, and merged report
artifacts are present.

## A-only Smoke

```yaml
mode: a-only
run_id: mfinal-a-only-smoke
repo_root: .
output_dir: /tmp/mfinal-runs
non_interactive: true
a:
  bundle_dir: tests/fixtures/golden/live-perf/tizen-arm/bundle
  ownership: tests/fixtures/golden/live-perf/tizen-arm/.perf-skill/ownership.yaml
```

Expected: `performance-findings.json` and `analysis-report.md` are present; no
`b_run/` directory is created.

## Interactive Gates

Omit `--non-interactive` to prompt:

```text
Gate 1: approve findings for Skill B patch suggestion generation? [Y/n]
Gate 2: approve generated patch review package? [Y/n]
```

Blank, `y`, or `yes` passes.  Any other response rejects the gate and leaves
the run resumable from the last successful stage.

## Resume

Rerun with the same `run_id`:

```bash
python3 -m perf_optimization_pipeline pipeline run \
  --config /tmp/mfinal-full.yaml \
  --run-id mfinal-full-smoke \
  --non-interactive
```

Successful stages in `state.json` are reused.  Failed or missing stages are run
again.

## Debug Logs

Each run writes:

- `<run-dir>/state.json`
- `<run-dir>/run-report.json`
- `<run-dir>/merged-report.md`
- `<run-dir>/run-<trace_id>.jsonl`

Attach those files plus the config YAML for review.
