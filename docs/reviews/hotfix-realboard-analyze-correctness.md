# Hotfix Realboard Analyze Correctness Review Pack

## Summary

This hotfix codifies the real-board analyze fixes verified on Tizen armv7l with
ffmpeg 8.0.1. It focuses on bounded source anchoring, ctags correctness,
versioned DSO ownership matching, and preserving owned hotspots under system
noise.

## Review Focus

- `[unknown]`, bracket pseudo-symbols, and pure addresses do not enter source
  search.
- Bounded source search caches misses for repeated unresolved symbols.
- Pattern-only ctags entries resolve to the actual source line lazily and never
  fake line 1.
- `/lib/libavcodec.so*` and `*/libavcodec.so*` match
  `/usr/lib/libavcodec.so.62.11.100`.
- Owned hotspots remain present even if global top-N is dominated by system
  frames.

## Verification

See `.dev_memory/hotfix_realboard_analyze_correctness/test_report.md`.
