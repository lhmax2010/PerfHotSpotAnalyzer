from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
INGEST_PATH = ROOT / "skills" / "perf-suggestion-patch" / "scripts" / "ingest.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("b2_ingest_anchor_search", INGEST_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_compile_db(repo_root: Path, source: Path) -> None:
    (repo_root / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(repo_root),
                    "file": str(source),
                    "command": f"cc -c {source}",
                }
            ]
        ),
        encoding="utf-8",
    )


def test_anchor_search_adds_benchmark_name_map_anchor(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    repo = tmp_path / "repo"
    bench_dir = repo / "bench"
    bench_dir.mkdir(parents=True)
    (bench_dir / "decode_bench.cc").write_text(
        "static void BM_Decode(benchmark::State& state) {}\nBENCHMARK(BM_Decode);\n",
        encoding="utf-8",
    )

    result = ingest.run_google_benchmark(
        FIXTURE_ROOT / "positive" / "02-google-benchmark-before-after" / "after.json",
        tmp_path / "out",
        baseline_report=(
            FIXTURE_ROOT / "positive" / "02-google-benchmark-before-after" / "before.json"
        ),
        repo_root=repo,
    )

    anchor = result.run_report["gate_decisions"][0]["effective_anchor"]
    assert anchor["resolution_method"] == "bench-name-map"
    assert anchor["anchor_confidence"] == 0.50
    assert anchor["file"] == "bench/decode_bench.cc"
    assert result.run_report["gate_decisions"][0]["reason"] == (
        "effective_anchor_confidence=0.5 < 0.70"
    )


def test_anchor_search_compile_db_upgrades_folded_hotspot_to_actionable(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "hot.c"
    source.write_text("int hot_symbol(int value) { return value + 1; }\n", encoding="utf-8")
    write_compile_db(repo, source)
    folded = tmp_path / "sample.folded"
    folded.write_text("root;worker;hot_symbol 11\n", encoding="utf-8")

    result = ingest.run_folded_stacks(folded, tmp_path / "out", repo_root=repo)

    decision = result.run_report["gate_decisions"][0]
    anchor = decision["effective_anchor"]
    assert anchor["resolution_method"] == "compile-db"
    assert anchor["anchor_confidence"] == 0.75
    assert anchor["file"] == "src/hot.c"
    assert decision["reason"] == "b1-advisory-only"


def test_anchor_search_generic_llm_deterministic_anchor_can_continue(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    raw_report = (
        FIXTURE_ROOT / "positive" / "05-low-confidence-generic-llm" / "freeform-report.txt"
    )
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "index.c"
    source.write_text("int maybe_lookup(int key) { return key; }\n", encoding="utf-8")
    write_compile_db(repo, source)
    paths = ingest.prepare_generic_llm_protocol(raw_report, output_dir=tmp_path, repo_root=repo)
    shutil.copyfile(
        FIXTURE_ROOT
        / "positive"
        / "05-low-confidence-generic-llm"
        / "performance-findings.json",
        paths.output_path,
    )

    result = ingest.run_generic_llm(raw_report, tmp_path, repo_root=repo)

    decision = result.run_report["gate_decisions"][0]
    assert decision["effective_anchor"]["resolution_method"] == "compile-db"
    assert decision["effective_anchor"]["anchor_confidence"] == 0.75
    assert "generic-llm-default-advisory" not in decision["reason"]
    assert "benchmark-latency-without-perf-budget" in decision["reason"]


def test_anchor_search_grep_anchor_stays_below_gate_threshold(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "hot.c"
    source.write_text("int grep_hot(int value) { return value; }\n", encoding="utf-8")
    folded = tmp_path / "sample.folded"
    folded.write_text("root;worker;grep_hot 5\n", encoding="utf-8")

    result = ingest.run_folded_stacks(folded, tmp_path / "out", repo_root=repo)

    decision = result.run_report["gate_decisions"][0]
    assert decision["effective_anchor"]["resolution_method"] == "grep"
    assert decision["effective_anchor"]["anchor_confidence"] == 0.65
    assert decision["reason"] == "effective_anchor_confidence=0.65 < 0.70"
