# A2 Known Issues

- A2 does not map sections to source symbols; `code_anchors` remain absent for binary-size findings.
- Ownership is path-based for the current ELF.  If no ownership rule matches, actionable binary-size findings are downgraded to `informational`.
- `bloaty` is not integrated; `size -A` is used only in tests for cross-checking.
- Tizen/ssh/sdb transport remains A3 scope.
