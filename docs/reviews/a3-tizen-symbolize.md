# A3 Tizen Symbolize Review Package

## Scope

A3 implements Tizen device capture transport and host-side cross-symbolization:

- ssh+scp primary DeviceRunner backend.
- sdb fallback DeviceRunner backend.
- Remote target-side perf capture through `runner.sh`.
- Host-side analysis from `perf-script.txt`.
- Build-id/sysroot/debuginfo mapping into `tizen.path_mapping`.
- Offline Tizen-style fixture and live device guide.

Out of scope: workflow orchestration, Skill B changes, binary-size work,
automatic target build/test/rerun, and any Python LLM/API calls.

## Key Files

- `common/device_runner.py`
- `skills/perf-hotspot-analyzer/scripts/capture.py`
- `skills/perf-hotspot-analyzer/target-side/runner.sh`
- `skills/perf-hotspot-analyzer/scripts/postprocess.py`
- `skills/perf-hotspot-analyzer/scripts/build_report.py`
- `tests/fixtures/golden/live-perf/tizen-arm/`
- `tests/functional/test_a3_tizen_symbolize.py`
- `tests/unit/test_a3_cross_symbolize.py`
- `docs/test-guides/a3-tizen-symbolize.md`

## Behavior

- ssh backend invokes `ssh <opts> user@host <cmd>` and `scp <opts> -r`.
- sdb backend invokes `sdb [-s serial] shell/push/pull`.
- Backend failures include remediation and do not silently retry or elevate.
- Remote capture pushes `runner.sh`, runs target perf, pulls a 10-piece bundle,
  and host-generates `out.folded` when target stackcollapse is disabled.
- `perf buildid-list -i perf.data` is preferred; `readelf -n` is fallback.
- Postprocess resolves build IDs under host debuginfo roots and projects target
  DSO paths into host sysroot.
- `performance-findings.json` carries `tizen.path_mapping` and validates through
  canonical schema plus semantic checks.

## Validation

```bash
pytest -q
```

Result: 171 passed, 1 skipped.

```bash
.venv/bin/python -m pytest --cov=common --cov=skills --cov=cli --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 171 passed, 1 skipped, total coverage 82.81%.

```bash
python3 tools/check_schema_copies.py
python3 tools/check_no_llm_sdk_imports.py
bash tools/check_no_llm_sdk_imports.sh
```

Result: all passed.

## Review Checklist

- [x] ssh backend implements shell/push/pull through subprocess.
- [x] sdb backend implements shell/push/pull through subprocess.
- [x] Backend command tracing records command, return code, and elapsed time.
- [x] Tizen sshd/OpenSSH remediation is explicit.
- [x] Remote capture keeps `perf-script.txt` as primary source.
- [x] `out.folded` is host-generated when target stackcollapse is false.
- [x] Pre-captured Tizen-style fixture anchors to file:line with confidence >= 0.7.
- [x] `tizen.path_mapping` is written into canonical findings output.
- [x] Canonical schema and semantic validation pass.
- [x] No Python code imports or calls LLM SDKs.

## Next Stage

Wait for A3 review. Do not continue to M-final until A3 and B3 reviews are
cleared.
