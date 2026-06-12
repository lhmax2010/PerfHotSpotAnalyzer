from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POSTPROCESS_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "postprocess.py"
)
BUILD_REPORT_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "build_report.py"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_tizen_context_resolves_debug_file_and_source(monkeypatch, tmp_path: Path) -> None:
    postprocess = load_module("a3_postprocess_symbolize", POSTPROCESS_PATH)
    debug = tmp_path / "debug" / ".build-id" / "ab" / "cd1234.debug"
    debug.parent.mkdir(parents=True)
    debug.write_text("debug\n", encoding="utf-8")
    source = tmp_path / "src" / "tizen_hot.c"
    source.parent.mkdir()
    source.write_text("int tizen_hot(void) { return 7; }\n", encoding="utf-8")
    frame = postprocess.Frame("tizen_hot", "/usr/lib/libdemo.so", ip="0x40")

    monkeypatch.setattr(
        postprocess,
        "run_addr2line",
        lambda debug_path, ip: (str(source), 1),
    )

    context = postprocess.build_tizen_context(
        manifest={
            "backend": "ssh",
            "device": {
                "arch": "aarch64",
                "sysroot": str(tmp_path / "sysroot"),
                "debuginfo_roots": [str(tmp_path / "debug")],
            },
        },
        bundle_dir=tmp_path / "bundle",
        repo_root=tmp_path,
        samples=[postprocess.StackSample(frames=[frame])],
        dso_build_ids={"/usr/lib/libdemo.so": "abcd1234"},
    )

    assert context["path_mapping"][0]["debug_path"] == str(debug)
    assert context["path_mapping"][0]["source_path"] == "src/tizen_hot.c"
    assert frame.file == "src/tizen_hot.c"
    assert frame.line_start == 1


def test_anchor_from_frame_uses_addr2line_confidence(tmp_path: Path) -> None:
    postprocess = load_module("a3_postprocess_anchor", POSTPROCESS_PATH)
    frame = postprocess.Frame(
        "tizen_hot",
        "/usr/lib/libdemo.so",
        ip="0x40",
        file="src/tizen_hot.c",
        line_start=12,
        line_end=12,
    )

    anchor = postprocess.anchor_from_frame(frame, tmp_path)

    assert anchor["symbol"] == "tizen_hot"
    assert anchor["file"] == "src/tizen_hot.c"
    assert anchor["anchor_confidence"] == 0.85
    assert anchor["resolution_method"] == "addr2line"


def test_resolve_host_path_anchors_relative_paths_at_repo_root(tmp_path: Path) -> None:
    postprocess = load_module("a3_postprocess_paths", POSTPROCESS_PATH)

    assert (
        postprocess.resolve_host_path("sysroot/usr/lib", tmp_path)
        == tmp_path / "sysroot" / "usr" / "lib"
    )
    assert postprocess.resolve_host_path(tmp_path / "debug", tmp_path) == tmp_path / "debug"


def test_build_report_copies_tizen_block_and_platform(tmp_path: Path) -> None:
    build_report = load_module("a3_build_report", BUILD_REPORT_PATH)
    analysis = {
        "schema_version": "postprocess/v1",
        "bundle_dir": str(tmp_path / "bundle"),
        "device": {"arch": "aarch64"},
        "source_report": {
            "id": "perf-script",
            "path": "perf-script.txt",
            "source_format": "perf-script",
            "parser": "perf-script-callgraph",
            "confidence": 0.95,
        },
        "target": {"kind": "pid", "pid": 4242, "cmdline": "/usr/bin/demo", "commit": "abc"},
        "profiling": {"tool": "perf", "events": ["cycles"], "callgraph_mode": "dwarf"},
        "run_context": {"cpu_governor": "unknown", "repeat_count": 1, "warmup_count": 0},
        "tizen": {
            "path_mapping": [
                {
                    "target_path": "/usr/lib/libdemo.so",
                    "host_path": str(tmp_path / "sysroot" / "usr" / "lib" / "libdemo.so"),
                    "debug_path": str(tmp_path / "debug" / ".build-id" / "ab" / "cd.debug"),
                    "source_path": "src/tizen_hot.c",
                    "build_id": "abcd",
                }
            ]
        },
        "hotspots": [
            {
                "rank": 1,
                "samples": 3,
                "self_cpu_pct": 100.0,
                "hot_frame": {
                    "symbol": "tizen_hot",
                    "dso": "/usr/lib/libdemo.so",
                    "ownership": "owned",
                },
                "callers": [],
                "ownership": "owned",
                "actionability": "actionable",
                "actionability_reason": "addr2line resolved source",
                "code_anchor": {
                    "symbol": "tizen_hot",
                    "dso": "/usr/lib/libdemo.so",
                    "file": "src/tizen_hot.c",
                    "line_start": 1,
                    "line_end": 1,
                    "language": "c",
                    "anchor_confidence": 0.85,
                    "resolution_method": "addr2line",
                },
            }
        ],
    }

    document = build_report.build_performance_findings(analysis, repo_root=tmp_path)

    assert document["target"]["platform"]["os"] == "tizen"
    assert document["target"]["platform"]["arch"] == "aarch64"
    assert document["tizen"]["path_mapping"][0]["source_path"] == "src/tizen_hot.c"
