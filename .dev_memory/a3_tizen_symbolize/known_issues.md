# A3 Known Issues

- CI does not contact a real Tizen board.  The deterministic fixture is offline,
  and live board validation is documented in `docs/test-guides/a3-tizen-symbolize.md`.
- The Tizen fixture debuginfo sample is host-built x86_64 with a deterministic
  build-id.  It validates host-side lookup and `addr2line` behavior, not target
  ISA decoding.
- Host `perf --symfs` fallback for decoding raw target `perf.data` is not fully
  exercised in CI because `perf-script.txt` is the v1.0.6 primary source.
- Workflow orchestration and integration with downstream agents remain M-final
  / M-integ scope.
