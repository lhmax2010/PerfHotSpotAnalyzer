# M-integ Known Issues

- Compiling Agent private API is not available.  Real registration, payload,
  artifact return, and authentication details must be supplied by the user.
- Cline MCP server wrapping is documented as an optional path, but no MCP server
  implementation is added in M-integ.
- The Cline integration test runs the CLI demo directly rather than launching a
  real Cline IDE session.  Manual Cline validation steps are documented in the
  README.
- v1 does not implement closed-loop patch apply, rebuild, rerun, or statistical
  measured impact.
