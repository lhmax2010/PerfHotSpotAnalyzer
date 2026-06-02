#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -gt 0 ]]; then
  roots=("$@")
else
  roots=(common skills workflows cli mcp integrations)
fi

matches="$(
  grep -rnE '^[[:space:]]*(from|import)[[:space:]]+(openai|anthropic|google\.generativeai|cohere)\b' \
    "${roots[@]}" \
    --include='*.py' \
    --exclude-dir='tests' \
    --exclude-dir='__pycache__' \
    2>/dev/null || true
)"

if [[ -n "$matches" ]]; then
  printf '%s\n' "$matches"
  exit 1
fi
