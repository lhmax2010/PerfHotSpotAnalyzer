# B2 Benchmark Folded Generic Memory

## Scope Completed

- Added Google Benchmark ingest for single-report latency and before/after regression.
- Added folded-stacks ingest that aggregates leaf symbols into function-hotspot findings.
- Added generic-llm prompt handoff: write prompt, wait for host-normalized JSON, read back and validate.
- Added repo-root deterministic anchor search:
  - `tags` file -> `ctags` at 0.75
  - `compile_commands.json` scoped unique match -> `compile-db` at 0.75
  - repo grep unique match -> `grep` at 0.65
  - benchmark name source match -> `bench-name-map` at 0.50
- Kept all emitted suggestion patches advisory-only; B3 patch/diff generation is not implemented.
- Added DESIGN implementation note for `reported_anchor_confidence` vs rubric-scored `anchor_confidence`.

## Scope Intentionally Not Done

- No patch generation or diff generation.
- No google-benchmark perf budget handling beyond advisory Gate reason.
- No capture/preflight/DeviceRunner/Tizen work.
- No runtime LLM SDK calls.

## Fixture Coverage

- #02 Google Benchmark before/after -> `benchmark-regression`.
- #03 Google Benchmark single report -> `benchmark-latency`, advisory by no perf budget.
- #05 generic-llm raw report -> prompt handoff + host-normalized JSON path.
- #18 generic-llm default advisory patch contract remains valid.
- #19 generic-llm deterministic-anchor patch contract remains valid.

## Next Step

Wait for B2 review. Do not continue to B3 until review is complete.
