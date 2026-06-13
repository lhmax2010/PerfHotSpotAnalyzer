# Hotfix Tizen Real Board Memory

## Scope

Branch: `stage/hotfix-tizen-realboard`

This hotfix addresses eight issues found during real Tizen armv7l board
profiling over ssh with an ffmpeg decode workload. It is limited to fixes and
hardening; no architecture changes, no patch auto-apply behavior, and no LLM SDK
usage were introduced.

## Completed

- Bounded `find_source_anchor` with ctags/compile_commands indexes and degraded
  fallback search.
- Restored Python 3.10 runtime compatibility and CI coverage.
- Added a PyYAML-first YAML loading facade with dependency-free fallback.
- Avoided Tizen UEP by running `runner.sh` over stdin instead of executing a
  pushed script from managed directories.
- Honored remote workdir and configurable shell/capture/script timeouts.
- Preferred frame-pointer callgraphs on embedded ARM auto mode and documented
  ARMv7 DWARF slowness.
- Accepted real Tizen arch values such as `armv7l` in schemas and report code.
- Captured target PID maps and non-empty/warning kallsyms metadata.

## Guardrails

- Python code does not import or call any LLM SDK.
- Runtime-generated patches remain review artifacts only; no apply/commit/push
  behavior changed.
- Existing A/B/M-final logic was only touched where needed by shared runtime
  compatibility or schema copies.
