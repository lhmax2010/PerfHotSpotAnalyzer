from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.schema_validate import collect_validation_issues


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden"


def fixture_expectations() -> list[Path]:
    return sorted(FIXTURE_ROOT.glob("*/*/expected.json"))


@pytest.mark.parametrize("expected_path", fixture_expectations(), ids=lambda path: path.parent.name)
def test_golden_fixture_contract(expected_path: Path) -> None:
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    document_path = expected_path.parent / expected["document"]
    document = json.loads(document_path.read_text(encoding="utf-8"))

    issues = collect_validation_issues(
        document,
        document_type=expected["document_type"],
    )
    issue_rules = {issue.rule for issue in issues}

    if expected["valid"]:
        assert issues == []
    else:
        assert issues, f"{document_path} should be rejected"
        assert set(expected.get("expected_rules", [])) <= issue_rules

