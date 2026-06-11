from __future__ import annotations

import importlib.util
import json
import sys
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
