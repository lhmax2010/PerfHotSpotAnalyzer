# M-final Known Issues

- The workflow does not apply patches, run validation commands from patch
  verification plans, commit user code, or push user branches.  This is a v1
  guardrail, not a bug.
- Live device capture is not exercised by M-final CI; full-mode functional tests
  use pre-captured bundles.
- Cline and Compiling Agent integration remain M-integ scope.
