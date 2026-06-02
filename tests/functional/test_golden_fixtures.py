from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.schema_validate import collect_validation_issues, derive_effective_anchor


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

    for required_file in expected.get("required_files", []):
        assert (expected_path.parent / required_file).exists()

    for text_file, snippets in expected.get("text_contains", {}).items():
        text = (expected_path.parent / text_file).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in text

    if "expected_effective_anchor" in expected:
        finding = document["findings"][expected.get("finding_index", 0)]
        effective_anchor = derive_effective_anchor(finding)
        assert effective_anchor is not None
        assert effective_anchor["symbol"] == expected["expected_effective_anchor"]["symbol"]
        assert effective_anchor["file"] == expected["expected_effective_anchor"]["file"]

    if "expected_actionability" in expected:
        finding = document["findings"][expected.get("finding_index", 0)]
        assert finding["actionability"] == expected["expected_actionability"]

    if "expected_patch_status" in expected:
        patch = document["patches"][expected.get("patch_index", 0)]
        assert patch["status"] == expected["expected_patch_status"]
        assert patch["patch_category"] == expected["expected_patch_category"]

    if "ownership_cases" in expected:
        cases = json.loads((expected_path.parent / expected["ownership_cases"]).read_text(encoding="utf-8"))
        assert {case["expected_ownership"] for case in cases["cases"]} == {
            "owned",
            "third-party",
            "system",
            "unknown",
        }
