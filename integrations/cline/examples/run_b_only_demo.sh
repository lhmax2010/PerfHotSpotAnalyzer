#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT_DIR"

rm -rf out/cline-b-only
python3 -m perf_optimization_pipeline pipeline run \
  --config integrations/cline/examples/b-only-demo.yaml \
  --non-interactive

python3 -m perf_suggestion_patch validate \
  --input out/cline-b-only/b_run/patches.json \
  --document-type suggestion-patch \
  --output-dir out/cline-b-only/validate

printf '%s\n' "Cline B-only demo complete: out/cline-b-only/merged-report.md"
