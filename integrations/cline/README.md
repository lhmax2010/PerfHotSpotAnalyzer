# Cline Integration

This integration keeps Cline as the human-facing agent and uses this repository's
CLI contracts as the execution surface.  It does not add a new triggerable skill.

Current Cline documentation confirms two stable paths:

- Workspace rules live under `.clinerules/` and are loaded as persistent project
  instructions.
- MCP servers can be added through Cline's MCP UI, manual JSON config, or the
  `cline mcp` CLI wizard.

References checked during M-integ:

- Cline Rules: https://docs.cline.bot/customization/cline-rules
- Cline MCP: https://docs.cline.bot/mcp/mcp-overview

## Path A: `.clinerules/` + CLI

Copy the sample rule into the target repository:

```bash
mkdir -p .clinerules
cp integrations/cline/examples/clinerules/perf-skill.md .clinerules/perf-skill.md
```

Then ask Cline to run one of the CLI-backed tasks.  The rule tells Cline to use
the v1 CLI entrypoints and to treat generated patches as review artifacts only.

Minimal B-only smoke:

```bash
integrations/cline/examples/run_b_only_demo.sh
```

Expected outputs:

- `out/cline-b-only/b_run/patches.json`
- `out/cline-b-only/b_run/patch-report.md`
- `out/cline-b-only/run-report.json`

Manual prompt for Cline:

```text
Run the perf suggestion patch B-only demo from
integrations/cline/examples/run_b_only_demo.sh, then summarize
out/cline-b-only/b_run/patch-report.md. Do not apply any generated patch.
```

## Path B: MCP Server Wrapper

When a CLI wrapper MCP server is available, add it to Cline as a local STDIO
server.  Cline's current MCP docs support manual JSON configuration and
`cline mcp`.

Manual config shape:

```json
{
  "mcpServers": {
    "perf-hotspot-analyzer": {
      "command": "python3",
      "args": ["-m", "mcp.server"],
      "env": {},
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

The MCP server is optional in v1.  The supported contract remains the CLI:

```bash
python3 -m perf_hotspot_analyzer ...
python3 -m perf_suggestion_patch ...
python3 -m perf_optimization_pipeline pipeline run --config ...
```

## Troubleshooting

- If Cline ignores the rule, confirm `.clinerules/perf-skill.md` is at the
  workspace root and enabled in Cline's Rules panel.
- If a command fails with exit code `3`, check input paths.
- If a command fails with exit code `124`, increase the timeout or run the
  command manually to inspect device/perf setup.
- If Skill B emits only advisory patches, that is valid v1 behavior when anchors
  or Gate conditions are not strong enough for a diff.
- Generated patches are never automatically applied, committed, or pushed.
