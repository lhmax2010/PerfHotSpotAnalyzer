# B3 Patch Generation Memory

## Scope Completed

- Implemented `skills/perf-suggestion-patch/scripts/make_patch.py`.
- Generates one atomic suggestion patch per finding.
- Uses `schema_validate.derive_effective_anchor(finding)` for `chosen_anchor`; no anchor is reselected in B3.
- Emits unified diffs for eligible findings and validates them through `suggestion-patch` schema.
- Enforces v1 invariants: `measured_impact=null`, `validation_status=not-run`.
- Implements file touched policy with default allow list and deny list.
- Marks build-flag changes as package-wide blast radius.
- Implements full B3 Gate status selection:
  - `diff-ready`
  - `needs-review`
  - `advisory-only`
- Generates `patch-report.md`.

## Scope Intentionally Not Done

- No runtime patch auto-apply, commit, or push.
- No build/test/benchmark execution.
- No Cline or Compiling Agent integration.
- No capture, preflight, DeviceRunner, or Tizen work.
- No LLM SDK usage.

## Notes

- Generated diffs are review suggestions and are intentionally not applied by the skill.
- `git apply --check` is covered in tests using temporary sample repos.
- Advisory-only outputs do not contain `diff`; schema_validate blocks invalid status/diff combinations.

## Next Step

Wait for B3 review. Do not continue to M-final until review is complete.
