# Integration Guide

This guide summarizes the v1 integration surface for PerfHotSpotAnalyzer.
The CLI contract is the source of truth.  Agent integrations should call the CLI
and consume JSON/Markdown artifacts rather than importing Skill A or Skill B.

## Unified CLI Contract

Entry points:

```bash
python3 -m perf_hotspot_analyzer <subcmd> [args]
python3 -m perf_suggestion_patch <subcmd> [args]
python3 -m perf_optimization_pipeline pipeline run --config <yaml>
```

Common outputs:

- `<output-dir>/performance-findings.json` for Skill A/report workflows
- `<output-dir>/patches.json` for Skill B patch suggestions
- `<output-dir>/run-report.json`
- `<output-dir>/run-<trace_id>.jsonl`
- optional Markdown reports such as `analysis-report.md`, `patch-report.md`, and
  workflow `merged-report.md`

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | Success, including degraded success with artifacts |
| 1 | Fatal error |
| 2 | Usage or argument error |
| 3 | Input file unreadable |
| 124 | Timeout |

Generated patches are review suggestions only.  v1 integrations must not
automatically apply, commit, or push them.

## Skill A: Perf Hotspot Analyzer

Common commands:

```bash
python3 -m perf_hotspot_analyzer capture \
  --job .perf-skill/jobs/example.yaml \
  --repo-root . \
  --output-dir out/captures

python3 -m perf_hotspot_analyzer analyze \
  --bundle-dir out/captures/example \
  --repo-root . \
  --ownership .perf-skill/ownership.yaml \
  --output out/postprocess.json \
  --output-dir out/analyze

python3 -m perf_hotspot_analyzer report \
  --analysis out/postprocess.json \
  --repo-root . \
  --output-dir out/report
```

## Skill B: Perf Suggestion Patch

Common command:

```bash
python3 -m perf_suggestion_patch analyze \
  --input out/report/performance-findings.json \
  --format analyzer-json \
  --repo-root . \
  --output-dir out/patches
```

Skill B writes `patches.json` and `patch-report.md`.  Advisory-only patches do
not include diffs.

## Workflow

Use the workflow when an integration wants one command for full, B-only, or
A-only operation:

```bash
python3 -m perf_optimization_pipeline pipeline run \
  --config workflows/perf-optimization-pipeline/config.example.yaml \
  --non-interactive
```

The workflow writes all artifacts under `.perf-skill/runs/<run_id>/` or the
configured `output_dir`, including `state.json` for resume and
`merged-report.md` for human review.

## Cline

See [`integrations/cline/README.md`](../integrations/cline/README.md).

Supported v1 paths:

- `.clinerules/` rules that instruct Cline to call the CLI.
- Optional MCP wrapper once a CLI-backed MCP server is configured in Cline.

Runnable example:

```bash
integrations/cline/examples/run_b_only_demo.sh
```

## Compiling Agent

See [`integrations/compiling_agent/README.md`](../integrations/compiling_agent/README.md).

The v1 integration is a CLI-based draft.  The private Compiling Agent API is not
specified, so the README starts with the required user-supplied details.  The
adapter skeleton is:

```python
from pathlib import Path
from integrations.compiling_agent.adapter import PerfSkillCLIAdapter

adapter = PerfSkillCLIAdapter(repo_root=Path("."))
result = adapter.analyze(config_path="workflow.yaml", mode="full")
```

Timeouts and non-zero exits return degraded results instead of raising into the
caller.

## Security And Guardrails

- No production Python code may import LLM SDKs.
- Integration code should use timeouts around subprocess calls.
- Generated patches are never automatically applied.
- Use `run-report.json` and JSONL traces for debugging.
- For Tizen/live perf, prefer preflight and capture guides under
  `docs/test-guides/`.
