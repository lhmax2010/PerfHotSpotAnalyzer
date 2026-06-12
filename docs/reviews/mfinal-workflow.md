# M-final Workflow Review Package

## Scope

M-final implements the non-triggerable `perf-optimization-pipeline` workflow:

- full mode: A -> Gate 1 -> B -> Gate 2 -> merged report
- b-only mode: external report -> B -> Gate 2 -> merged report
- a-only mode: A -> merged report
- resumable stage state under configured run directories
- CLI `pipeline run --config <yaml>`

Out of scope: patch auto-apply, commit, push, Cline integration, Compiling Agent
integration, and measured-impact reruns.

## Key Files

- `workflows/perf-optimization-pipeline/orchestrate.py`
- `workflows/perf-optimization-pipeline/WORKFLOW.md`
- `workflows/perf-optimization-pipeline/config.example.yaml`
- `cli/perf_optimization_pipeline.py`
- `tests/functional/test_mfinal_workflow.py`
- `tests/unit/test_mfinal_orchestrate.py`
- `docs/test-guides/mfinal-workflow.md`
- `.dev_memory/mfinal_workflow/*`

## Behavior

- Workflow directory has no `SKILL.md`.
- Skill A and Skill B are invoked through their existing CLI modules.
- Gate 1 and Gate 2 default to interactive stdin `Y/n`.
- `--non-interactive` records PASS and continues, but does not apply, commit, or
  push patches.
- Each stage writes artifacts under `.perf-skill/runs/<run_id>/` or configured
  `output_dir`.
- Reruns with the same `run_id` resume successful stages from `state.json`.
- `merged-report.md` combines review status, A report, and B patch report.

## Validation

```bash
pytest -q
```

Result: 176 passed, 1 skipped.

```bash
.venv/bin/python -m pytest --cov=common --cov=skills --cov=cli --cov=workflows --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 176 passed, 1 skipped, total coverage 82.78%.

```bash
python3 tools/check_no_llm_sdk_imports.py
python3 tools/check_schema_copies.py
bash tools/check_no_llm_sdk_imports.sh
```

Result: all passed.

## Review Checklist

- [x] full mode runs A, Gate 1, B, Gate 2, and merged report.
- [x] b-only mode runs external report through B and Gate 2.
- [x] a-only mode stops after A output.
- [x] Gates default to interactive `Y/n`.
- [x] non-interactive mode does not apply, commit, or push.
- [x] stage resume reuses successful artifacts.
- [x] merged report includes Gate status, finding count, patch count, and review decisions.
- [x] workflow remains non-triggerable and has no `SKILL.md`.
- [x] no Python code imports or calls LLM SDKs.

## Next Stage

Wait for M-final review. Do not continue to M-integ until review is complete.
