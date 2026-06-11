# A2 Decisions

## D001: Use readelf First

The implementation shells out to `readelf -S --wide` as requested.  No Python ELF
dependency was added.

## D002: One Large Finding Per Section

For each alloc section, A2 picks the strongest threshold in this order:
`user-budget > absolute-bytes > section-ratio > top-n`.  This prevents duplicate
findings for the same section while preserving top-n's informational default when
no stronger threshold is hit.

## D003: Ownership Applies At ELF Path Granularity

A2 does not attempt source-level section-to-symbol anchoring.  It classifies the
current ELF path with `.perf-skill/ownership.yaml`; otherwise ownership remains
`unknown` and actionable defaults are downgraded to `informational`.

## D004: Commit Real ELF Fixtures

The CI fixture stores pre-generated x86_64 ELF files plus their source and
`build.sh`.  This keeps CI deterministic while still making the binaries
reproducible during review.
