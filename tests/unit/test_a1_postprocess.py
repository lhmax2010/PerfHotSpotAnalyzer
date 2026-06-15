from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POSTPROCESS_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "postprocess.py"
)


def load_postprocess_module():
    spec = importlib.util.spec_from_file_location("a1_postprocess", POSTPROCESS_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_repo_sources(root: Path) -> None:
    src = root / "src"
    src.mkdir()
    (src / "slow_loop.c").write_text(
        """
        int decode_block(int n) {
          return n + 1;
        }

        int my_element_chain(int n) {
          return decode_block(n);
        }

        int gst_my_element_loop(int n) {
          return my_element_chain(n);
        }
        """,
        encoding="utf-8",
    )


def write_ownership(root: Path) -> Path:
    config = root / ".perf-skill"
    config.mkdir()
    path = config / "ownership.yaml"
    path.write_text(
        """
        owned_build_id_sources: []
        owned_paths:
          - /usr/lib64/myplugin/*.so*
          - /tmp/x86-hotspot/slow-loop
        third_party_paths:
          - /usr/lib64/libg*.so*
        system_paths:
          - /lib64/libc-*.so*
          - "[kernel.kallsyms]"
        attribution_strategy: nearest-to-hotspot
        """,
        encoding="utf-8",
    )
    return path


def write_bundle(bundle: Path) -> None:
    bundle.mkdir()
    (bundle / "perf-script.txt").write_text(
        """
        demo 4242/4242 1.0: 7f0012345678 g_signal_emit+0x2a (/usr/lib64/libgobject-2.0.so.0)
          7f0012345678 g_signal_emit+0x2a (/usr/lib64/libgobject-2.0.so.0)
          7f0011112244 my_element_chain+0x44 (/usr/lib64/myplugin/libdemo-plugin.so)
          7f0011111020 gst_my_element_loop+0x20 (/usr/lib64/myplugin/libdemo-plugin.so)
        demo 4242/4242 1.1: 7f0012345678 g_signal_emit+0x2a (/usr/lib64/libgobject-2.0.so.0)
          7f0012345678 g_signal_emit+0x2a (/usr/lib64/libgobject-2.0.so.0)
          7f0011112244 my_element_chain+0x44 (/usr/lib64/myplugin/libdemo-plugin.so)
        demo 4242/4242 1.2: 7f0011113300 decode_block+0x18 (/usr/lib64/myplugin/libdemo-plugin.so)
          7f0011113300 decode_block+0x18 (/usr/lib64/myplugin/libdemo-plugin.so)
          7f0011112244 my_element_chain+0x44 (/usr/lib64/myplugin/libdemo-plugin.so)
        """,
        encoding="utf-8",
    )
    for name in [
        "perf.data",
        "out.folded",
        "perf-report.txt",
        "kallsyms",
        "exec.log",
        "proc-4242-maps",
    ]:
        (bundle / name).write_text("fixture\n", encoding="utf-8")
    (bundle / "dso-list.txt").write_text(
        "\n".join(
            [
                "3f2a1dbe /usr/lib64/myplugin/libdemo-plugin.so",
                "8a7c55f0 /usr/lib64/libgobject-2.0.so.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (bundle / "run-context.json").write_text(
        json.dumps({"cpu_governor": "performance", "affinity": "0-3", "thermal_state": "unknown"}),
        encoding="utf-8",
    )
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "capture-bundle/v1",
                "backend": "local",
                "device": {"name": "host", "host": "host", "arch": "x86_64"},
                "capture_job": "capture-job.yaml",
                "target": {
                    "kind": "pid",
                    "pid": 4242,
                    "cmdline": "./slow-loop",
                    "service": None,
                    "commit": "abc123",
                },
                "perf": {
                    "events": ["cycles"],
                    "freq_hz": 999,
                    "callgraph_mode": "fp",
                    "duration_s": 2,
                    "repeat": 1,
                    "warmup": 0,
                },
                "run_context": {
                    "cpu_governor": "performance",
                    "affinity": "0-3",
                    "thermal_state": "unknown",
                },
                "artifacts": {
                    "perf_data": "perf.data",
                    "perf_script": "perf-script.txt",
                    "folded": "out.folded",
                    "perf_report": "perf-report.txt",
                    "kallsyms": "kallsyms",
                    "proc_maps": "proc-4242-maps",
                    "dso_list": "dso-list.txt",
                    "run_context": "run-context.json",
                    "exec_log": "exec.log",
                },
                "provenance": {
                    "generated_by": "test",
                    "version": "1.0.0",
                    "timestamp": "2026-06-11T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )


def test_parse_perf_script_uses_symbol_after_header_colon(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    script = tmp_path / "perf-script.txt"
    script.write_text(
        "demo 4242/4242 1.0: 7f0012345678 g_signal_emit+0x2a (/usr/lib64/libgobject-2.0.so.0)\n",
        encoding="utf-8",
    )

    samples = postprocess.parse_perf_script(script)

    assert samples[0].frames[0].symbol == "g_signal_emit"
    assert samples[0].frames[0].dso == "/usr/lib64/libgobject-2.0.so.0"


def test_classify_ownership_covers_owned_third_party_system_unknown(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    profile = postprocess.load_ownership_profile(write_ownership(tmp_path))

    assert postprocess.classify_ownership(
        "/usr/lib64/myplugin/libdemo-plugin.so", None, profile
    ).ownership == "owned"
    assert postprocess.classify_ownership(
        "/usr/lib64/libgobject-2.0.so.0", None, profile
    ).ownership == "third-party"
    assert postprocess.classify_ownership("/lib64/libc-2.35.so", None, profile).ownership == "system"
    assert postprocess.classify_ownership("/opt/mystery.so", None, profile).ownership == "unknown"


def test_select_attribution_frame_uses_nearest_owned_to_hotspot(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    profile = postprocess.load_ownership_profile(write_ownership(tmp_path))
    frames = [
        postprocess.Frame("g_signal_emit", "/usr/lib64/libgobject-2.0.so.0", ownership="third-party"),
        postprocess.Frame("my_element_chain", "/usr/lib64/myplugin/libdemo-plugin.so", ownership="owned"),
        postprocess.Frame("gst_my_element_loop", "/usr/lib64/myplugin/libdemo-plugin.so", ownership="owned"),
    ]

    selected = postprocess.select_attribution_frame(frames, profile)

    assert selected.symbol == "my_element_chain"


def test_postprocess_bundle_resolves_attribution_and_owned_anchor(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    write_repo_sources(tmp_path)
    ownership = write_ownership(tmp_path)
    bundle = tmp_path / "bundle"
    write_bundle(bundle)

    analysis = postprocess.postprocess_bundle(
        bundle_dir=bundle,
        repo_root=tmp_path,
        ownership_path=ownership,
        top_n=2,
    )

    top = analysis["hotspots"][0]
    assert top["hot_frame"]["symbol"] == "g_signal_emit"
    assert top["ownership"] == "third-party"
    assert top["actionability"] == "actionable"
    assert top["attribution_anchor"]["symbol"] == "my_element_chain"
    assert top["attribution_anchor"]["anchor_confidence"] == 0.80

    second = analysis["hotspots"][1]
    assert second["hot_frame"]["symbol"] == "decode_block"
    assert second["ownership"] == "owned"
    assert second["code_anchor"]["symbol"] == "decode_block"
    assert second["actionability"] == "actionable"


def test_third_party_stack_without_owned_frame_is_not_actionable(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    profile = postprocess.load_ownership_profile(write_ownership(tmp_path))
    samples = [
        postprocess.StackSample(
            frames=[
                postprocess.Frame("g_signal_emit", "/usr/lib64/libgobject-2.0.so.0", ownership="third-party"),
                postprocess.Frame("g_main_context_iterate", "/usr/lib64/libglib-2.0.so.0", ownership="third-party"),
            ]
        )
    ]

    hotspots = postprocess.analyze_hotspots(
        samples,
        profile=profile,
        repo_root=tmp_path,
        total_samples=1,
        top_n=1,
    )

    assert hotspots[0].actionability == "not-actionable"
    assert hotspots[0].actionability_reason == "no owned frame in callgraph"


def test_nearest_to_entry_attribution_strategy_selects_outer_owned_frame(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    profile = postprocess.load_ownership_profile(write_ownership(tmp_path))
    profile = postprocess.OwnershipProfile(
        owned_build_id_sources=profile.owned_build_id_sources,
        owned_paths=profile.owned_paths,
        third_party_paths=profile.third_party_paths,
        system_paths=profile.system_paths,
        attribution_strategy="nearest-to-entry",
    )
    frames = [
        postprocess.Frame("g_signal_emit", "/usr/lib64/libgobject-2.0.so.0", ownership="third-party"),
        postprocess.Frame("my_element_chain", "/usr/lib64/myplugin/libdemo-plugin.so", ownership="owned"),
        postprocess.Frame("gst_my_element_loop", "/usr/lib64/myplugin/libdemo-plugin.so", ownership="owned"),
    ]

    selected = postprocess.select_attribution_frame(frames, profile)

    assert selected.symbol == "gst_my_element_loop"


def test_unknown_hotspot_is_informational(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    profile = postprocess.load_ownership_profile(write_ownership(tmp_path))
    samples = [
        postprocess.StackSample(
            frames=[
                postprocess.Frame("mystery_hot", "/opt/unknown/libmystery.so", ownership="unknown"),
            ]
        )
    ]

    hotspots = postprocess.analyze_hotspots(
        samples,
        profile=profile,
        repo_root=tmp_path,
        total_samples=1,
        top_n=1,
    )

    assert hotspots[0].actionability == "informational"
    assert hotspots[0].actionability_reason == "unknown hotspot ownership"


def test_parse_dso_build_ids_maps_paths(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    dso_list = tmp_path / "dso-list.txt"
    dso_list.write_text(
        "1111aaaa /tmp/x86-hotspot/slow-loop\n2222bbbb /usr/lib64/libgobject-2.0.so.0\n",
        encoding="utf-8",
    )

    assert postprocess.parse_dso_build_ids(dso_list) == {
        "/tmp/x86-hotspot/slow-loop": "1111aaaa",
        "/usr/lib64/libgobject-2.0.so.0": "2222bbbb",
    }


def test_find_source_anchor_uses_compile_db_index_for_large_source_tree(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    source_root = tmp_path / "ffmpeg"
    source_root.mkdir()
    for idx in range(450):
        (source_root / f"unused_{idx}.c").write_text(
            f"int unused_helper_{idx}(int n) {{ return n + {idx}; }}\n",
            encoding="utf-8",
        )
    target = source_root / "libavcodec" / "decode.c"
    target.parent.mkdir()
    target.write_text(
        "int ffmpeg_decode_hot_path(int n) { return n * 2; }\n",
        encoding="utf-8",
    )
    (tmp_path / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(target.parent),
                    "command": "cc -c decode.c",
                    "file": str(target),
                }
            ]
        ),
        encoding="utf-8",
    )

    started = time.monotonic()
    anchor = postprocess.find_source_anchor(
        "ffmpeg_decode_hot_path",
        tmp_path,
        dso="/usr/lib/libavcodec.so",
    )
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert anchor is not None
    assert anchor["file"] == "ffmpeg/libavcodec/decode.c"
    assert anchor["resolution_method"] == "compile-db"
    assert anchor["anchor_confidence"] == 0.75


def test_find_source_anchor_uses_large_ctags_without_reopening_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    postprocess = load_postprocess_module()
    tags_lines = ["!_TAG_FILE_FORMAT\t2\t/extended format/"]
    tags_lines.extend(
        f"unused_symbol_{idx}\tlibavcodec/unused_{idx}.c\t{idx + 1};\"\tf"
        for idx in range(8000)
    )
    tags_lines.append("ffmpeg_decode_hot_path\tlibavcodec/decode.c\t123;\"\tf")
    (tmp_path / "tags").write_text("\n".join(tags_lines) + "\n", encoding="utf-8")

    def forbidden_source_scan(symbol: str, path: Path):
        raise AssertionError(f"ctags lookup reopened source file {path} for {symbol}")

    monkeypatch.setattr(postprocess, "_find_symbol_in_file", forbidden_source_scan)

    started = time.monotonic()
    anchor = postprocess.find_source_anchor(
        "ffmpeg_decode_hot_path",
        tmp_path,
        dso="/usr/lib/libavcodec.so",
    )
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert anchor is not None
    assert anchor["file"] == "libavcodec/decode.c"
    assert anchor["line_start"] == 123
    assert anchor["resolution_method"] == "ctags"


def test_find_source_anchor_uses_ctags_pattern_line_field(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    (tmp_path / "tags").write_text(
        'pattern_symbol\tlibavcodec/pattern.c\t/^int pattern_symbol(int n)$/;"\tf\tline:77\n',
        encoding="utf-8",
    )

    anchor = postprocess.find_source_anchor(
        "pattern_symbol",
        tmp_path,
        dso="/usr/lib/libavcodec.so",
    )

    assert anchor is not None
    assert anchor["file"] == "libavcodec/pattern.c"
    assert anchor["line_start"] == 77
    assert "pattern address" in anchor["evidence"]


def test_find_source_anchor_resolves_pattern_only_ctags_to_real_line(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    source = tmp_path / "libavcodec" / "decode.c"
    source.parent.mkdir()
    source.write_text(
        "\n".join(
            [
                "int helper_one(int n) { return n; }",
                "int helper_two(int n) { return n + 1; }",
                "",
                "int ffmpeg_decode_hot_path(int n) { return n * 2; }",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "tags").write_text(
        'ffmpeg_decode_hot_path\tlibavcodec/decode.c\t/^int ffmpeg_decode_hot_path(int n) { return n * 2; }$/;"\tf\n',
        encoding="utf-8",
    )

    anchor = postprocess.find_source_anchor(
        "ffmpeg_decode_hot_path",
        tmp_path,
        dso="/usr/lib/libavcodec.so.62.11.100",
    )

    assert anchor is not None
    assert anchor["file"] == "libavcodec/decode.c"
    assert anchor["line_start"] == 4
    assert "pattern resolved" in anchor["evidence"]


def test_find_source_anchor_invalid_symbols_skip_bounded_search(tmp_path: Path, monkeypatch) -> None:
    postprocess = load_postprocess_module()

    def forbidden_search(symbol: str, root: Path, *, dso: str):
        raise AssertionError(f"invalid symbol reached bounded search: {symbol}")

    monkeypatch.setattr(postprocess, "_bounded_source_search", forbidden_search)

    for symbol in ["", "[unknown]", "[vdso]", "[kernel.kallsyms]", "0x7f001234", "7f001234abcd"]:
        assert postprocess.find_source_anchor(symbol, tmp_path, dso="/usr/lib/libavcodec.so") is None


def test_find_source_anchor_fallback_prefers_dso_directory_on_large_tree(tmp_path: Path) -> None:
    postprocess = load_postprocess_module()
    source_root = tmp_path / "ffmpeg"
    (source_root / "libavcodec").mkdir(parents=True)
    (source_root / "libavformat").mkdir()
    (source_root / "doc").mkdir()
    (source_root / "tests").mkdir()
    for idx in range(1200):
        (source_root / "libavformat" / f"format_{idx}.c").write_text(
            f"int format_helper_{idx}(int n) {{ return n; }}\n",
            encoding="utf-8",
        )
    for idx in range(300):
        (source_root / "doc" / f"doc_{idx}.c").write_text(
            f"int doc_helper_{idx}(int n) {{ return n; }}\n",
            encoding="utf-8",
        )
        (source_root / "tests" / f"test_{idx}.c").write_text(
            f"int test_helper_{idx}(int n) {{ return n; }}\n",
            encoding="utf-8",
        )
    (source_root / "libavcodec" / "000_decode.c").write_text(
        "int ffmpeg_decode_hot_path(int n) { return n * 2; }\n",
        encoding="utf-8",
    )

    started = time.monotonic()
    anchor = postprocess.find_source_anchor(
        "ffmpeg_decode_hot_path",
        tmp_path,
        dso="/usr/lib/libavcodec.so",
    )
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert anchor is not None
    assert anchor["file"] == "ffmpeg/libavcodec/000_decode.c"
    assert anchor["line_start"] == 1


def test_postprocess_large_unknown_and_repeated_asm_frames_is_bounded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    postprocess = load_postprocess_module()
    source_root = tmp_path / "ffmpeg"
    (source_root / "libavcodec").mkdir(parents=True)
    for idx in range(900):
        (source_root / "libavcodec" / f"unused_{idx}.c").write_text(
            f"int unused_{idx}(int n) {{ return n + {idx}; }}\n",
            encoding="utf-8",
        )
    ownership = write_ownership(tmp_path)
    bundle = tmp_path / "bundle"
    write_bundle(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["backend"] = "ssh"
    manifest["device"]["arch"] = "armv7l"
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    dso = "/usr/lib/libavcodec.so.62.11.100"
    (bundle / "dso-list.txt").write_text(f"abcd1234 {dso}\n", encoding="utf-8")
    lines: list[str] = []
    timestamp = 1.0
    for idx in range(2500):
        lines.append(f"ffmpeg 4242/4242 {timestamp:.4f}: 00000000 [unknown] ({dso})")
        timestamp += 0.0001
    for idx in range(300):
        lines.append(f"ffmpeg 4242/4242 {timestamp:.4f}: 00001000 ff_hevc_idct_neon ({dso})")
        timestamp += 0.0001
    (bundle / "perf-script.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    find_calls = 0
    original_find = postprocess._find_symbol_in_file

    def counted_find(symbol: str, path: Path):
        nonlocal find_calls
        find_calls += 1
        return original_find(symbol, path)

    monkeypatch.setattr(postprocess, "_find_symbol_in_file", counted_find)

    started = time.monotonic()
    analysis = postprocess.postprocess_bundle(
        bundle_dir=bundle,
        repo_root=tmp_path,
        ownership_path=ownership,
        top_n=5,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 30.0
    assert any(hotspot["hot_frame"]["symbol"] == "[unknown]" for hotspot in analysis["hotspots"])
    assert find_calls <= postprocess.SOURCE_SEARCH_FILE_LIMIT
