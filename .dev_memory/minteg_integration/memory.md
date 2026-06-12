# M-integ Integration Memory

## Status

M-integ is implemented on `stage/minteg-integration`.

## Implemented

- `integrations/cline/`
  - README with `.clinerules` + CLI and MCP-wrapper paths.
  - Cline rule snippet under `examples/clinerules/perf-skill.md`.
  - Runnable B-only demo config and shell script.
  - Integration test that executes the demo and validates artifacts.
- `integrations/compiling_agent/`
  - README with required user-provided API details at the top.
  - CLI-based adapter draft in `adapter.py`.
  - `analyze()` runs the workflow CLI through `subprocess.run(..., timeout=...)`.
  - `apply()` returns review-only degraded status and does not apply patches.
  - Unit tests cover success, non-zero exit, timeout, and review-only behavior.
- `docs/integration_guide.md`
  - v1 integration overview, unified CLI contract, exit codes, and links.

## Handoff Notes

- Cline current docs were checked during implementation:
  - https://docs.cline.bot/customization/cline-rules
  - https://docs.cline.bot/mcp/mcp-overview
- Compiling Agent remains a draft until the private API is supplied by the user.
- v1 is complete after this milestone; further closed-loop validation belongs to
  v1.1/v2 backlog.
