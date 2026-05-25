# 性能优化 Skill 套件设计文档 v1.0.2

**版本**：v1.0.2（实施冻结版，整合 v1~v3.1.1 全部 review 意见 + 工程化要求）
**v1.0.2 修订**：附录 anchor_confidence 措辞同步、binary-size threshold 移出未决、generic-llm Gate 写成机器可实现形式、diff-ready/needs-review 对 verification_plan 的要求明确、schema_validate 增 source_ref 有效性与 benchmark-regression baseline 一致性校验。纯文字/语义一致性收口，无架构变更。
**v1.0.1 修订**：闸门措辞精确化、新增 `verification_plan`、跨字段语义校验（confidence 上限 / report_types 一致性）、binary-size-large v1 默认 threshold、generic-llm 二次锚定硬规则、Diagnose 改为宿主 Agent/LLM、common 共享边界、新增 Implementation Guardrails。无架构变更。
**目标读者**：实施者（Codex）、Review 协作 AI（ChatGPT / Claude / 其它）、最终用户
**仓库**：<https://github.com/lhmax2010/PerfHotSpotAnalyzer>

> **本文档是 Codex 实施的唯一基线。** v1~v3.1.1 的演进文档归档在 `docs/archive/`，仅供决策追溯。Codex 启动 prompt 见 `docs/CODEX_PROMPT.md`。

---

## 目录

**第一部分：核心设计**
- §1 设计哲学与原则
- §2 整体架构
- §3 Skill A：perf-hotspot-analyzer
- §4 Skill B：perf-suggestion-patch
- §5 Workflow：perf-optimization-pipeline（编排器，非 triggerable skill）
- §6 数据契约（performance-findings / suggestion-patch + 条件校验）
- §7 Tizen / GBS 专项

**第二部分：工程化**
- §8 开发产物管理（dev_memory）
- §9 GitHub 工作流
- §10 测试体系
- §11 可观测性（Tracing + Run Report）
- §12 Skill 接入方案（Cline + Compiling Agent）

**第三部分：实施**
- §13 文件目录结构
- §14 实施计划（按 milestone）
- §15 风险与未决问题
- §16 附录

---

# 第一部分：核心设计

## §1 设计哲学与原则

### 1.1 一句话设计哲学

> 让 skill 把性能报告变成**带可信代码锚点的证据**；LLM 只在证据足够时把证据变成**可评审的补丁建议**；证据不足就老实降级为 advisory。**可信、可降级、可评审，优先于"全自动优化"。**

### 1.2 设计原则

1. **双 Skill 独立**：A、B 互不 import，靠中立契约 `performance-findings` 解耦，各自可独立使用。
2. **可信证据优先于自动修改**：先把证据做稳，再让 LLM 出建议，自动改代码/自动证明收益放最后。
3. **接受任意报告，但只在锚点可信时出 diff**：`anchor_confidence`（≥0.7）是出 diff 的**必要闸门（必须通过）**，但**非充分条件**——最终是否出 diff 还受 finding kind、`patch_category`、`perf_budget`、语义风险共同约束（见 §4.1）。
4. **schema 管结构，Gate 管行为**：必填字段约束进 schema；降级/拒绝出 patch 的判断进 SKILL.md 的 Gate。
5. **确定性脚本做可复现的事**：采集、解析、折叠、评分、diff 组装、schema 校验全走脚本；LLM 只做诊断与方案设计。
6. **expected 与 measured 严格分离**：预期收益是带 confidence 的估计；实测收益只在真跑基准时填，绝不编造。
7. **每阶段可观测、可追溯、可接续**：dev_memory + tracing 保证换 AI/崩溃也能续接。
8. **schema 按完整愿景留槽，实现做 v1 子集**：到点只加实现、不改契约。
9. **默认安全**：不静默提权、不自动 apply/commit/push 生成的补丁、关键步骤过人工闸门。
10. **可接入**：CLI + SKILL.md + 可选 MCP 三层调用面，统一契约，宿主无关。

### 1.3 非目标

- 不自动 apply / commit / push **运行时生成的补丁**（只建议，由人评审）。
- 不内嵌或调用 LLM API（推理由宿主 agent 提供）。
- 不替代人工对优化方案的最终判断。
- 不在证据不足时强行出 diff（一律降级 advisory）。
- 不编造性能收益（`measured_impact` 仅在实测时填）。
- v1 不做：Memory Mapping finding、Go/Python/Java profiler 适配、外部 benchmark 专用 parser 长尾、设备上自动构建/测试/重测闭环（见 §14 路线图）。
- 不保证宿主 agent 不绕过 skill 直接乱改代码（agent 框架问题，免责）。

---

## §2 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│        调用方（Cline / Compiling Agent / Claude / Codex）       │
└───────────────┬──────────────────────────────┬────────────────┘
                │                              │
        ┌───────▼─────────┐            ┌───────▼─────────┐
        │ Skill A          │            │ Skill B          │
        │ hotspot-analyzer │            │ suggestion-patch │
        │ (独立可用)        │            │ (独立可用)        │
        └───────┬─────────┘            └───────▲─────────┘
                │                              │
        performance-findings.json（中立交换格式）
                │              ┌───────────────┤
                └──A→B 路径───►│               │
                外部报告 ──────┘ (B-only 路径)  │ + repo_root
                                              │
        ┌─────────────────────────────────────▼──────────────┐
        │ Workflow: orchestrate.py（编排器，非 triggerable skill）│
        │ full / B-only / A-only + 两道人工闸门，不自动 apply/push │
        └──────────────────────────────────────────────────────┘
