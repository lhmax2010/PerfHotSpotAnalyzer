# Hotfix Effective Anchor Handoff Memory

Branch: `stage/hotfix-effective-anchor-handoff`

## Scope

Fixes the A to B handoff discovered by a real Tizen armv7l ffmpeg profiling
run. A findings had deterministic source anchors, but the canonical report did
not persist `effective_anchor`, so B lost the chosen target location.

## Completed

- `skills/perf-hotspot-analyzer/scripts/build_report.py` now writes
  `finding.effective_anchor` using `schema_validate.derive_effective_anchor()`.
- A analysis markdown and run-report anchor summaries now read the same
  effective-anchor value.
- `skills/perf-suggestion-patch/scripts/ingest.py` prefers serialized
  `effective_anchor` before deriving a fallback.
- `skills/perf-suggestion-patch/scripts/make_patch.py` prefers serialized
  anchors for `chosen_anchor`, keeps `chosen_anchor` on advisory patches, and
  makes A-originated reports without candidates advisory-only.
- Patch generation orders owned/actionable findings before system or
  not-actionable noise.

## Guardrails

- No LLM SDK imports or calls were added.
- No schema changes were made.
- Runtime-generated patches remain review-only and are never applied,
  committed, or pushed by the tool.
- v1 invariants remain intact: `measured_impact=null` and
  `validation_status=not-run`.

