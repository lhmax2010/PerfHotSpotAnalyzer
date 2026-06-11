# A1 x86 perf Review Package

## Scope

A1 implements the local x86 path for Skill A:

- DeviceRunner local backend.
- Perf preflight.
- Capture/Analyze two-stage artifacts.
- Ownership classification and caller-attribution.
- Canonical `performance-findings.json` output.
- CLI `capture`, `analyze`, and `report` subcommands.

Out of scope: binary-size findings, Tizen/ssh/sdb transport, workflow
orchestration, and any LLM/API calls from Python.

## Key Files

- `common/device_runner.py`
- `common/simple_yaml.py`
- `skills/perf-hotspot-analyzer/scripts/preflight.py`
- `skills/perf-hotspot-analyzer/scripts/capture.py`
- `skills/perf-hotspot-analyzer/target-side/runner.sh`
- `skills/perf-hotspot-analyzer/scripts/postprocess.py`
- `skills/perf-hotspot-analyzer/scripts/build_report.py`
- `cli/perf_hotspot_analyzer.py`
- `tests/fixtures/golden/live-perf/x86-hotspot/`
- `tests/functional/test_a1_x86_perf.py`

## Behavior

- Local capture uses `DeviceRunner.shell/push/pull`.
- `perf-script.txt` is the primary symbolization/postprocess source.
- `out.folded` is generated from `perf-script.txt` when target-side folded data
  is absent.
- Ownership is determined from `.perf-skill/ownership.yaml`.
- Third-party/system hotspots walk the callgraph to the nearest owned frame by
  default.
- Findings without required anchors are downgraded before schema validation.
- `diagnosis` and `candidate_optimizations` remain pending host Agent work.

## Validation

```bash
pytest -q
```

Result: 140 passed, 1 skipped.

```bash
uv run --with pytest --with pytest-cov --with jsonschema pytest --cov=common --cov=skills --cov=cli --cov-report=term-missing --cov-fail-under=80 -q
```

Result: 140 passed, 1 skipped, total coverage 80.09%.

```bash
python3 tools/check_schema_copies.py
python3 tools/check_no_llm_sdk_imports.py
bash tools/check_no_llm_sdk_imports.sh
```

Result: all passed.

## Review Checklist

- [x] DeviceRunner local backend implements shell/push/pull.
- [x] ssh/sdb remain A3 stubs.
- [x] Preflight does not run sudo or mutate host permissions.
- [x] Capture Bundle manifest validates.
- [x] Pre-captured x86 fixture Top-1 is `busy_loop`.
- [x] Ownership covers owned/third-party/system/unknown.
- [x] Caller-attribution picks the nearest owned frame by default.
- [x] Canonical `performance-findings.json` validates.
- [x] `report_types` are derived from finding kinds.
- [x] Python production code imports no LLM SDKs.

## Next Stage

Wait for A1 review. Do not continue to A2 until review is complete.
