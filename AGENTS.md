# AGENTS.md

> 本文件是常驻协议，任何 AI/Codex 在本仓库每个 task 开始时都应先读它。

## 开工前必读
1. `docs/DESIGN.md` — **唯一实施基线**（v1.0.2，已冻结）。
2. `docs/CODEX_PROMPT.md` — 启动 prompt 与每阶段 8 步循环的完整定义。
3. `.dev_memory/current.yaml` — 当前进度指针（接手/续作的入口）。

## 不可违背的硬规则（详见 DESIGN §1.3 / §13.1）
- 不扩范围：只做当前 milestone 与 DESIGN 的 v1 边界；v1.1/v2 backlog 只在 schema 留槽。
- **任何 Python 代码不得调用 LLM API**；诊断/方案推理由宿主 Agent 提供。
- 运行时生成的补丁**只建议，绝不自动 apply/commit/push** 到被测仓库。
- v1：`measured_impact` 恒 null、`validation_status` 恒 not-run、`advisory-only` 不出 diff。
- CLI 输出前必过 `common/schema_validate.py`（含跨字段语义校验），不得绕过。
- x86 fixture 主链通过前不碰 Tizen 真机逻辑（A3 排最后）。
- DESIGN 有歧义/不可实现 → 停下记 `.dev_memory/<stage>/decisions.md` 等确认，不静默重解释。

## 每阶段工作循环（摘要，完整见 CODEX_PROMPT.md）
RESUME（读 current.yaml）→ BRANCH（stage/<id>）→ IMPLEMENT → TRACE → TEST（UT+功能，全绿）→ GUIDE（真机）→ MEMORY（dev_memory）→ SHIP（commit+tag+push+review 包，然后**停下等 review**）。

## 区分两类提交
- 把**套件源码**提交到本仓库 = 正常 git。
- skill **运行时产出的补丁** = 只写 `.patch`/advisory，永不自动落到用户代码。
