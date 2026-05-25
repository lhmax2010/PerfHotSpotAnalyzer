# PerfHotSpotAnalyzer

一套面向 **Tizen / GBS 嵌入式** 场景的性能分析与优化建议 **Skill 套件**：从 `perf` 热点/体积分析，到把任意性能报告转成可评审的建议补丁。

> **状态**：设计已冻结（`docs/DESIGN.md` v1.0.2 实施基线），按 milestone 实施中。代码骨架由实施阶段 **M0** 建立。

---

## 这是什么

两个**相互独立**的 Skill + 一个编排器：

- **Skill A — `perf-hotspot-analyzer`**：用 Linux `perf` 定位 CPU 热点 + 静态扫描 ELF section/体积，结合源码诊断瓶颈，产出**结构化性能证据报告**（`performance-findings.json` + Markdown + 火焰图）。独立可用。
- **Skill B — `perf-suggestion-patch`**：吃**任意结合代码的性能/基准报告**（A 的报告、Google Benchmark、folded-stacks、自由格式…）+ 代码仓库，归一化 → 代码锚定 → 生成 **review 式建议补丁**（advisory-first，只建议不自动改）。独立可用，不依赖 A。
- **Workflow — `perf-optimization-pipeline`**：把 A→B 串起来的**编排器**（非 triggerable skill）。

两个 Skill 通过中立交换格式 `performance-findings` 解耦，互不 import，可各自独立迭代。

**核心安全约束**：`anchor_confidence` 是出 diff 的必要闸门（证据不足只给 advisory）；`expected_impact`（估计）与 `measured_impact`（实测）严格分离，v1 不编造收益；**生成的补丁只建议，绝不自动 apply/commit/push**。

---

## 文档

| 文档 | 作用 |
|------|------|
| **`docs/DESIGN.md`** | **唯一实施基线**（v1.0.2，已冻结）。架构、数据契约、测试、工程化、接入方案全在这里。 |
| `docs/CODEX_PROMPT.md` | Codex 启动 prompt（如何开机、每阶段 8 步循环）。 |
| `AGENTS.md` | 常驻协议指针，Codex 每个 task 自动加载。 |
| `docs/archive/` | v1~v3.1.1 演进稿，仅供决策追溯（可选添加）。 |

---

## 怎么开发

按 milestone 推进，**每阶段都要产出**：代码 + 单测/功能测试 + 真机测试 guide + `dev_memory`（含 patch 与改动理由）+ tracing 日志 + PR，并**停下供 review**。详见 `docs/DESIGN.md` 第二部分（工程化）与 §13.1 Implementation Guardrails。

里程碑顺序（A/B 两线可并行，Tizen 真机逻辑放最后）：

```
M0 schema/校验/骨架 → M0.5 golden fixtures →（A1→A2→A3）∥（B1→B2→B3）→ M-final workflow → M-integ 接入
```

实施者从 **M0** 开始：只建 `schemas/` + `common/schema_validate.py` + golden fixtures + tracing/CLI 骨架，先把契约钉死，再写业务逻辑。

---

## 仓库结构（规划，M0 由实施阶段建立）

```
PerfHotSpotAnalyzer/
├── README.md
├── AGENTS.md
├── docs/{DESIGN.md, CODEX_PROMPT.md, test-guides/, reviews/, archive/}
├── .dev_memory/{current.yaml, <stage>/...}
├── common/{tracing.py, schema_validate.py, cli_base.py}
├── skills/{perf-hotspot-analyzer/, perf-suggestion-patch/}
├── workflows/perf-optimization-pipeline/
├── cli/  mcp/  integrations/{cline/, compiling_agent/}
└── tests/{unit/, functional/, integration/, e2e/, fixtures/}
```

---

## 如何使用（规划）

三层调用面（CLI 为主 + SKILL.md + 可选 MCP），统一契约、统一 exit code，宿主无关；面向 **Cline** 与 **Compiling Agent** 运行。详见 `docs/DESIGN.md` §12。

---

## License

待定（建议开工前补 `LICENSE`）。
