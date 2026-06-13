# Hotfix Tizen Real Board Test Report

## Targeted Tests

- `pytest tests/unit/test_a1_postprocess.py -q`: 9 passed
- `pytest tests/unit/test_python310_compat.py -q`: 2 passed
- `pytest tests/unit/test_yaml_loader.py tests/unit/test_a1_device_runner.py -q`: 15 passed
- `pytest tests/unit/test_a1_capture.py tests/unit/test_a1_device_runner.py -q`: 22 passed
- `pytest tests/unit/test_a1_preflight.py tests/unit/test_a1_capture.py -q`: 18 passed
- `pytest tests/unit/test_schema_conditions.py tests/unit/test_a1_capture.py tests/unit/test_a1_build_report.py -q`: 29 passed
- `pytest tests/unit/test_a1_capture.py -q`: 11 passed
- `python3 tools/check_schema_copies.py`: passed

## Final Verification

- `python3 -m pytest tests/unit tests/functional tests/security tests/integration -q`:
  200 passed, 1 skipped
- `PYTHONPATH=/tmp/perfhotspot-deps:$PYTHONPATH python3 -m pytest tests/unit tests/functional tests/security tests/integration --cov=common --cov=cli --cov=perf_hotspot_analyzer --cov=perf_suggestion_patch --cov=perf_optimization_pipeline --cov=skills --cov=workflows --cov=integrations --cov-report=term-missing`:
  200 passed, 1 skipped; total coverage 82%
- `python3 tools/check_schema_copies.py`: passed
- `bash tools/check_no_llm_sdk_imports.sh`: passed

Note: the base environment lacked `pytest-cov` and `python3-venv`, so coverage
dependencies were installed into `/tmp/perfhotspot-deps` with `pip --target` and
loaded through `PYTHONPATH`.
