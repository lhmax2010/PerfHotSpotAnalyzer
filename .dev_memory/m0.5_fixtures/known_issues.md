# M0.5 Known Issues

- M0.5 was branched from `stage/m0-schema` because `main` had not yet received
  M0. Review/merge order should preserve M0 before M0.5.
- Fixtures are hand-authored normalized contract examples, not outputs from real
  profilers or parsers. Parser-backed fixture generation belongs to A/B
  milestones.
- The low-confidence generic-llm fixture is valid as data, but Gate downgrade
  behavior is not implemented until B milestones.
- No coverage report is configured yet; M0.5 DoD focuses on fixture pass/reject
  behavior.
- `tools/check_no_llm_sdk_imports.py` remains as a Python helper for tests, while
  CI uses the v1.0.6 grep shell script `tools/check_no_llm_sdk_imports.sh`.
- The capture bundle fixture uses a small placeholder `perf.data`; the
  `perf-script.txt` content is the meaningful host-symbolization sample for
  M0.5.