```

**独立性约束**：A、B 不互相 import；唯一共享物是 `performance-findings.schema.json`（两 skill 各放一份拷贝）。Workflow 是唯一同时知道 A 和 B 的组件，其"知道"体现在编排代码里，**不写 SKILL.md、不做触发描述**。
**common 边界**：A、B 可以 import `common/*`（tracing、schema_validate、cli_base）；但**不得互相 import 对方 skill 内部模块**（`skills/perf-hotspot-analyzer/` ↔ `skills/perf-suggestion-patch/`）。"互不 import"指 skill 内部，不含共享库。

**三入口**：full（A→Gate→B）、B-only（外部报告直接进 B，需求主路径之一）、A-only（只要分析）。

### 2.1 Skill A 内部数据流

```
Preflight ─► Capture ─► Post-process ─► Diagnose ─► Report(校验)
(权限/符号/   (perf 多次  (perf script   (读源码    (performance-
 callgraph    采集+静态    --symfs 折叠    分类瓶颈+   findings.json
 策略决策)     size 扫描)   /火焰图/排名)   评锚点置信度) +md+flame)
```

### 2.2 Skill B 内部数据流

```
Ingest ─► Anchor ─► Gate ─► Design ─► Patch ─► PatchReport
(格式探测  (锚定+按   (置信度/   (方案    (原子 diff  (.patch +
 →归一化   rubric    类型闸门,   设计)    +分级+     patches.json
 →findings) 评分)     决定能否           副作用)    +md)
                     出 diff)
```

---

## §3 Skill A：perf-hotspot-analyzer

**职责**：对原生 C/C++/Rust 模块用 Linux `perf` 采样定位 CPU 热点，并静态扫描 ELF section/体积，结合源码诊断瓶颈，产出结构化性能证据报告。独立可用。

**SKILL.md frontmatter（description 决定触发）**：

```yaml
name: perf-hotspot-analyzer
description: >-
  Profile a native C/C++/Rust module on Linux/Tizen with perf to locate CPU
  hotspots, and statically scan ELF section/binary size, then diagnose
  bottlenecks against the source and emit a structured performance-findings
  report (JSON + Markdown + flamegraph). Cross-symbolizes Tizen/GBS targets via
  build-id and a debuginfo symfs. Use whenever the user wants to find why
  something is slow, profile a binary/service/app, analyze perf.data, locate hot
  functions, or check binary/section size on an embedded target. The findings
  JSON can be fed directly to perf-suggestion-patch.
```

**流程（SKILL.md 正文，imperative）**：

1. **Preflight**（`scripts/preflight.py`）：检测 `perf` 版本、`perf_event_paranoid`、`CAP_PERFMON`、容器；检测符号/分离 debuginfo/build-id。**决定自适应 callgraph 策略**：frame pointer 可用→`fp`；否则 dwarf/CFI 可用→`dwarf`；否则→`none`（地址/DSO 级降级）。Tizen 走 §7。绝不静默 sudo，缺权限给明确补救步骤。
2. **Capture**（`scripts/capture.py`）：启动型 `perf record -F <freq> -g --call-graph <mode> -- <command>`；附加型 `perf record -p <pid> -g -- sleep <dur>`。可选 `perf stat` 填 `summary_metrics`。**采前填 `run_context`**（CPU governor、affinity、thermal），按 `repeat_count`/`warmup_count` 多次采集（嵌入式波动大，单次不可信）。**静态 binary-size 扫描**（`readelf -S`/`size`/`bloaty`）。
3. **Post-process**（`scripts/postprocess.py`）：`perf script --symfs <sysroot>` → 折叠栈 → 火焰图 SVG + speedscope JSON；`perf report --stdio` 解析 self%/children% 取 Top-N。
4. **Diagnose**（由**宿主 Agent/LLM** 按 `references/bottleneck-taxonomy.md` 执行）：读每个热点源码，结合 `summary_metrics` 分类瓶颈，写 `diagnosis` 与 `candidate_optimizations`，并按 §6.4 rubric 评 `anchor_confidence`。**脚本只负责收集源码上下文、生成待诊断输入、校验输出；任何脚本都不得调用 LLM API（OpenAI/Anthropic/等）。**
5. **Report**（`scripts/build_report.py`）：组装并**条件校验** `performance-findings.json`，渲染 `analysis-report.md`，`report_types` **由脚本据 `findings[].kind` 自动派生**（不信用户输入，见 §6.6）。

**Finding 类型**：v1 实现 `function-hotspot`（perf）+ `binary-size-large`（无基线，必带 `threshold`）+ `binary-size-regression`（两版 ELF 对比，必带 `baseline`+`delta`）。`memory-mapping`（smaps/PSS）留 v1.1。`.rodata`/`.eh_frame`/`.dynsym/.dynstr` 这类需基线才能判异常，衔接既有 LLVM/GCC size 分析。

**binary-size-large 的 v1 默认 threshold 策略**（先能跑，后校准）：对 ELF 的 alloc section，满足任一即生成 finding——① top-n：最大的 Top 5 alloc sections；② section-ratio：单 section ≥ alloc 总大小的 10%；③ absolute：section ≥ 64KB。命中后把触发规则写入 `evidence.threshold`（如 `{"type":"top-n","value":5,"reason":"top 5 largest allocated sections"}`）。

---

## §4 Skill B：perf-suggestion-patch

**职责**：把**任意结合代码的性能/基准报告**归一化、锚定到源码，在锚点可信时生成 review 式建议补丁，否则降级 advisory。独立可用，不依赖 A。

**SKILL.md frontmatter**：

```yaml
name: perf-suggestion-patch
description: >-
  Analyze a code-related performance or benchmark report and, when the source
  anchor is reliable, generate review-style suggestion patches against a
  codebase. Accepts perf-hotspot-analyzer findings JSON, Google Benchmark
  results (single or before/after comparison), folded stacks / flamegraph data,
  and free-form reports. Works standalone; does NOT require the analyzer.
  Low-confidence anchors or semantically risky changes are downgraded to
  advisory recommendations instead of applyable diffs. Use whenever the user has
  a profiling OR benchmark result and wants suggested code changes, optimization
  patches, or a hotspot/regression turned into a diff. Always propose for
  review; never auto-commit.
```

**输入**：`report`（任意格式，必需）+ `repo_root`（必需，外部报告靠它锚定）+ 可选 `baseline_report` / `build_cmd` / `test_cmd` / `symfs` / `perf_budget` / `output_dir`。

**流程**：

1. **Ingest / 归一化**（`scripts/ingest.py` + 必要时 LLM 兜底）：格式探测→选 adapter：`analyzer-json`（直接用）、`google-benchmark`（结构化解析，有基线算 `regression_pct`）、`folded-stacks`（按符号聚合）、`generic-llm`（未知/自由格式，标低置信度）。逐份登记 `source_reports`，统一产出符合 schema 的 findings。
2. **benchmark 对比规则**：给 `baseline_report` → name-match 配对 → `benchmark-regression`；没给 → 只出 `benchmark-latency`（无基线即无"太慢"证据，除非给 `perf_budget`，否则默认 advisory，不出 diff）；重命名用 `comparison.renamed_map` 兜。
3. **Anchor**：findings 自带锚点直接用；仅符号/bench 名则在 `repo_root` 检索（符号→源码、bench 名→被测函数 `bench-name-map`）；按 §6.4 rubric 评 `anchor_confidence`；定位不到标记"不可出 diff"。
4. **Gate**（见 §4.1）。
5. **Design**：参考 `references/optimization-patterns.md`。
6. **Patch**（`scripts/make_patch.py`）：一 finding 一原子补丁，记 `chosen_anchor` + `files_touched_policy` + `patch_category` + `side_effects`，填 status / validation_status。
7. **PatchReport**：`suggestion-patches/*.patch` + `patches.json` + `patch-report.md`。

### 4.1 Gate：拒绝出 patch 硬规则 + 状态语义

```
能否出 diff（行为规则，不进 schema；anchor_confidence 是必要非充分条件）：
  anchor_confidence < 0.7                                  -> advisory-only
  benchmark-latency 且无 perf_budget                        -> advisory-only
  source_format=generic-llm                                -> 永远 advisory-only，
      判定式：source_reports[ finding.source_ref.source_id ].source_format == "generic-llm"
              且 chosen_anchor.resolution_method ∉ {dwarf, addr2line, ctags, compile-db}
      （即自由格式 finding 必须经确定性方法二次锚定到 anchor_confidence≥0.7 才可出 diff；最易误抽）
  patch_category ∈ {algorithm-change, concurrency-change}  -> 默认 advisory-only
  patch_category = api/semantic-change                     -> 不出 diff
  patch_category ∈ {local-micro-optimization, build-flag}  -> 可出 diff

status：
  diff-ready    = 有可应用 diff + chosen_anchor；anchor_confidence≥0.7；
                  verification_plan.required=true 且 build_cmd 与 test_cmd 均非空（供人/CI 验证）。
                  注意：v1 不自动跑，validation_status 仍为 not-run，diff-ready ≠ 已验证收益。
  needs-review  = 有可应用 diff + chosen_anchor；但 verification_plan 缺失或 test_cmd 为空，或中等语义风险。
  advisory-only = 无可应用 diff（禁止出现 diff 字段），只给 recommendation。

validation_status（与 status 正交）：not-run | build-pass | test-pass | benchmark-pass
  v1 恒为 "not-run"；measured_impact 恒为 null（仅当 verification_plan.benchmark_cmd 存在且真跑过才可填）。
```

### 4.2 文件修改策略

```
默认允许修改：src/  include/  CMakeLists.txt  packaging/*.spec
默认禁止修改：.git/  二进制  生成文件  *.lock  凭据/密钥/CI secret
```
build-flag 类常需改 `.spec`/`CMakeLists.txt`，不一刀切禁，但 blast radius 大，须在 patch 标 `files_touched_policy`。

---

## §5 Workflow：perf-optimization-pipeline

**定位**：编排器，**不是 triggerable skill**（无 SKILL.md、无触发描述）。供 headless/CI/无 agent 规划时一条命令可复现地跑整条线，归入 CLI/集成 surface。

**入口模式**：
- **full**：Run A → Gate① 评审热点 → Run B → Gate② 批准 → 交付（不自动 apply/push）。
- **B-only**：外部报告 → Run B → Gate② → 交付。
- **A-only**：只要分析报告。

v2 才做闭环（沙箱/设备应用补丁 → 同负载重测 → 回填统计化 `measured_impact` → 迭代）+ 统计基准配置（warmup/repeat/median/min_speedup/max_noise）。

---

## §6 数据契约

### 6.1 中立交换格式 `performance-findings`（A 产出 / B 归一化目标）

标 `[v1]` 必须支持；其余留槽 v1 可空。

```jsonc
{
  "schema_version": "1.0",
  "report_types": ["hotspot-profile","binary-size"],     // [v1] 脚本据 findings[].kind 自动派生，不信用户输入（见 §6.6）
  "target": { "name":"...", "kind":"binary|process|service|app|benchmark-suite",
              "command":"...", "repo_root":"/abs", "commit":"sha", "build_id":"...",
              "build_config":"release|debug|gbs",
              "platform":{ "os":"linux|tizen","arch":"armv7|aarch64|x86_64","kernel":"..." } },   // [v1]
  "source_reports":[ { "id":"S1","path":"bench-after.json","source_format":"google-benchmark",
                       "parser":"structured","confidence":0.95 } ],                                 // [v1]
  "comparison":{ "current_report":"after.json","baseline_report":"before.json",     // [v1, 仅 benchmark]
                 "compare_method":"name-match|manual-map","renamed_map":{} },        // baseline 缺→只出 latency
  "run_context":{ "device":"emulator|target-board|host","cpu_governor":"performance|ondemand|schedutil|unknown",
                  "core_count":4,"affinity":"0-3","thermal_state":"nominal|throttling|unknown",
                  "repeat_count":5,"warmup_count":1,"stat_method":"median","noise_pct":1.8 },       // [v1]
  "profiling":{ "tool":"perf|external","events":["cycles","cache-misses"],
                "callgraph_mode":"fp|dwarf|none","symfs":"/sysroot",
                "artifacts":{ "raw":"perf.data","folded":"out.folded","flamegraph_svg":"flame.svg" } }, // [v1] 可省
  "tizen":{ "package_name":"...","rpm_name":"...rpm","build_root":"~/GBS-ROOT/...",
            "debuginfo_root":"...","target_rootfs":"...","sdb_serial":"opt","service_name":"opt","pid":1234,
            "path_mapping":[ { "target_path":"/usr/lib/libxxx.so","host_path":"/sysroot/usr/lib/libxxx.so",
              "debug_path":"/usr/lib/debug/.build-id/xx/yyyy.debug","source_path":"src/...","build_id":"xxyyyy" } ] }, // [v1, os=tizen]
  "summary_metrics":{ "ipc":0.81,"cache_miss_rate":0.12 },                                          // [v1] 可选
  "findings":[ {
    "id":"F001",                                                                                    // [v1]
    "kind":"function-hotspot|binary-size-large|binary-size-regression|benchmark-regression|benchmark-latency", // [v1]
    "title":"...",
    "source_ref":{ "source_id":"S1","locator":"$.benchmarks[3]","label":"BM_Decode/1024/real_time" }, // [v1] 对象化
    "evidence":{ "metric":"self_cpu_pct|children_pct|section_bytes|regression_pct|latency_ms",
                 "value":38.2,"unit":"percent|bytes|ms","samples":45000,"rank":1,
                 "callers":["..."],"callees":["..."],
                 "section":".rodata.str1.1","file":"/usr/lib/libxxx.so","symbol_or_object":"opt",
                 "baseline":{ "value":13024,"label":"gcc-build|main@abc123" },
                 "delta":{ "abs":46724,"pct":358.7,"direction":"increase|decrease" },
                 "threshold":{ "type":"absolute-bytes|section-ratio|top-n|user-budget",   // 仅 binary-size-large
                               "value":65536,"unit":"bytes","reason":"section exceeds 64KB / top-3" } },
    "code_anchors":[ { "symbol":"...","dso":"libxxx.so","file":"src/math.c","line_start":120,"line_end":156,
                       "language":"c","anchor_confidence":0.86,
                       "resolution_method":"dwarf|addr2line|ctags|compile-db|grep|bench-name-map|llm","evidence":"..." } ],
    "bottleneck_class":["cpu-bound","cache-unfriendly"],"diagnosis":"...","confidence":0.8,
    "candidate_optimizations":[ { "id":"O1","strategy":"loop-tiling","expected_impact":"high","confidence":0.7,"risk":"medium","rationale":"..." } ]
  } ],
  "notes":"...","provenance":{ "generated_by":"...","version":"1.0.0","timestamp":"..." }
}
```

### 6.2 per-kind 条件校验（JSON Schema `if/then/else`，只约束结构）

| kind | evidence 必填 | 其它必填 |
|------|--------------|---------|
| `function-hotspot` | `metric∈{self_cpu_pct,children_pct}`, `value`, `rank` | 顶层 `profiling`；≥1 `code_anchors` |
| `binary-size-large` | `metric=section_bytes`, `value`, `section`, `file`, **`threshold`** | — |
| `binary-size-regression` | `section`, `file`, **`baseline`**, **`delta`** | — |
| `benchmark-regression` | `metric∈{regression_pct,latency_ms}`, **`baseline`**, **`delta`** | 顶层 `comparison.baseline_report` 非空 |
| `benchmark-latency` | `metric=latency_ms`, `value` | —（diff-ready 限制是 Gate 行为，不在 schema） |

### 6.3 输出契约 `suggestion-patch`

```jsonc
{
  "schema_version":"1.0", "source_reports":[ /* 透传 */ ],
  "patches":[ {
    "id":"P001","finding_id":"F001","source_ref":{ "source_id":"S1","locator":"...","label":"..." },
    "patch_category":"local-micro-optimization|build-flag|allocation-reduction|algorithm-change|concurrency-change|api/semantic-change",
    "strategy":"loop-tiling",
    "chosen_anchor":{ "symbol":"matrix_multiply","file":"src/math.c","line_start":120,"line_end":156,
                      "anchor_confidence":0.86,"resolution_method":"dwarf" },   // diff-ready/needs-review 必填
    "diff":"<unified diff>",                          // advisory-only 时禁止出现（条件校验）
    "recommendation":{ "suggested_locations":["src/math.c:120"],"idea":"...","risk":"..." }, // advisory-only 必填
    "files_touched":["src/math.c"],
    "files_touched_policy":{ "allowed":true,"reason":"...","risk":"..." },
    "expected_impact":{ "level":"high","estimate":"~2x","confidence":0.7 },
    "measured_impact": null,                          // v1 恒 null
    "side_effects":{ "runtime_memory":"unknown","binary_size":"increase","startup_time":"unknown","maintainability":"medium risk" },
    "risk":{ "level":"medium","notes":"..." },"rationale":"...",
    "verify_cmd":"<freeform 人读，可选>",
    "verification_plan":{ "build_cmd":"gbs build -A armv7l ...","test_cmd":"...",
                          "benchmark_cmd":null,"manual_steps":[],"required":true }, // v1 只填 build/test，不跑
    "status":"diff-ready|needs-review|advisory-only","validation_status":"not-run"
  } ],
  "apply_instructions":"...","provenance":{ "generated_by":"perf-suggestion-patch","version":"1.0.0","timestamp":"..." }
}
```

`advisory-only` 项不带 `diff`、必须有 `recommendation`；`diff-ready`/`needs-review` 必须有 `diff` 与 `chosen_anchor`（per-status 条件校验）。

### 6.4 anchor_confidence 评分 rubric（默认值可调，`references/anchor-confidence.md`）

```
0.95  DWARF/build-id 精确到 file:line 且源码存在
0.85  addr2line 精确到函数/行，源码路径可映射
0.75  ctags/compile_commands 唯一函数定义
0.65  grep 多候选，LLM 选一
0.50  benchmark 名启发式匹配
0.30  generic-llm 纯文本猜测
阈值：≥0.7 方可出 diff。
```

### 6.5 confidence 字段术语表

| 字段 | 含义 | 影响 |
|------|------|------|
| `source_reports[].confidence` | 输入报告**解析**可信度 | finding 置信上限 |
| `findings[].confidence` | finding **是否成立** | 不直接决定出 diff |
| `code_anchors[].anchor_confidence` | finding→源码**锚定**可信度 | **决定能否出 diff（0.7）** |
| `candidate_optimizations[].confidence` | 优化方向合理性 | 策略取舍 |
| `expected_impact.confidence` | 预期收益估计可信度 | 仅参考，≠ 实测 |

> 能否出 diff 主要看 `anchor_confidence`，不是 finding confidence。

### 6.6 跨字段语义校验（`common/schema_validate.py`，JSON Schema 之外的硬规则）

JSON Schema 只管单字段结构，下列跨字段规则由 `schema_validate.py` 强制（CLI 输出前必过，不得绕过）：

1. **confidence 上限**：`findings[i].confidence ≤ source_reports[ findings[i].source_ref.source_id ].confidence`。即 finding 置信度不得超过其来源报告的解析置信度。
2. **report_types 一致性**：顶层 `report_types[]` 必须等于 `{ map(kind→report_type) for kind in findings[].kind }` 去重后的集合；由脚本自动派生重算，**用户/外部输入里的 `report_types` 不可信，归一化时丢弃重算**。
3. **per-status 一致性**：`advisory-only` 不得含 `diff`；`diff-ready`/`needs-review` 必须含 `diff` 与 `chosen_anchor`。
4. **v1 不变量**：所有 patch `measured_impact==null`、`validation_status=="not-run"`。
5. **source_ref 有效性**：每个 `findings[].source_ref.source_id` 必须存在于 `source_reports[].id`。
6. **benchmark-regression 一致性**：若存在 `kind=benchmark-regression` 的 finding，则顶层 `comparison.baseline_report` 必须非空（与 §6.2 的 per-kind 校验互为冗余兜底；JSON Schema 跨层 `contains→top-level required` 不好写时以此为准）。

---

## §7 Tizen / GBS 专项（`references/adapters/tizen-gbs.md`）

> 命令为形态示意，**实施时按目标 Tizen 版本确认**；所有 target↔host↔debug↔source 映射写进 `tizen.path_mapping`，作为 B 锚定依据。

1. **设备侧采集**：经 `sdb`（类比 adb）在目标板/模拟器 `perf record`，`sdb pull perf.data` 回 host；app 经 launcher/aul 起后按 pid 附加，daemon/service 经 systemd 附加。
2. **host 侧解析**：目标常 stripped，符号在分离 `-debuginfo`/`-debugsource` RPM，用 **build-id**（`.note.gnu.build-id`）匹配；`perf report --symfs <sysroot> --kallsyms <target>` 符号化。
3. **sysroot 组装**：从 GBS 产物/debuginfo RPM 解出未 strip `.so`/调试文件拼成 symfs，映射 `/usr/lib`、`/usr/lib64`、`/usr/bin`。
4. **GBS 构建**：`gbs build -A <arch>` 产 RPM（通常 `~/GBS-ROOT/.../RPMS/`）；patch 的 `verification_plan.build_cmd` 以 GBS 形式给出，`test_cmd` 为运行时测试（两者不同，v1 只填不跑）。
5. **架构注意**：ARMv7 无 LBR、fp unwinding 需保留 frame pointer、dwarf 更重——由 §3 自适应策略定。
6. **体积/内存联动**：`readelf -S`/`size`/`bloaty`；RELRO 用 `readelf -d`/checksec；(v1.1) `/proc/<pid>/smaps` 的 PSS/Private_Dirty。

---

# 第二部分：工程化

## §8 开发产物管理（dev_memory）

**目的**：milestone 完成即写 dev_memory，使 session 崩溃或换 AI 可无损接续，并支持决策追溯。**写"为什么"，不只写"做了什么"。**

### 8.1 目录结构（适配 A/B 双并行线）

```
.dev_memory/
├── README.md                       # 读取指南
├── current.yaml                    # ★ 接手者第一份读：双线指针
├── m0_schema/ , m0.5_fixtures/
├── a1_x86_perf/ , a2_binary_size/ , a3_tizen_symbolize/      # A 线
├── b1_ingest_anchor/ , b2_benchmark_folded/ , b3_patch_gen/  # B 线
└── mfinal_workflow/ , minteg_integration/
     每个 milestone 目录含：
     ├── memory.md         # 主记忆（已完成/改动详情+为什么/测试状态/下一步入口/接手指引）
     ├── decisions.md      # 设计决策日志（含被否决方案与理由）
     ├── patches.yaml      # patch 记录（见 8.3）
     ├── test_report.md    # UT + 功能测试报告
     └── known_issues.md   # 已知问题 / TODO
