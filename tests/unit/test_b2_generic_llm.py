from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

from common.schema_validate import SUGGESTION_PATCH, validate_file


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
INGEST_PATH = ROOT / "skills" / "perf-suggestion-patch" / "scripts" / "ingest.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("b2_ingest_generic", INGEST_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generic_llm_writes_prompt_and_waits_for_normalized_output(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    raw_report = (
        FIXTURE_ROOT / "positive" / "05-low-confidence-generic-llm" / "freeform-report.txt"
    )

    try:
        ingest.load_generic_llm(raw_report, output_dir=tmp_path, repo_root="/repo/demo")
    except ingest.GenericLLMOutputPending as exc:
        pending = exc
    else:
        raise AssertionError("generic-llm should wait for host-normalized output")

    assert pending.paths.prompt_path.exists()
    assert not pending.paths.output_path.exists()
    prompt = pending.paths.prompt_path.read_text(encoding="utf-8")
    assert "source_format to \"generic-llm\"" in prompt
    assert "lookup is slow" in prompt
    assert str(pending.paths.output_path) in prompt


def test_generic_llm_reads_host_written_normalized_json(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    raw_report = (
        FIXTURE_ROOT / "positive" / "05-low-confidence-generic-llm" / "freeform-report.txt"
    )
    paths = ingest.prepare_generic_llm_protocol(
        raw_report,
        output_dir=tmp_path,
        repo_root="/repo/demo",
    )
    shutil.copyfile(
        FIXTURE_ROOT
        / "positive"
        / "05-low-confidence-generic-llm"
        / "performance-findings.json",
        paths.output_path,
    )

    report = ingest.load_generic_llm(raw_report, output_dir=tmp_path, repo_root="/repo/demo")

    assert report.source_reports == [
        {
            "id": "S1",
            "path": str(raw_report),
            "source_format": "generic-llm",
            "parser": "generic-llm",
            "confidence": 0.30,
        }
    ]
    assert report.findings[0]["confidence"] == 0.30
    assert report.findings[0]["source_format"] == "generic-llm"


def test_generic_llm_e2e_default_advisory_gate(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    raw_report = (
        FIXTURE_ROOT / "positive" / "05-low-confidence-generic-llm" / "freeform-report.txt"
    )
    paths = ingest.prepare_generic_llm_protocol(raw_report, output_dir=tmp_path)
    shutil.copyfile(
        FIXTURE_ROOT
        / "positive"
        / "05-low-confidence-generic-llm"
        / "performance-findings.json",
        paths.output_path,
    )

    result = ingest.run_generic_llm(raw_report, tmp_path)

    decision = result.run_report["gate_decisions"][0]
    assert "generic-llm-default-advisory" in decision["reason"]
    assert result.suggestion_patch["patches"][0]["status"] == "advisory-only"
    assert "diff" not in result.suggestion_patch["patches"][0]


def test_generic_llm_gate_shape_fixtures_18_and_19_are_valid() -> None:
    validate_file(
        FIXTURE_ROOT / "positive" / "18-generic-llm-default-advisory" / "patches.json",
        document_type=SUGGESTION_PATCH,
    )
    validate_file(
        FIXTURE_ROOT / "positive" / "19-generic-llm-deterministic-anchor" / "patches.json",
        document_type=SUGGESTION_PATCH,
    )
