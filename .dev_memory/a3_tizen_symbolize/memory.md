# A3 Tizen Symbolize Memory

## Status

A3 is implemented on `stage/a3-tizen-symbolize`.

## Implemented

- `common/device_runner.py`
  - Implements `backend=ssh` through `ssh` and `scp`.
  - Implements `backend=sdb` through `sdb shell`, `sdb push`, and `sdb pull`.
  - Records backend command, return code, and elapsed time through tracing.
  - Adds clear remediation for ssh reachability, key denial, missing Tizen
    sshd/OpenSSH setup, `sdb devices`, timeouts, and target permissions.
- `skills/perf-hotspot-analyzer/scripts/capture.py`
  - Allows remote ssh/sdb capture using the same capture-job flow as local.
  - Pushes `runner.sh`, runs target-side capture, pulls the bundle, and derives
    `out.folded` on host when target-side stackcollapse is disabled.
  - Persists Tizen device metadata in `manifest.json`.
- `skills/perf-hotspot-analyzer/target-side/runner.sh`
  - Supports command, pid, and service targets.
  - Runs `perf record`, `perf stat`, `perf script`, `perf report`, and
    `perf buildid-list`.
  - Falls back to `readelf -n` for build IDs when needed.
- `skills/perf-hotspot-analyzer/scripts/postprocess.py`
  - Resolves Tizen build IDs against host debuginfo roots.
  - Maps target DSO paths through host sysroot.
  - Uses `perf-script.txt` as the primary source and `addr2line`/source fallback
    for file:line anchors.
  - Emits `tizen.path_mapping` in the postprocess document.
- `skills/perf-hotspot-analyzer/scripts/build_report.py`
  - Copies `tizen.path_mapping` into canonical `performance-findings.json`.
  - Marks Tizen reports as `target.platform.os=tizen`.
- `tests/fixtures/golden/live-perf/tizen-arm/`
  - Adds a CI-safe, pre-captured Tizen-style bundle with `perf-script.txt`,
    build-id list, sysroot/debuginfo samples, ownership profile, and source.
- `docs/test-guides/a3-tizen-symbolize.md`
  - Documents ssh primary capture, sdb fallback, Tizen sshd prerequisites,
    public-key setup, analysis/report commands, and feedback attachments.

## Handoff Notes

- The deterministic CI fixture is offline; it does not require a live Tizen
  board, local sshd, or `sdb`.
- The fixture debuginfo sample is a tiny host-built shared object with a
  deterministic build-id.  It exists only to validate build-id lookup and
  `addr2line` path-mapping behavior.
- Real Tizen/GBS sysroot and debuginfo roots should be absolute paths in the
  device profile.  Relative paths are resolved against `repo_root` for fixtures.
- No Python code imports or calls LLM SDKs.
- M-final remains blocked on review; do not continue workflow integration yet.
