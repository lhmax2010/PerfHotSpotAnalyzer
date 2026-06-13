# Hotfix Tizen Real Board Decisions

## 1. Source Anchor Search Hangs On Large Repos

- Phenomenon: ffmpeg-scale repos with thousands of C files made postprocess
  appear hung while resolving each hot symbol.
- Root cause: `find_source_anchor` performed a full `repo_root.rglob` and
  per-line regex scan for every symbol.
- Fix: prefer `tags` and `compile_commands.json` symbol indexes, then use a
  bounded fallback search with DSO token prioritization, a per-symbol timeout,
  and file-count limits. Limit hits degrade confidence instead of hanging.
- Test: `test_find_source_anchor_uses_compile_db_index_for_large_source_tree`
  builds a 450-file source tree and asserts indexed anchoring completes quickly.

## 2. Python 3.10 Import Failure

- Phenomenon: host Python 3.10 failed immediately because `datetime.UTC` is
  Python 3.11+.
- Root cause: runtime modules imported `UTC` from `datetime` and
  `pyproject.toml` declared Python 3.11 minimum.
- Fix: replaced all runtime `datetime.UTC` use with `timezone.utc`, lowered the
  package minimum to Python 3.10, and added CI matrix coverage for 3.10/3.11.
- Test: `test_python310_compat.py` imports entrypoints and statically rejects
  `datetime.UTC`, `tomllib`, `typing.Self`, and `except*` in runtime sources.

## 3. YAML Loader Preference

- Phenomenon: real hosts had PyYAML 6.0.3, but code always used the minimal
  fallback parser.
- Root cause: runtime callers imported `common.simple_yaml.load_yaml` directly.
- Fix: added `common.yaml_loader` as a PyYAML-first facade and moved runtime
  callers to it while preserving `simple_yaml` as fallback.
- Test: `test_yaml_loader.py` covers PyYAML-preferred and fallback-only paths.

## 4. Tizen UEP Blocks Pushed Scripts

- Phenomenon: scripts executed from `/tmp` or `/opt/usr` failed with
  `[uep][bash] the file is NOT signed!!`.
- Root cause: capture pushed `runner.sh` to the remote bundle and executed that
  file path.
- Fix: added `DeviceRunner.shell_script()` and changed capture to stream
  `runner.sh` over stdin with `bash -s --`, so no unsigned remote script needs
  to execute from managed directories.
- Test: remote capture mock asserts only `capture-job.yaml` is pushed and
  `runner.sh` never appears in shell commands or remote paths.

## 5. Remote Workdir And Timeout Handling

- Phenomenon: profile `remote_workdir` and timeout needs were not reflected in
  the capture command path; `command + duration_s: 0` could under-budget the
  workload and perf-script step.
- Root cause: capture used fixed shell timeouts and a duration-based timeout
  formula that treated zero-duration command profiling as almost zero work.
- Fix: added profile/job timeout fields, used profile shell/copy timeouts, made
  the remote bundle path derive from profile `remote_workdir`, and split record
  versus perf-script timing in runner logs.
- Test: capture tests assert remote_workdir is the first runner argument,
  shell timeout values are honored, job overrides win, and duration-zero command
  profiling receives a real workload budget.

## 6. ARMv7 DWARF Perf Script Slowness

- Phenomenon: 50MB ARMv7 DWARF `perf.data` made target-side `perf script` take
  about two minutes, while frame-pointer callgraphs took seconds.
- Root cause: auto callgraph mode did not account for embedded ARM DWARF cost.
- Fix: `callgraph=auto` now prefers `fp` for ARMv7/armv7l/armv7hl/armv8l, and
  ARM embedded DWARF gets a larger independent perf-script timeout budget.
- Test: preflight and capture timeout tests cover armv7l auto-fp and larger
  dwarf script budgets.

## 7. Missing `armv7l` Schema Enum

- Phenomenon: real `uname -m` reported `armv7l`, rejected by capture and
  performance schemas.
- Root cause: schema arch enums only allowed `armv7`, `aarch64`, and `x86_64`.
- Fix: added `armv7l`, `armv7hl`, `armv8l`, and `i686` to schemas and matching
  report-generation allowlists; synchronized skill schema copies.
- Test: capture bundle and performance findings tests validate `armv7l`, and
  schema-copy SHA checking passes.

## 8. Empty/Wrong Bundle Metadata

- Phenomenon: `kallsyms` and `proc-<pid>-maps` were zero bytes; command-mode
  maps could come from perf/self rather than the ffmpeg process.
- Root cause: runner fell back to `/proc/self/maps` and silently truncated
  kallsyms/maps when permissions or process lifetime prevented reads.
- Fix: command mode writes `target.pid`, captures `/proc/<target_pid>/maps`
  while the process is alive, avoids proc-self fallback, and writes warning
  placeholders for unavailable kallsyms/maps.
- Test: a fake-perf runner test executes command mode and asserts
  `proc-<target_pid>-maps` exists, `target.pid` matches, no `proc-self-maps`
  exists, and kallsyms is non-empty or warning-filled.
