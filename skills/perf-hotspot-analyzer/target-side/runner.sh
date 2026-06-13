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
TARGET_HAS_STACKCOLLAPSE="${11:-false}"

mkdir -p "${OUTPUT_DIR}"
EXEC_LOG="${OUTPUT_DIR}/exec.log"
: > "${EXEC_LOG}"
TARGET_PID_FILE="${OUTPUT_DIR}/target.pid"

log_cmd() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "${EXEC_LOG}"
}

run_logged() {
  log_cmd "$*"
  "$@" >> "${EXEC_LOG}" 2>&1
}

run_timed() {
  label="$1"
  shift
  started_s="$(date +%s)"
  log_cmd "start ${label}: $*"
  "$@" >> "${EXEC_LOG}" 2>&1
  status="$?"
  ended_s="$(date +%s)"
  log_cmd "finish ${label}: status=${status} elapsed_s=$((ended_s - started_s))"
  return "${status}"
}

run_redirect_timed() {
  label="$1"
  output="$2"
  shift 2
  started_s="$(date +%s)"
  log_cmd "start ${label}: $* > ${output}"
  "$@" > "${output}" 2>> "${EXEC_LOG}"
  status="$?"
  ended_s="$(date +%s)"
  log_cmd "finish ${label}: status=${status} elapsed_s=$((ended_s - started_s))"
  return "${status}"
}

write_unavailable_file() {
  path="$1"
  reason="$2"
  printf '# unavailable: %s\n' "${reason}" > "${path}"
  log_cmd "warning: ${reason}"
}

copy_proc_maps() {
  target_pid="$1"
  if [[ -n "${target_pid}" && -r "/proc/${target_pid}/maps" ]]; then
    if cp "/proc/${target_pid}/maps" "${OUTPUT_DIR}/proc-${target_pid}-maps" 2>> "${EXEC_LOG}"; then
      return 0
    fi
  fi
  write_unavailable_file "${OUTPUT_DIR}/proc-${target_pid:-unknown}-maps" "unable to read /proc/${target_pid:-unknown}/maps for target process"
  return 1
}