```

### 8.2 `current.yaml`（双线指针）

```yaml
shared_last_completed: m0.5_fixtures
lines:
  A: { current: a2_binary_size, last_completed: a1_x86_perf, last_commit: abc123, review_status: pending }
  B: { current: b1_ingest_anchor, last_completed: null, last_commit: def456, review_status: in-progress }
session_count: 4
next_steps:
  - "A 线：实现 binary-size large/regression 解析"
  - "B 线：analyzer-json ingest + 仓库锚定 + rubric 评分"
blocked_on: null
notes: |
  M0/M0.5 已合入 main。A、B 两线并行推进，互不依赖。
```

### 8.3 `patches.yaml`（满足"记 patch 与为什么"）

```yaml
patches:
  - id: p001
    title: "Implement perf record wrapper with run_context capture"
    commit: "abc123de"
    files_changed: ["skills/perf-hotspot-analyzer/scripts/capture.py"]
    lines_added: 180
    lines_removed: 0
    rationale: "DESIGN §3 — 多次采集填 run_context，嵌入式单次不可信"
    test_commit: "def456gh"
```

### 8.4 `memory.md` 模板要点

状态(completed/in-progress/blocked)、起始/最新 commit、已完成清单、**关键改动详情(文件→改了什么→为什么→来源 DESIGN 章节→对应测试)**、测试状态表+覆盖率、下一阶段入口、给下一个开发者(AI/人)的接手步骤。

---

## §9 GitHub 工作流

**仓库**：<https://github.com/lhmax2010/PerfHotSpotAnalyzer>

### 9.1 分支策略

```
main                                  # 稳定分支，只经 PR 合并
└── stage/m0-schema
└── stage/a1-x86-perf , stage/b1-ingest-anchor , ...   # 每 milestone 一分支（A/B 可并行）
```
main 只经 PR 合并；每 milestone 完成开 PR，标题 `[<stage-id>] <name>`；PR 必须含 dev_memory 链接 + 测试报告。

### 9.2 PR 模板 `.github/pull_request_template.md`

含：milestone、dev_memory 链接、关键改动、测试结果(UT __/__、功能 __/__、覆盖率 __%)、Review checklist(`pytest` 全绿 / 端到端验证命令 / dev_memory 已更新 / 真机 guide 已写 / 已知问题已记)、下一阶段入口。

### 9.3 Commit 规范

`<type>(<scope>): <subject>` + body + `Refs: DESIGN §x, dev_memory <stage>`。type：feat/fix/test/docs/refactor/perf/chore；scope：preflight/capture/postprocess/ingest/anchor/patch/tracing/infra。

### 9.4 GitHub Actions CI `.github/workflows/ci.yml`

ubuntu + python 3.11 → 装依赖(含 universal-ctags) → ruff + mypy → `pytest tests/unit --cov` → schema 契约测试(正/负向 fixtures) → 功能/e2e → `coverage --fail-under=80`。

> 注：真机 perf 采集与 Tizen 交叉符号化无法在 CI 自动化；CI 用预采 fixture，真验证靠 §10/§14 的真机 guide。

---

## §10 测试体系

### 10.1 测试金字塔

```
┌──────────────────┐
│   E2E            │  完整报告 → 补丁/分析
├──────────────────┤
│ Integration      │  跨模块（scan+rank、ingest+anchor）
├──────────────────┤
│  Functional      │  golden fixtures 级（语义正确）
├──────────────────┤
│     UT (100+)    │  单模块/单函数
└──────────────────┘
```

### 10.2 单元测试
框架 pytest，`tests/unit/`。覆盖 schema 条件校验(正/负向)、perf 解析、折叠聚合、binary-size 解析、ingest adapter、anchor 评分、Gate 规则、patch 组装、日志格式。核心模块行覆盖 ≥80%(CI gate)。每模块至少含 happy path + 2 edge + 1 degraded + 异常输入。

### 10.3 功能测试（fixture 级）
`tests/functional/` 跑 `tests/fixtures/`，断言**语义正确**而非跑通。每 fixture 含：输入报告/数据、`expected.json` 期望、`README.md` 人工标注、`notes.md` 注意事项。

### 10.4 Golden Fixtures（M0.5，先于业务脚本）
正向：①hotspot+binary-size 混合 ②GB before/after ③GB 单份(latency) ④binary-size-regression ⑤low-confidence generic-llm ⑥advisory-only patch ⑦diff-ready patch。
负向(验证条件校验会拦)：⑧binary-size-regression 缺 baseline ⑨benchmark-regression 缺 comparison.baseline_report ⑩advisory-only 带 diff ⑪diff-ready 缺 chosen_anchor ⑫binary-size-large 缺 threshold。

### 10.5 每 milestone Definition of Done

| Milestone | UT | 功能测试 | 其它 |
|-----------|----|---------|------|
| M0 schema | 条件校验正/负向全覆盖 | 12 fixtures 校验判定正确 | 两 skill 引用同一 schema |
| M0.5 fixtures | — | 正向全过、负向全拦 | 作为后续契约基线 |
| A1 x86 perf | 30+，≥80% | 故意慢 C 样例 Top-1 命中 | callgraph_mode/run_context 如实 |
| A2 binary-size | 15+，≥80% | large+regression 各 1 | delta 正确、与 size 一致 |
| A3 Tizen 符号化 | 10+ | Tizen perf.data 锚到 file:line | anchor_confidence≥0.7 |
| B1 ingest+anchor | 20+，≥80% | analyzer-json 锚定正确 | rubric 评分 |
| B2 bench/folded/generic | 20+ | GB 有/无基线分别 regression/latency；自由格式 generic-llm | — |
| B3 patch 生成 | 20+ | micro-opt 出可 apply diff；风险项 advisory 无 diff | measured_impact=null |
| M-final workflow | 10+ | full + B-only 跑通 | 默认不 apply/push |

### 10.6 测试 guide（真机，每 milestone 一份）

`docs/test-guides/<stage-id>.md`，含：适用范围、**环境前置(OS/arch、perf 版本、paranoid、Tizen sdb/rootfs/debuginfo/GBS 路径，差异点重点标)**、准备步骤、执行步骤(命令+预期输出)、判定通过标准、看日志 debug(trace_id 在哪)、常见问题排查、反馈附件清单。CI 无法自动化的(真机 perf、Tizen 符号化)给可人工执行的等价步骤。

---

## §11 可观测性（Tracing + Run Report）

### 11.1 Tracing 日志
`common/tracing.py` 统一 logger，每次调用生成 `trace_id`，日志带 `trace_id`+`step`+`level`。双输出：控制台(人读) + `<output_dir>/run-<trace_id>.jsonl`(结构化)。级别 DEBUG/INFO/WARN/ERROR，`--verbose` 或 `PERF_SKILL_LOG_LEVEL=DEBUG` 提级。不打印密钥/token/完整源码。

结构化字段示例：
```
{"ts":"...","level":"INFO","step":"preflight","event":"callgraph_chosen","mode":"dwarf","reason":"no frame pointer"}
{"ts":"...","level":"INFO","step":"anchor","event":"resolved","finding":"F001","confidence":0.86,"method":"dwarf"}
{"ts":"...","level":"INFO","step":"gate","event":"downgrade","finding":"F003","decision":"advisory-only","reason":"anchor_confidence=0.62<0.7"}
```
**必记**：A——preflight 结论(含 callgraph 及原因)、capture 实际命令、采样数、Top-N、每 finding 的 kind/evidence/anchor 评分；B——每份输入的 source_format/parser/confidence、每 finding 锚定过程与得分、**每条 Gate 判定及触发规则**、每 patch 的 category/status。

### 11.2 Run Report（每次运行输出 `<output_dir>/run-report.json`）

```jsonc
{
  "schema_version":"run-report/v1","trace_id":"...","skill":"perf-hotspot-analyzer|perf-suggestion-patch",
  "started_at":"...","total_ms":8420,
  "by_step":{ "preflight":120,"capture":6000,"postprocess":1800,"diagnose":400,"report":100 },
  "input":{ "callgraph_mode":"dwarf","source_formats":["analyzer-json"] },
  "findings":{ "total":5,"by_kind":{ "function-hotspot":3,"binary-size-large":2 } },
  "anchors":{ "resolved":4,"confidence_distribution":{ ">=0.9":2,"0.7-0.9":2,"<0.7":1 } },
  "gate_decisions":[ { "finding":"F003","decision":"advisory-only","reason":"anchor_confidence=0.62<0.7" } ],
  "patches":{ "diff-ready":2,"needs-review":1,"advisory-only":2 },
  "degradations":[],"exit_status":"success"
}
```

### 11.3 性能基线（可选目标，随实现校准）
perf.data 解析(典型 size) < 目标秒数；report 组装 < 1s；ingest 单份报告 < 1s。具体阈值在 M1/B1 实测后写入。

---

## §12 Skill 接入方案

三层调用面并存，宿主无关：CLI（主，即契约）、SKILL.md（agent 指令面）、可选 MCP server（包装 CLI）。

### 12.1 统一调用契约（A、B 两个 entrypoint 共享）

```
ENTRYPOINTS:
  python -m perf_hotspot_analyzer <subcmd> [args]
  python -m perf_suggestion_patch <subcmd> [args]
  python -m perf_optimization_pipeline ...        # 编排器

