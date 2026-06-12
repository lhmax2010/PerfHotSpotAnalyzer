# Compiling Agent Integration Draft

## Need User Input Before Final Integration

The Compiling Agent private integration API is not available in this repository.
To finish a real adapter, the user must provide:

- Tool registration mechanism: how the Compiling Agent discovers/registers an
  external tool.
- Parameter contract: how workload, repo root, device profile, capture job,
  report paths, and mode are passed.
- Artifact return path: how JSON reports, Markdown reports, and patch review
  files are returned to the agent.
- Authentication/authorization requirements: whether the agent requires tokens,
  workspace capabilities, sandbox permissions, or secret handling.

Until those details exist, v1 provides a CLI-based adapter draft only.  It does
not invent or depend on private Compiling Agent APIs.

## Contract

The adapter calls the v1 CLI surface with `subprocess.run(..., timeout=...)` and
maps results to structured JSON-like dictionaries.  It follows the §12.1 exit
codes:

- `0`: success, including degraded success with artifacts
- `1`: fatal error
- `2`: usage error
- `3`: unreadable input
- `124`: timeout

## Minimal Use

```python
from pathlib import Path
from integrations.compiling_agent.adapter import PerfSkillCLIAdapter

adapter = PerfSkillCLIAdapter(repo_root=Path("."))
result = adapter.analyze(
    config_path=Path("workflows/perf-optimization-pipeline/config.example.yaml"),
    mode="b-only",
    non_interactive=True,
)

if result["status"] == "success":
    print(result["artifacts"])
else:
    print(result["degraded_reason"])
```

## Methods

- `analyze(config_path, mode=None, non_interactive=True, timeout_s=None)`: runs
  `python -m perf_optimization_pipeline pipeline run --config ...`.
- `apply(patches_path, timeout_s=None)`: returns a review-only degraded result.
  v1 never applies generated patches automatically.

## Failure Behavior

- Non-zero CLI exit returns `status=degraded` with `exit_code`, stdout, stderr,
  and reason.
- Timeout returns `status=degraded`, `exit_code=124`, and reason `timeout`.
- The adapter does not raise to the caller for normal CLI failure/timeout.
- Unexpected local Python errors are caught and returned as degraded results.

## Example Registration Sketch

The following is intentionally pseudocode because the real Compiling Agent API
is unknown:

```python
# Pseudocode only; replace with the real API once provided.
agent.register_tool(
    name="perf_optimization_pipeline",
    handler=lambda payload: adapter.analyze(
        config_path=payload["config_path"],
        mode=payload.get("mode"),
        non_interactive=True,
    ),
)
```

Do not ship this pseudocode as production integration without replacing
registration, payload, artifact, and auth details with the real API.
