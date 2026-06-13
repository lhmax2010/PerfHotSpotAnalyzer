# Hotfix Tizen Real Board Known Issues

- No known hotfix regressions at the time of writing.
- Live-board SSH/SDB behavior still depends on target image prerequisites:
  sshd, root/developer access, perf availability, and matching sysroot/debuginfo.
- ARMv7 DWARF is supported but intentionally discouraged for routine live
  profiling because target-side `perf script` can be very slow.
