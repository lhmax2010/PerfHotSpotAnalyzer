# M-integ Decisions

## D001: Continue Despite Pending M-final Review Pointer

`.dev_memory/current.yaml` still said to wait for M-final review, but the user
explicitly requested M-integ.  The latest user instruction controlled the turn.

## D002: Cline Rules Path Matches Current Docs

Cline documentation checked during M-integ says workspace rules live under
`.clinerules/` and Cline processes markdown/text rule files there.  This matches
DESIGN §12.2, so no design divergence is required.

## D003: Cline MCP Config Uses Current Manual/CLI Paths

Cline's current MCP docs describe manual MCP server config and the `cline mcp`
CLI wizard.  The integration README documents both at a high level and leaves
the v1 supported execution path as CLI.

## D004: Compiling Agent Remains API-Agnostic

DESIGN §15.2 lists the Compiling Agent API as unresolved.  The implementation
therefore provides a subprocess-based adapter draft and a top-of-README checklist
of required user details instead of inventing registration/auth/payload APIs.

## D005: No New Runtime Dependencies

The adapter uses only Python standard library modules and existing CLI entry
points.  No dependency was added.
