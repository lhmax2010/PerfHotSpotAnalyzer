# Hotfix Tizen Real Board Review Pack

## Summary

This branch fixes eight real-board issues found on a Tizen armv7l board running
ffmpeg decode profiling through ssh. The changes are scoped to robustness,
compatibility, schema acceptance, and target metadata correctness.

## Review Focus

- `find_source_anchor` no longer scans the full repo per symbol when indexes are
  available and has bounded fallback behavior.
- Capture streams `runner.sh` over stdin, avoiding Tizen UEP script execution
  restrictions in `/tmp` and `/opt/usr`.
- Profile/job timeout knobs are honored, and command-mode `duration_s: 0` no
  longer produces a tiny capture timeout.
- ARMv7 auto callgraph mode prefers frame pointers, with DWARF documented as a
  slower explicit choice.
- Capture/performance schemas accept `armv7l`, and schema copies remain
  SHA-256 synchronized.
- Runner metadata captures `proc-<target_pid>-maps` and warning-filled
  `kallsyms` rather than empty files or proc-self maps.

## Patches

See `.dev_memory/hotfix_tizen_realboard/patches.yaml` for the eight logical
fix commits and SHA references.
