from __future__ import annotations

import json
from pathlib import Path

from cli.perf_hotspot_analyzer import main as analyzer_main
from common.schema_validate import CAPTURE_BUNDLE, PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "live-perf" / "tizen-arm"
BUNDLE = FIXTURE / "bundle"
OWNERSHIP = FIXTURE / ".perf-skill" / "ownership.yaml"


def test_a3_tizen_precaptured_bundle_manifest_is_valid() -> None:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))

    validate_document(manifest, document_type=CAPTURE_BUNDLE)

    assert manifest["backend"] == "ssh"
    assert manifest["device"]["arch"] == "aarch64"
    assert manifest["artifacts"]["perf_script"] == "perf-script.txt"
    for artifact in manifest["artifacts"].values():
        assert (BUNDLE / artifact).exists()


def test_a3_tizen_precaptured_analyze_report_chain(tmp_path: Path) -> None:
    analysis_path = tmp_path / "postprocess.json"
    analyze_out = tmp_path / "analyze"
    report_out = tmp_path / "report"

    assert analyzer_main(
        [
            "analyze",
            "--bundle-dir",
            str(BUNDLE),
            "--repo-root",
            str(FIXTURE),
            "--ownership",
            str(OWNERSHIP),
            "--output",
            str(analysis_path),
            "--output-dir",
            str(analyze_out),
        ]
    ) == 0
    assert analyzer_main(
        [
            "report",
            "--analysis",
            str(analysis_path),
            "--repo-root",
            str(FIXTURE),
            "--output-dir",
            str(report_out),
        ]
    ) == 0

    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    document = json.loads((report_out / "performance-findings.json").read_text(encoding="utf-8"))
    validate_document(document, document_type=PERFORMANCE_FINDINGS)

    top = document["findings"][0]
    assert top["evidence"]["hot_symbol"]["symbol"] == "tizen_hot"
    assert top["ownership"] == "owned"
    assert top["actionability"] == "actionable"
    assert top["code_anchors"][0]["file"] == "src/tizen_hot.c"
    assert top["code_anchors"][0]["anchor_confidence"] >= 0.7
    assert top["code_anchors"][0]["resolution_method"] == "addr2line"

    assert document["target"]["platform"]["os"] == "tizen"
    assert document["target"]["platform"]["arch"] == "aarch64"
    assert document["profiling"]["callgraph_mode"] == "dwarf"

    mapping = document["tizen"]["path_mapping"][0]
    assert mapping["target_path"] == "/usr/lib/liba3demo.so"
    assert mapping["host_path"].endswith("sysroot/usr/lib/liba3demo.so")
    assert mapping["debug_path"].endswith("debuginfo/.build-id/ab/cdef1234567890.debug")
    assert mapping["source_path"] == "src/tizen_hot.c"
    assert analysis["tizen"]["backend"] == "ssh"

    by_symbol = {
        finding["evidence"]["hot_symbol"]["symbol"]: finding
        for finding in document["findings"]
    }
    third_party = by_symbol["g_signal_emit"]
    assert third_party["ownership"] == "third-party"
    assert third_party["actionability"] == "actionable"
    assert third_party["attribution_anchor"]["symbol"] == "tizen_hot"
    assert third_party["attribution_anchor"]["anchor_confidence"] >= 0.7
