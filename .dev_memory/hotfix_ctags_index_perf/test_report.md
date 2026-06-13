# Hotfix Ctags Index Performance Test Report

## Targeted

- `pytest tests/unit/test_a1_postprocess.py -q`: 12 passed

## Full Verification

- `python3 tools/check_schema_copies.py`: passed
- `bash tools/check_no_llm_sdk_imports.sh`: passed
- `PYTHONPATH=/tmp/perfhotspot-deps:$PYTHONPATH python3 -m pytest tests/unit tests/functional tests/security tests/integration --cov=common --cov=cli --cov=perf_hotspot_analyzer --cov=perf_suggestion_patch --cov=perf_optimization_pipeline --cov=skills --cov=workflows --cov=integrations --cov-report=term-missing`:
  203 passed, 1 skipped; total coverage 83%

Note: coverage uses `/tmp/perfhotspot-deps` because the base environment lacks
pytest-cov and is PEP 668 managed.
