# M0 Known Issues

- `LICENSE` remains unresolved. README already marks it as pending; M0 did not invent a license.
- M0 contains only CLI validation skeletons. Perf capture, report ingestion, anchor scoring, patch generation, workflow gates, MCP behavior, Cline integration, and Compiling Agent integration are intentionally deferred.
- The local host lacks the `python` and `pip` commands. Validation used `python3` and `uv` to create `.venv`.
- No M0.5 golden fixtures were added; only unit-test fixtures live in test code.
