# A1 Known Issues

- `ssh` and `sdb` backends intentionally raise `NotImplementedError`; they are A3 scope.
- Live perf capture is not run by default in CI because host/container perf permissions vary.  Use `PERF_SKILL_ENABLE_LIVE_PERF=1` for the manual smoke test.
- The checked-in `perf.data` in the x86 fixture is a placeholder; A1 deterministic CI analysis consumes `perf-script.txt` as the primary source per DESIGN v1.0.6.
- Source anchoring is conservative and only accepts unique C/C++ function-definition matches.