write_kallsyms() {
  if [[ -r /proc/kallsyms ]]; then
    if cp /proc/kallsyms "${OUTPUT_DIR}/kallsyms" 2>> "${EXEC_LOG}" && [[ -s "${OUTPUT_DIR}/kallsyms" ]]; then
      return 0
    fi
    write_unavailable_file "${OUTPUT_DIR}/kallsyms" "unable to copy non-empty /proc/kallsyms; check perf_event_paranoid or root permissions"
    return 1
  fi
  write_unavailable_file "${OUTPUT_DIR}/kallsyms" "/proc/kallsyms is not readable; check perf_event_paranoid or root permissions"
  return 1
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

if [[ "${TARGET_KIND}" == "service" ]]; then
  service_pid="$(systemctl show -p MainPID --value "${TARGET_VALUE}" 2>> "${EXEC_LOG}" || printf 0)"
  if [[ -z "${service_pid}" || "${service_pid}" == "0" ]]; then
    service_pid="$(pidof "${TARGET_VALUE}" 2>> "${EXEC_LOG}" | awk '{print $1}' || true)"
  fi
  if [[ -z "${service_pid}" || "${service_pid}" == "0" ]]; then
    printf 'unable to resolve service pid for %s\n' "${TARGET_VALUE}" >&2
    exit 2
  fi
  TARGET_KIND="pid"
  TARGET_VALUE="${service_pid}"
fi

if [[ "${TARGET_KIND}" == "pid" ]]; then
  printf '%s\n' "${TARGET_VALUE}" > "${TARGET_PID_FILE}"
  copy_proc_maps "${TARGET_VALUE}" || true
  record_args+=("-p" "${TARGET_VALUE}" "--" "sleep" "${DURATION_S}")
elif [[ "${TARGET_KIND}" == "command" ]]; then
  record_args+=(
    "--"
    "env"
    "PERF_SKILL_OUTPUT_DIR=${OUTPUT_DIR}"
    "PERF_SKILL_TARGET_COMMAND=${TARGET_VALUE}"
    "bash"
    "-lc"
    'target_pid=$$; printf "%s\n" "${target_pid}" > "${PERF_SKILL_OUTPUT_DIR}/target.pid"; (for attempt in 1 2 3 4 5; do if [[ -r "/proc/${target_pid}/maps" ]]; then cp "/proc/${target_pid}/maps" "${PERF_SKILL_OUTPUT_DIR}/proc-${target_pid}-maps" 2>/dev/null && exit 0; fi; sleep 0.1; done) & eval "exec ${PERF_SKILL_TARGET_COMMAND}"'
  )
else
  printf 'unsupported target kind for perf runner: %s\n' "${TARGET_KIND}" >&2
  exit 2
fi

run_timed perf-record "${record_args[@]}"

script_cmd=("${PERF_PATH}" script "-i" "${OUTPUT_DIR}/perf.data" "-F" "comm,pid,tid,time,ip,sym,dso")
run_redirect_timed perf-script "${OUTPUT_DIR}/perf-script.txt" "${script_cmd[@]}"

report_cmd=("${PERF_PATH}" report "--stdio" "-i" "${OUTPUT_DIR}/perf.data")
run_redirect_timed perf-report "${OUTPUT_DIR}/perf-report.txt" "${report_cmd[@]}" || true

buildid_cmd=("${PERF_PATH}" buildid-list "-i" "${OUTPUT_DIR}/perf.data")
run_redirect_timed perf-buildid-list "${OUTPUT_DIR}/dso-list.txt" "${buildid_cmd[@]}" || true
if [[ ! -s "${OUTPUT_DIR}/dso-list.txt" ]]; then
  log_cmd "fallback readelf -n over mapped DSOs > dso-list.txt"
  maps_pid=""
  if [[ -s "${TARGET_PID_FILE}" ]]; then
    maps_pid="$(cat "${TARGET_PID_FILE}" 2>/dev/null || true)"
  fi
  maps_source="${OUTPUT_DIR}/proc-${maps_pid}-maps"
  if [[ -n "${maps_pid}" && -r "${maps_source}" ]]; then
    awk '{print $6}' "${maps_source}" 2>/dev/null | sort -u | while read -r dso; do
      [[ -r "${dso}" ]] || continue
      build_id="$(readelf -n "${dso}" 2>/dev/null | awk '/Build ID:/ {print $3; exit}')"
      [[ -n "${build_id}" ]] && printf '%s %s\n' "${build_id}" "${dso}"
    done > "${OUTPUT_DIR}/dso-list.txt" || true
  else
    log_cmd "warning: no target proc maps available for readelf build-id fallback"
  fi
fi

write_kallsyms || true

target_maps_pid=""
if [[ -s "${TARGET_PID_FILE}" ]]; then
  target_maps_pid="$(cat "${TARGET_PID_FILE}" 2>/dev/null || true)"
fi
if [[ -n "${target_maps_pid}" && ! -s "${OUTPUT_DIR}/proc-${target_maps_pid}-maps" ]]; then
  copy_proc_maps "${target_maps_pid}" || true
elif [[ -z "${target_maps_pid}" ]]; then
  write_unavailable_file "${OUTPUT_DIR}/proc-unknown-maps" "target pid was not recorded; cannot capture target maps"
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

if [[ "${TARGET_HAS_STACKCOLLAPSE}" == "true" ]] && command -v stackcollapse-perf.pl >/dev/null 2>&1; then
  log_cmd "stackcollapse-perf.pl < perf-script.txt > out.folded"
  stackcollapse-perf.pl "${OUTPUT_DIR}/perf-script.txt" > "${OUTPUT_DIR}/out.folded" 2>> "${EXEC_LOG}" || : > "${OUTPUT_DIR}/out.folded"
else
  : > "${OUTPUT_DIR}/out.folded"
fi
log_cmd "capture complete"
