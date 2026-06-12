# Perf Skill CLI Rules

When asked to profile, analyze, or suggest performance optimizations in this
workspace, use the repository CLI contracts:

- Analyzer: `python3 -m perf_hotspot_analyzer <subcmd> ...`
- Patch suggestions: `python3 -m perf_suggestion_patch analyze ...`
- Workflow: `python3 -m perf_optimization_pipeline pipeline run --config ...`

Always validate generated JSON with the matching CLI `validate` subcommand when
the user asks for a final artifact.  Treat `patches.json` and `.patch` text as
review suggestions only.  Do not automatically apply, commit, or push generated
patches.

Recommended B-only demo:

```bash
integrations/cline/examples/run_b_only_demo.sh
```

After the command succeeds, summarize:

- `out/cline-b-only/patch-report.md`
- `out/cline-b-only/run-report.json`

Exit codes:

- `0`: success, including degraded success with artifacts
- `1`: fatal error
- `2`: usage error
- `3`: unreadable input
- `124`: timeout
