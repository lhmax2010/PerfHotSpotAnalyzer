#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${ROOT}/bin"

gcc -O2 -fno-omit-frame-pointer "${ROOT}/src/topn_sections.c" -o "${ROOT}/bin/topn.elf"
gcc -O2 -fno-omit-frame-pointer -DINFLATE_BYTES=2048 "${ROOT}/src/regression_sections.c" -o "${ROOT}/bin/before.elf"
gcc -O2 -fno-omit-frame-pointer -DINFLATE_BYTES=8192 "${ROOT}/src/regression_sections.c" -o "${ROOT}/bin/after.elf"
