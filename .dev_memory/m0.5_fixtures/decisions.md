# M0.5 Decisions

## D001: Branch from M0 baseline

Decision: Create `stage/m0.5-fixtures` from `stage/m0-schema`.

Reason: `origin/main` still contained only design documents when M0.5 started,
while the user explicitly requested continuing with M0.5 from `current.yaml`.
M0.5 depends on M0's `common/schema_validate.py` and schemas.

## D002: Store fixtures as contract documents

Decision: Each golden fixture validates a normalized `performance-findings.json`
or `patches.json` contract document. Some fixtures also include raw report data
for later adapter milestones.

Reason: DESIGN §10.4 says M0.5 is the contract baseline. Parser implementation
belongs to later A/B milestones, not M0.5.

## D003: Expected files name schema_validate rules

Decision: `expected.json` records `valid` and optional `expected_rules`.

Reason: This makes negative fixture failures auditable while keeping the test
generic and centered on `common/schema_validate.py`.

## D004: No schema edits in M0.5

Decision: M0.5 adds fixtures and functional tests only.

Reason: The user requested golden fixtures as the next milestone. Contract
behavior remains the M0 schema/validator baseline unless review asks for a
schema correction.
