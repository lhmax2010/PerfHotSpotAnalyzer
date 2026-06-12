from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cline_b_only_demo_script_runs_happy_path() -> None:
    script = ROOT / "integrations" / "cline" / "examples" / "run_b_only_demo.sh"

    result = subprocess.run(
        [str(script)],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    output_dir = ROOT / "out" / "cline-b-only"
    patches = json.loads((output_dir / "b_run" / "patches.json").read_text(encoding="utf-8"))
    run_report = json.loads((output_dir / "run-report.json").read_text(encoding="utf-8"))
    merged = (output_dir / "merged-report.md").read_text(encoding="utf-8")

    assert len(patches["patches"]) == 2
    assert run_report["gate_decisions"][0]["decision"] == "pass"
    assert "The workflow did not apply, commit, or push generated patches." in merged
