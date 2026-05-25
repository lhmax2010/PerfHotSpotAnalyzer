# Codex 启动 Prompt

> 本文件是 Codex 的启动入口。工作纪律的完整定义在 `docs/DESIGN.md` 第二部分（工程化）与第三部分（实施）；本文件只负责"如何开机"。
> 同样的内容建议复制一份到仓库根目录 `AGENTS.md`，让 Codex 每个 task 自动加载常驻协议。

---

## 你的角色

你是 Codex，按 `docs/DESIGN.md`（实施唯一基线）实现「性能优化 Skill 套件」：两个独立 skill（`perf-hotspot-analyzer`、`perf-suggestion-patch`）+ 一个编排器 `perf-optimization-pipeline`。目标仓库 `https://github.com/lhmax2010/PerfHotSpotAnalyzer`。

## 最高原则

1. **不扩范围**：严格按 DESIGN 的 v1 边界（§1.3 非目标、§14）。延后项只在 schema 留槽，不实现。
2. **不自由发挥**：DESIGN 某处不可实现或矛盾时，**停下**，写 `.dev_memory/<stage>/decisions.md`，在 `current.yaml` 标 BLOCKED，提方案等人确认，不静默改设计。
3. **两类提交别混**：把**套件源码**提交到本仓库是正常 git；skill **运行时生成的补丁**永远只产出 `.patch`/advisory，**绝不自动 apply/commit/push 到被测仓库**。
4. **每阶段自包含**：代码 + 测试 + 真机 guide + dev_memory + 日志 + git tag + review 包必须同时齐备才算完成（DoD 见 DESIGN §10.5）。

## 每阶段 8 步循环（严格执行，不跳步）

```
1 RESUME    读 .dev_memory/current.yaml（+ 对应 <stage>/memory.md）确认当前阶段与 Next。
2 BRANCH    git checkout -b stage/<stage-id>（基于已 review 合入的 main）。
3 IMPLEMENT 按 DESIGN 实现本阶段。
4 TRACE     按 DESIGN §11 边写边埋 tracing（含每条 Gate 判定）。
5 TEST      按 DESIGN §10 写并跑 UT + 功能测试，全绿才继续，结果记入 test_report.md。
6 GUIDE     写 docs/test-guides/<stage-id>.md（真机 guide，DESIGN §10.6）。
7 MEMORY    更新 .dev_memory/<stage>/{memory.md,decisions.md,patches.yaml,known_issues.md} + current.yaml。
8 SHIP      写 docs/reviews/<stage-id>.md → commit（规范见 DESIGN §9.3）→ tag stage-<id>-done
            → push 分支 → 回复"阶段 <id> 完成，可 review"，然后停。
```

> 每阶段做完即停，等用户 review/合入 main 后再起下一阶段（用户要逐阶段给其他 AI review）。

## 里程碑顺序（DESIGN §14）

```
M0 → M0.5 →（A1→A2→A3）∥（B1→B2→B3）→ M-final → M-integ
```
A 线、B 线可并行（双 skill 独立）；A3（Tizen 交叉符号化）非阻塞，放最后。

## 现在开始

1. 完整阅读 `docs/DESIGN.md`。
2. 建好仓库骨架（DESIGN §13）+ 初始化 `.dev_memory/current.yaml`（阶段全 TODO）。
3. 进入 **M0**，按 8 步循环执行。
4. M0 完成后停下，报告"M0 完成，可 review"，等我反馈再继续 M0.5。

> 记住：慢就是快。每阶段把记忆、测试、日志、guide、review 包做扎实，比快速堆功能重要——这套东西要反复换 AI 接手、要在真机验证、要逐阶段被 review。
