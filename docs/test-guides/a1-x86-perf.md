# A1 x86 perf Test Guide

## Scope

A1 validates the local x86 path for Skill A: preflight, Capture Bundle,
postprocess ownership/attribution, and report generation.  It does not validate
Tizen, ssh, sdb, binary-size findings, or workflow orchestration.

## Prerequisites

- Linux x86_64 host.
- Python test dependencies from `requirements.txt` and `requirements-dev.txt`.
- Optional for live smoke only: `gcc`, `perf`, and host permissions for perf
  sampling.

## Deterministic CI Path

```bash
pytest tests/functional/test_a1_x86_perf.py -q
```

Expected result: 3 passed, 1 skipped.  The skipped test is live perf capture.

Manual equivalent:

```bash
python3 -m cli.perf_hotspot_analyzer analyze \
  --bundle-dir tests/fixtures/golden/live-perf/x86-hotspot/bundle \
  --repo-root tests/fixtures/golden/live-perf/x86-hotspot \
  --ownership tests/fixtures/golden/live-perf/x86-hotspot/.perf-skill/ownership.yaml \
  --output /tmp/a1-postprocess.json \
  --output-dir /tmp/a1-analyze

python3 -m cli.perf_hotspot_analyzer report \
  --analysis /tmp/a1-postprocess.json \
  --repo-root tests/fixtures/golden/live-perf/x86-hotspot \
  --output-dir /tmp/a1-report
```

Pass criteria:

- `/tmp/a1-report/performance-findings.json` validates with
  `common/schema_validate.py`.
- Top-1 finding is `busy_loop`.
- `profiling.callgraph_mode` is `fp`.
- `run_context.cpu_governor` is preserved.
- `g_signal_emit` has an attribution anchor to `busy_loop`.
- `malloc` is `not-actionable`.
- `mystery_hot` is `informational`.

## Live Perf Smoke

Live capture is optional and skipped by default:

```bash
PERF_SKILL_ENABLE_LIVE_PERF=1 pytest tests/functional/test_a1_x86_perf.py::test_a1_live_perf_capture_smoke -q
```

If perf permission is denied, inspect:

```bash
cat /proc/sys/kernel/perf_event_paranoid
grep CapEff /proc/self/status
```

Ask an administrator to lower `perf_event_paranoid` or grant CAP_PERFMON to the
perf executable.  The scripts do not run sudo or change host policy.

## Debug Logs

Each CLI command writes:

- `<output-dir>/run-<trace_id>.jsonl`
- `<output-dir>/run-report.json`

Use the `trace_id` from stderr or `run-report.json` to correlate events.

## Feedback Attachments

For review or bug reports, attach:

- `capture-job.yaml`
- `manifest.json`
- `perf-script.txt`
- `run-context.json`
- `performance-findings.json`
- `analysis-report.md`
- `run-report.json`
