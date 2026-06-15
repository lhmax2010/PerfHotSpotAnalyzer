# Hotfix Realboard Analyze Correctness Memory

Branch: `stage/hotfix-realboard-analyze-correctness`

## Scope

Codifies fixes manually verified on a real Tizen armv7l board with ffmpeg 8.0.1.
The workload produced thousands of `[unknown]` frames and versioned ffmpeg DSOs
such as `/usr/lib/libavcodec.so.62.11.100`.

## Completed

- `find_source_anchor()` now short-circuits invalid symbols before any source
  tree search.
- Bounded source search now caches both hits and misses by `(root, symbol, dso)`.
- Pattern-only ctags entries no longer resolve to fake line 1; they lazily read
  the matched source file only for the queried symbol.
- Ownership matching now handles `/lib` versus `/usr/lib`, basename glob rules,
  and versioned `.so.N.N.N` DSOs without overmatching generic `*.so*` patterns.
- Hotspot selection keeps global top-N and also preserves owned hotspots so
  system noise cannot completely hide actionable owned code.
- Tizen guide now recommends `*/libavcodec.so*` style ownership globs.

## Guardrails

- No LLM SDK imports or calls were added.
- No schema changes were made.
- Runtime patch apply/commit/push behavior remains unchanged.