OUTPUT（统一）:
  <output_dir>/performance-findings.json | suggestion-patch 产物
  <output_dir>/run-report.json   (评估)
  <output_dir>/run-<trace_id>.jsonl  (debugging)

EXIT CODES（两 entrypoint 一致）:
  0   成功（含 degraded 但有产物）
  1   致命错误（无产物）
  2   参数错误
  3   输入文件不可读
  124 超时（沿用 GNU timeout 约定）
```

### 12.2 Cline 接入（`integrations/cline/`）

两条路径：(a) 把 SKILL.md 内容作为 Cline 规则（`.clinerules/`）+ 让 Cline 调用 §12.1 的 CLI；(b) 启动 MCP server 挂为 Cline 的 MCP 工具。给最小可跑示例(custom command 配 `python -m perf_hotspot_analyzer ...` + 读产物喂 LLM)。**实施时按当时 Cline 文档核对接入机制，如有出入以 Cline 现状为准并记 ADR。**

### 12.3 Compiling Agent 接入（`integrations/compiling_agent/`）

无人值守，subprocess 调用 + JSON 通信，遵 §12.1 exit code。给集成类骨架(`analyze()` 带 timeout 防 hang，超时/非零退出返回 degraded 结果)。⚠ Compiling Agent 接入 API 尚未提供 → 先出基于 CLI 的通用适配草案 + **一份"需用户补充的接入细节清单"**(如何注册工具、传参、产物回传)，不臆测私有接口。

---

# 第三部分：实施

## §13 文件目录结构

```
PerfHotSpotAnalyzer/                       # GitHub repo root
├── README.md  LICENSE  pyproject.toml  requirements.txt  requirements-dev.txt
├── AGENTS.md                              # = docs/CODEX_PROMPT.md 常驻协议（可选，便于 Codex 自动加载）
├── .github/{workflows/ci.yml, pull_request_template.md}
├── .dev_memory/{README.md, current.yaml, <stage>/...}        # §8
├── docs/
│   ├── DESIGN.md                          # 本文档（唯一基线）
│   ├── CODEX_PROMPT.md                    # 启动 prompt
│   ├── test-guides/<stage-id>.md          # §10.6
│   ├── reviews/<stage-id>.md              # 每阶段 review 包
│   ├── integration_guide.md               # §12 汇总
│   └── archive/                           # v1~v3.1.1 历史
├── common/{tracing.py, schema_validate.py, cli_base.py}      # §11 共享库
├── skills/
│   ├── perf-hotspot-analyzer/{SKILL.md, schemas/, scripts/{preflight,capture,postprocess,build_report,flamegraph}.py,
│   │     references/{bottleneck-taxonomy.md,perf-cheatsheet.md,adapters/tizen-gbs.md}, evals/}
│   └── perf-suggestion-patch/{SKILL.md, schemas/{performance-findings,suggestion-patch}.schema.json,
│         scripts/{ingest,make_patch}.py,
│         references/{optimization-patterns.md,report-format-parsers.md,anchor-confidence.md,file-policy.md,
│           adapters/{google-benchmark.md,folded-stacks.md}}, evals/}
├── workflows/perf-optimization-pipeline/{WORKFLOW.md, orchestrate.py, config.example.yaml}
├── cli/                                   # §12.1 entrypoints（薄封装 common/cli_base）
├── mcp/server.py                          # 可选
├── integrations/{cline/, compiling_agent/}# §12.2 / §12.3
└── tests/{unit/, functional/, integration/, e2e/, fixtures/}
```

### §13.1 Implementation Guardrails（Codex 实施硬规则，防扩范围/防自由发挥）

1. 不实现 v1.1/v2 backlog，除非当前 milestone 明确需要。
2. **任何 Python 代码不得调用 LLM API**（OpenAI/Anthropic/等）；诊断/方案推理由宿主 Agent 提供。
3. **不自动 apply 生成的补丁到用户分支**（只产出 `.patch`/advisory）。
4. v1 不得把 `measured_impact` 写成非 null。
5. `advisory-only` 不得生成 `diff`。
6. CLI 输出前不得绕过 `common/schema_validate.py`（含 §6.6 跨字段校验）。
7. x86 fixture 主链通过前，不得实现 Tizen 真机/设备逻辑（A3 排最后）。
8. 所有外部命令必须支持 dry-run/日志，并带 timeout。
9. DESIGN 有歧义或不可实现时**停下记 ADR 等确认**，不静默重解释。
10. 新增依赖必须记入 `.dev_memory/<stage>/decisions.md`。

## §14 实施计划（按 milestone）

A 线（x86 优先，Tizen 殿后）与 B 线（用 M0.5 fixture/外部样例独立推进）**可并行**，正体现双 skill 独立。

| 里程碑 | 内容 | 线 | DoD |
|--------|------|----|-----|
| **M0** | 仓库骨架 + 两份 schema(含 per-kind/per-status 条件校验) + 校验器 + 共享 tracing + CLI 骨架 | 共享 | 条件校验正/负向正确；两 skill 引用同一 schema、互不 import |
| **M0.5** | Golden fixtures(正①-⑦ + 负⑧-⑫) | 共享 | 正向全过、负向全拦；先于业务脚本 |
| **A1** | x86 perf → findings(preflight/capture/postprocess/flamegraph/diagnose/report) | A | Top-1 命中；callgraph_mode/run_context 如实；报告过校验 |
| **A2** | binary-size finding(large + regression) | A | section_bytes 与 size 一致；regression delta 正确 |
| **A3** | Tizen 交叉符号化(symfs/build-id + tizen.path_mapping)（非阻塞，最后） | A | Tizen perf.data 锚到 file:line，confidence≥0.7 |
| **B1** | ingest(analyzer-json) + anchor + rubric 评分 + 仅 advisory 输出 | B | 锚定正确、按 rubric 评分 |
| **B2** | ingest(google-benchmark 含 comparison / folded / generic-llm) | B | 有/无基线分别 regression/latency；自由格式 generic-llm 低置信度 |
| **B3** | patch 生成(Gate + status/validation_status + chosen_anchor + files_touched_policy) | B | micro-opt 出可 apply diff(diff-ready/needs-review)；风险项 advisory 无 diff；measured_impact=null |
| **M-final** | Workflow(full + B-only + 两闸门) | 共享 | full 端到端通；B-only 用外部报告通；默认不 apply/push |
| **M-integ** | 集成(Cline + Compiling Agent)，CLI/MCP 文档定稿 | 共享 | Cline 示例可跑；Compiling Agent 出草案 + 待补清单 |

依赖：M0 → M0.5 →（A1→A2→A3）∥（B1→B2→B3）→ M-final → M-integ。

### 14.1 扩展路线图

| 版本 | 内容 |
|------|------|
| v1.1 | A 的 Memory Mapping finding(smaps/PSS/Private Dirty)；B 专用 parser(JMH/Criterion/pytest-benchmark) |
| v2 | B 的 go bench/hyperfine parser；Workflow 闭环 + 统计化 measured_impact + 迭代 + validation_status 真正流转；off-CPU 完整分析；Go pprof/py-spy/async-profiler 适配 |

## §15 风险与未决问题

### 15.1 风险表

| 风险 | 影响 | 缓解 |
|------|------|------|
| perf 权限/符号缺失(paranoid、容器、stripped) | A 无法符号化 | Preflight 报错+补救；无符号降 DSO/地址级标低置信度 |
| 外部报告无代码锚点(benchmark 只给名字) | B 无法出 diff | repo 检索 + anchor_confidence；<0.7 advisory |
| generic-llm 误抽 | 错误 finding | 强制标记 + 低置信度 + 默认 advisory |
| 嵌入式性能波动 | measured 不可信 | 多次采集 + run_context 噪声记录；v1 不填实测 |
| 优化改变语义 | 正确性破坏 | 测试是闸门；v1 不自动验证，advisory + 人工 Gate② |
| Tizen 格式/路径版本差异 | 符号化失效 | path_mapping 结构化 + fixture 回归；版本相关项标 TBD |
| Codex 一把梭做全功能 | v1 收敛失败 | dev_memory + 每阶段 PR + 人工 review gate + 每阶段停 |

### 15.2 未决问题

1. 目标 Tizen 版本的精确 `gbs`/`sdb`/`perf`/GBS-ROOT 路径（待用户提供，写入 §7 与 path_mapping）。
2. Compiling Agent 接入 API（待用户提供，定 §12.3 实方案）。
3. anchor_confidence rubric 各档阈值的 fixture 校准。
4. binary-size-large 的 `threshold` 默认策略**已定**为 top-n / section-ratio / absolute 三规则并行（见 §3）；后续仅据 fixtures 校准阈值，非阻塞。
5. run-report 性能基线的具体目标值（M1/B1 实测后定）。

## §16 附录

### 附录 A：术语表
- **perf**：Linux 性能采样工具。
- **hotspot（热点）**：占用 CPU 时间高的函数。
- **finding**：一条性能发现（热点/体积/回归），契约的基本单元。
- **performance-findings**：A 产出、B 归一化目标的中立交换格式。
- **code_anchor**：finding 到源码 file:line 的定位。
- **anchor_confidence**：锚定可信度；出 diff 的**必要闸门之一**（≥0.7 才可能出 diff），但非充分——最终还受 `patch_category`、`perf_budget`、语义风险等 Gate 规则约束。
- **build-id**：ELF `.note.gnu.build-id`，匹配 stripped 二进制与 debuginfo。
- **symfs**：host 侧符号化用的 sysroot 根。
- **GBS**：Git Build System，Tizen 本地构建。
- **sdb**：Tizen 设备桥(类比 adb)。
- **advisory-only**：不出可应用 diff，只给建议的补丁状态。
- **dev_memory**：milestone 开发产物记录，支持接续与追溯。

### 附录 B：契约顶层字段简表

`performance-findings`：`schema_version, report_types[], target, source_reports[], comparison?, run_context, profiling?, tizen?, summary_metrics?, findings[], provenance`。
`suggestion-patch`：`schema_version, source_reports[], patches[]{finding_id, source_ref, patch_category, chosen_anchor?, diff?, recommendation?, files_touched_policy, expected_impact, measured_impact, side_effects, risk, status, validation_status}, apply_instructions, provenance`。

### 附录 C：演进归档
v1~v3.1.1（含多轮 ChatGPT review）归档于 `docs/archive/`，仅供决策追溯。

---

**v1.0.2 文档完结。Codex 实施基线已冻结，进入实施阶段。启动见 `docs/CODEX_PROMPT.md`。**
