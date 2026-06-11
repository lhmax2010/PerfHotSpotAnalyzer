# A2 binary-size Memory

## Status

A2 is implemented on `stage/a2-binary-size`.

## Implemented

- `skills/perf-hotspot-analyzer/scripts/binary_size.py`
  - Parses `readelf -S --wide` section headers.
  - Filters SHF_ALLOC sections via the `A` flag.
  - Generates `binary-size-large` findings for single ELF input.
  - Generates `binary-size-regression` findings for current/baseline ELF input.
  - Writes `performance-findings.json`, `analysis-report.md`, and `run-report.json`.
- `cli/perf_hotspot_analyzer.py`
  - Adds `binary-size --elf <path> [--baseline <path>] --output-dir <dir>`.
- `tests/fixtures/golden/live-perf/binary-size/`
  - `topn.elf` for top-n-only large findings.
  - `before.elf` / `after.elf` for `.inflate` section regression.
  - Source and rebuild script included.

## Behavior

- Single ELF:
  - `top-n`: top 5 alloc sections, default `informational`.
  - `section-ratio`: section >= 10% alloc bytes, default actionable if owned.
  - `absolute-bytes`: section >= 64KB, default actionable if owned.
  - `user-budget`: optional budget, default actionable if owned.
- Regression:
  - Pair alloc sections by name across current/baseline.
  - Trigger if absolute delta >= 1024 bytes or pct delta >= 5%.
  - Default actionable if current ELF ownership resolves to owned.
- If an otherwise actionable binary-size finding has non-owned/unknown ownership and no attribution anchor, it is downgraded to `informational`.

## Handoff Notes

- A2 does not change A1 perf capture/analyze flow.
- A2 does not implement binary-size source-level anchors.
- A3 should still be limited to Tizen symbolization/transport after A2 review.
