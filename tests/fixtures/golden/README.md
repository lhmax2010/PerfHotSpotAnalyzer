# Golden Fixtures

M0.5 contract fixtures from DESIGN §10.4.

- `positive/`: documents that must pass `common/schema_validate.py`.
- `negative/`: documents that must be rejected by `common/schema_validate.py`.

Each fixture directory contains `README.md`, `notes.md`, `expected.json`, and the
JSON document under validation. Some fixtures also include raw input data to make
the normalized contract document traceable for later milestones.

