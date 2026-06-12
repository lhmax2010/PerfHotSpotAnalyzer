# M-integ Integration Review Package

## Scope

M-integ completes the v1 integration surface:

- Cline rules + CLI path and MCP-wrapper guidance.
- Compiling Agent CLI adapter draft with degraded failure handling.
- User-facing integration guide for §12.1 entrypoints and exit codes.

Out of scope: private Compiling Agent protocol, real Cline IDE automation, patch
auto-apply, closed-loop validation, and LLM SDK usage from production Python.

## Key Files

- `integrations/cline/README.md`
- `integrations/cline/examples/clinerules/perf-skill.md`
- `integrations/cline/examples/b-only-demo.yaml`
- `integrations/cline/examples/run_b_only_demo.sh`
- `integrations/compiling_agent/README.md`
- `integrations/compiling_agent/adapter.py`
- `docs/integration_guide.md`
- `tests/integration/test_cline_examples.py`
- `tests/unit/test_compiling_agent_adapter.py`

## Behavior

- Cline users can copy `.clinerules` guidance and run a B-only CLI demo.
- Cline MCP path is documented according to current Cline docs, but CLI remains
  the supported v1 contract.
- Compiling Agent adapter uses `subprocess.run(..., timeout=...)`.
- Non-zero CLI exits return degraded results instead of raising.
- Timeouts return degraded result with exit code `124`.
- `apply()` is review-only and never applies patches.

## Validation

```bash
pytest -q
```

Result: 183 passed, 1 skipped.

```bash
.venv/bin/python -m pytest --cov=common --cov=skills --cov=cli --cov=workflows --cov=integrations --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 183 passed, 1 skipped, total coverage 82.92%.

```bash
python3 tools/check_no_llm_sdk_imports.py
python3 tools/check_schema_copies.py
bash tools/check_no_llm_sdk_imports.sh
```

Result: all passed.

## Review Checklist

- [x] `integrations/cline/` has README and runnable examples.
- [x] Cline `.clinerules` snippet exists.
- [x] Cline happy-path demo is covered by an integration test.
- [x] `integrations/compiling_agent/` has README and adapter skeleton.
- [x] Compiling Agent README starts with required user-supplied details.
- [x] Compiling Agent subprocess success/non-zero/timeout paths are tested.
- [x] `docs/integration_guide.md` documents entrypoints and exit codes.
- [x] No production Python code imports or calls LLM SDKs.

## v1 Closure

M-integ is the final v1 milestone.  After review, remaining work should move to
v1.1/v2 backlog rather than expanding v1 scope.
