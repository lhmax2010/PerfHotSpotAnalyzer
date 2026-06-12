# M-final Decisions

## D001: Orchestrate Through CLIs

The workflow calls `python -m perf_hotspot_analyzer` and
`python -m perf_suggestion_patch` through subprocess.  This preserves A/B skill
boundaries and keeps the workflow as the only component that knows both sides.

## D002: Pre-captured Bundles For Deterministic Full Tests

The config supports `a.bundle_dir` for CI and offline reviews.  Live capture is
still supported through `a.capture_job`, but deterministic tests use existing
pre-captured A1/A3 bundles.

## D003: Resume By `state.json`

Every successful stage records output paths.  Reruns with the same `run_id`
reuse those outputs if they still exist.  Failed stages are not reused.

## D004: Non-interactive Means Review Artifact Only

`--non-interactive` records PASS for gates and continues writing reports.  It
does not apply patches, commit profiled repositories, push branches, or invoke
any git operation.

## D005: No New Runtime Dependencies

The workflow reuses `common.simple_yaml`, `common.tracing`, and standard library
subprocess/json/pathlib APIs.  No new dependency was added.
