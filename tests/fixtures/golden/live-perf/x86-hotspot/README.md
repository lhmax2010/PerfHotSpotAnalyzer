# A1 x86 hotspot fixture

This fixture is the deterministic CI baseline for A1.  It contains a small
loop-heavy C target plus a pre-captured local Capture Bundle.  Live perf
capture is intentionally not required in CI; enable it explicitly with
`PERF_SKILL_ENABLE_LIVE_PERF=1`.
