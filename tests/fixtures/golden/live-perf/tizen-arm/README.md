# A3 Tizen ARM Fixture

This is a pre-captured, trimmed Tizen-style Capture Bundle used by CI. It keeps
the transport offline while preserving the A3 contract:

- backend is `ssh`
- target arch is `aarch64`
- `perf-script.txt` is the primary symbolization source
- `dso-list.txt` carries build-id entries
- `debuginfo/.build-id/...` and `sysroot/usr/lib/...` provide host-side mapping

The debuginfo sample is a tiny host-built shared object with a deterministic
build-id. It is intentionally small; the test only requires stable `addr2line`
resolution and path mapping behavior.
