# M0 Decisions

## D001: Keep schemas in skill directories

Decision: Store `performance-findings.schema.json` under both skill directories as byte-identical copies, matching DESIGN §2. Skill B additionally owns `suggestion-patch.schema.json`.

Reason: A and B must remain independent and must not import each other. Tests compare the two findings schema copies.

Rejected: Put only one canonical schema under `common/`. That would be simpler, but DESIGN says both skills carry their own copy.

## D002: Semantic validation returns named issues

Decision: `common/schema_validate.py` exposes `collect_validation_issues()` and raises `SchemaValidationError` from `validate_document()` / `validate_file()`.

Reason: Unit tests need precise coverage of each DESIGN §6.6 rule, while CLI callers need a simple success/failure contract.

## D003: Benchmark findings map to `benchmark`

Decision: `benchmark-regression` and `benchmark-latency` derive the report type `benchmark`.

Reason: DESIGN §6.1 names `hotspot-profile` and `binary-size` explicitly and requires report types to be derived from kind. It does not name the benchmark report type, so M0 records the minimal stable mapping here.

## D004: CLI M0 implements only validation

Decision: The three entrypoints support only a `validate` subcommand.

Reason: DESIGN §12.1 defines the calling surface and exit codes, but M0 scope allows only argument parsing plus `schema_validate` calls. Capture, ingest, patch generation, workflow gates, and Tizen logic are deferred.

## D005: No license invented

Decision: M0 does not add a `LICENSE` file.

Reason: README already says license is pending. Adding an arbitrary license would be a project ownership decision outside M0.
