# Hotfix Realboard Analyze Correctness Known Issues

- Pattern-only ctags entries require the referenced source file to be available
  on the host. If the file is missing or the pattern cannot be located, the
  anchor is correctly omitted instead of returning a fabricated line.
- Hotspot output can exceed the CLI `--top-n` value because global top-N and
  owned top-N are both retained. This is intentional to keep actionable owned
  code visible under system-heavy profiles.
