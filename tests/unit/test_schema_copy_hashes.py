from __future__ import annotations

from tools.check_schema_copies import main


def test_schema_copy_hashes_match_canonical() -> None:
    assert main() == 0
