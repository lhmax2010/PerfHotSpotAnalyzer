# Hotfix Realboard Analyze Correctness Decisions

## Invalid Symbols Must Not Search Source

- Root cause: `perf-script.txt` from the real ffmpeg run contained 6232
  `[unknown]` frames. Each unresolved frame could enter source-anchor lookup and
  trigger bounded fallback search.
- Fix: `find_source_anchor()` now returns `None` immediately for empty symbols,
  bracket pseudo-symbols such as `[unknown]`, and pure hexadecimal addresses.
- Test: `test_find_source_anchor_invalid_symbols_skip_bounded_search` monkeypatches
  bounded search to fail if invalid symbols reach it.

## Repeated Misses Need A Cache

- Root cause: repeated assembly symbols such as NEON helpers can miss source
  lookup repeatedly, causing repeated bounded tree scans.
- Fix: `_bounded_source_search()` caches `(matches, degraded)` for each
  `(repo_root, symbol, dso)`, including miss results.
- Test: `test_postprocess_large_unknown_and_repeated_asm_frames_is_bounded`
  uses thousands of `[unknown]` frames plus repeated NEON symbols and asserts
  source-file probes remain bounded.

## Pattern-Only Ctags Must Resolve Real Lines

- Root cause: standard ctags without `-n` emits search patterns without `line:`
  fields. The previous hotfix returned line 1, producing incorrect anchors.
- Fix: ctags pattern-only entries are kept with `line=None`; only when the
  queried symbol hits that entry do we open the source file once and locate the
  real line from the ctags pattern. If it cannot be resolved, no anchor is
  returned.
- Test: `test_find_source_anchor_resolves_pattern_only_ctags_to_real_line`
  verifies a pattern-only ctags entry resolves to line 4, not line 1.

## Ownership Must Match Versioned Symbolized DSOs

- Root cause: real symbolized DSO paths used `/usr/lib/libavcodec.so.62.11.100`
  while user rules often describe `/lib/libavcodec.so*` or basename globs.
- Fix: ownership matching tries original path, `/usr`-normalized variants, and
  safe basename patterns such as `libavcodec.so*`. It avoids overmatching broad
  basename patterns like `*.so*`.
- Test: `test_ownership_matches_versioned_usr_lib_by_basename_glob` covers
  `/usr/lib/libxxx.so.1.2.3` with `*/libxxx.so*` and ffmpeg's versioned
  libavcodec path with `/lib/libavcodec.so*`.

## Top-N Must Preserve Owned Hotspots

- Root cause: global top-N could be filled by system noise such as spinlock or
  allocator symbols, hiding lower-percentage owned/actionable hotspots.
- Fix: hotspot selection now keeps global top-N and additionally keeps top-N
  owned groups that were not already selected.
- Test: `test_top_n_keeps_owned_hotspot_when_system_noise_is_larger` builds a
  system-heavy fixture and asserts the owned hotspot is still emitted and
  actionable.
