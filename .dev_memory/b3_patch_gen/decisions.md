# B3 Decisions

## Patch Generation

- The deterministic generator inserts a review marker comment at the selected anchor line to create an atomic unified diff.
- This keeps B3 free of LLM calls while producing a real, apply-checkable diff.
- `chosen_anchor` is selected only by `schema_validate.derive_effective_anchor(finding)`.

## Gate

- Actionability, anchor confidence, benchmark-latency without perf budget, generic-llm default, patch category, allocation-reduction risk, and file policy all feed advisory decisions.
- `local-micro-optimization` can be `diff-ready`.
- `build-flag` can produce a diff but is `needs-review` because it may affect all files in the package.
- `allocation-reduction` can produce a diff only for local reserve/preallocation style changes.
- shared caches, object pools, ownership/lifetime/thread visibility changes are advisory-only.
- algorithm, concurrency, and API/semantic changes are advisory-only.

## Verification Plan

- B3 fills build/test/benchmark commands as review instructions.
- B3 does not execute them.
- `validation_status` remains `not-run`.

## File Policy

- Default allow list: `src/`, `include/`, `CMakeLists.txt`, `packaging/*.spec`.
- Deny list includes `.git`, binaries, generated/build outputs, locks, credentials, secrets, tokens, and secret-like paths.
