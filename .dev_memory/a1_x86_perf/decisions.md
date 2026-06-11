# A1 Decisions

## D001: Keep YAML Support Local And Minimal

Added `common/simple_yaml.py` instead of introducing PyYAML.  A1 only needs a
small config subset for device profiles, capture jobs, and ownership profiles.

## D002: Capture Bundle Is Directory-Based In Tests

The design describes a tarball for device transfer, but all schema validation is
manifest/artifact based.  A1 stores the local fixture as a directory bundle so CI
can inspect individual files without unpacking.  The manifest remains the
contract.

## D003: Source Anchors Are Deterministic Only

Owned frames become actionable only when the scripts find a unique C/C++ function
definition under `repo_root`.  If not, the finding is downgraded rather than
inventing an anchor.

## D004: Coverage Uses `uv run`

The system Python lacks `pytest-cov` and cannot create a venv because
`ensurepip` is unavailable.  Validation used `uv run --with pytest-cov` in an
ephemeral environment; no repository dependency was added.
