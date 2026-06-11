#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="$1"
PERF_PATH="$2"
TARGET_KIND="$3"
TARGET_VALUE="$4"
EVENTS="$5"
FREQ_HZ="$6"
CALLGRAPH_MODE="$7"
DURATION_S="$8"
REPEAT="$9"
WARMUP="${10}"

mkdir -p "${OUTPUT_DIR}"
EXEC_LOG="${OUTPUT_DIR}/exec.log"
: > "${EXEC_LOG}"

log_cmd() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "${EXEC_LOG}"
}

run_logged() {
  log_cmd "$*"
  "$@" >> "${EXEC_LOG}" 2>&1
}

record_args=("${PERF_PATH}" record "-F" "${FREQ_HZ}" "-e" "${EVENTS}" "-o" "${OUTPUT_DIR}/perf.data")
if [[ "${CALLGRAPH_MODE}" != "none" ]]; then
  record_args+=("-g" "--call-graph" "${CALLGRAPH_MODE}")
fi

for ((i = 0; i < WARMUP; i++)); do
  if [[ "${TARGET_KIND}" == "command" ]]; then
    log_cmd "warmup command ${i}: ${TARGET_VALUE}"
    bash -lc "${TARGET_VALUE}" >> "${EXEC_LOG}" 2>&1 || true
  fi
done

if [[ "${TARGET_KIND}" == "pid" ]]; then
  record_args+=("-p" "${TARGET_VALUE}" "--" "sleep" "${DURATION_S}")
elif [[ "${TARGET_KIND}" == "command" ]]; then
  record_args+=("--" "bash" "-lc" "${TARGET_VALUE}")
else
  printf 'unsupported target kind for A1 local runner: %s\n' "${TARGET_KIND}" >&2
  exit 2
fi

run_logged "${record_args[@]}"

script_cmd=("${PERF_PATH}" script "-i" "${OUTPUT_DIR}/perf.data" "-F" "comm,pid,tid,time,ip,sym,dso")
log_cmd "${script_cmd[*]} > perf-script.txt"
"${script_cmd[@]}" > "${OUTPUT_DIR}/perf-script.txt" 2>> "${EXEC_LOG}"

report_cmd=("${PERF_PATH}" report "--stdio" "-i" "${OUTPUT_DIR}/perf.data")
log_cmd "${report_cmd[*]} > perf-report.txt"
"${report_cmd[@]}" > "${OUTPUT_DIR}/perf-report.txt" 2>> "${EXEC_LOG}" || true

buildid_cmd=("${PERF_PATH}" buildid-list "-i" "${OUTPUT_DIR}/perf.data")
log_cmd "${buildid_cmd[*]} > dso-list.txt"
"${buildid_cmd[@]}" > "${OUTPUT_DIR}/dso-list.txt" 2>> "${EXEC_LOG}" || true

if [[ -r /proc/kallsyms ]]; then
  cp /proc/kallsyms "${OUTPUT_DIR}/kallsyms" 2>> "${EXEC_LOG}" || : > "${OUTPUT_DIR}/kallsyms"
else
  : > "${OUTPUT_DIR}/kallsyms"
fi

maps_pid="self"
if [[ "${TARGET_KIND}" == "pid" ]]; then
  maps_pid="${TARGET_VALUE}"
fi
if [[ -r "/proc/${maps_pid}/maps" ]]; then
  cp "/proc/${maps_pid}/maps" "${OUTPUT_DIR}/proc-${maps_pid}-maps" 2>> "${EXEC_LOG}" || : > "${OUTPUT_DIR}/proc-${maps_pid}-maps"
else
  cp /proc/self/maps "${OUTPUT_DIR}/proc-self-maps" 2>> "${EXEC_LOG}" || : > "${OUTPUT_DIR}/proc-self-maps"
fi

governor="unknown"
if [[ -r /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
  governor="$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || printf unknown)"
fi
affinity="$(taskset -pc $$ 2>/dev/null | sed 's/.*: //' || printf unknown)"

cat > "${OUTPUT_DIR}/run-context.json" <<JSON
{
  "cpu_governor": "${governor}",
  "affinity": "${affinity}",
  "thermal_state": "unknown",
  "repeat_count": ${REPEAT},
  "warmup_count": ${WARMUP},
  "target_has_stackcollapse": false
}
JSON

: > "${OUTPUT_DIR}/out.folded"
log_cmd "capture complete"
