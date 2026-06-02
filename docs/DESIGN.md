# 性能优化 Skill 套件设计文档 v1.0.6

**版本**：v1.0.6（实施冻结版，整合 v1~v3.1.1 全部 review 意见 + 工程化要求）
**v1.0.6 修订**：纯文案/一致性扫尾——§7 与 §14 残留"folded 作主源"全部改成 `perf-script.txt` 主源、folded 仅供火焰图/聚合;`out.folded` 默认改由 **host** 基于 perf-script.txt 生成(不强依赖 target 上的 stackcollapse/Perl);修正 §13.1 中 §4.3 误引用;扩大 CI LLM SDK 扫描范围(覆盖 common/skills/workflows/cli/mcp/integrations,豁免 tests/)并同时拦 `import`/`from import`;§6.4 rubric 补 `caller-attribution` 评分档;§2 "M0 已实现"改"M0 必须实现";附录术语表补 `perf-script.txt`。无架构变更。
**v1.0.5 修订**：实现可判定性收口——Bundle 改 10 件并新增 `perf-script.txt`(host 符号化主源);明确 `out.folded` 由 `stackcollapse-perf` 生成且仅作火焰图/聚合;§6.2 `function-hotspot` 条件按 ownership/actionability 分支;新增 **`effective_anchor` 规则**(B 一律用它,不看 `code_anchors[0]`);消除 `generic-llm` 的两段冲突措辞;明确 ingest 的 generic-llm 兜底由**宿主 Agent 写回磁盘**,脚本不调 LLM SDK(进 §13.1);schema 共享改为 canonical(`common/schemas/`)+ 两 skill 拷贝 + CI 字节一致;`allocation-reduction` 补 Gate 归类;binary-size-large 的 top-n 默认 informational;CI live perf 默认 skip;buildid 采集首选 `perf buildid-list`;ownership 模板补 `/usr/lib64`/`/lib`/`/lib64`。架构不动。
**v1.0.4 修订**：§3A 从抽象 Device Transport 落到 **ssh+scp 主路径**（Tizen 场景；sdb 作退路）；新增 `DeviceRunner` 抽象与两份用户面 yaml（**device profile** + **capture-job**）；新增 **ownership profile yaml**（`/usr/lib` 量级前缀清单，作为 §3B 的输入而非未决项）；Capture Bundle 内容扩成 8 件套并补 `perf-report.txt` 作退路、`exec.log`；A1 显式跑 DeviceRunner local backend 把"远程执行链"在 x86 上先打通；§14/§15 同步。架构不动，§3A/§3B 从规格变成可执行方案。
**v1.0.3 修订**：新增 §3A「设备执行与数据搬运」（Device Transport 两模式 + Capture Bundle；Skill A 拆 Capture/Analyze 两阶段）、新增 §3B「热点归属与归因」（ownership 分层 + caller-attribution + actionability 闸门）；§6 增 capture-bundle manifest 与 finding 的 `ownership`/`attribution_anchor`/`actionability` 字段；B 的 Gate 增「非 actionable 不出 diff」；§7 细化 transport。补规格缺口，无架构变更。
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
- §3A 设备执行与数据搬运（perf 在开发板上跑）
- §3B 热点归属与归因（决定哪段代码才是可优化点）
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

**独立性约束**：A、B 不互相 import；schema 采用 **canonical 单源 + 字节一致拷贝**——`common/schemas/performance-findings.schema.json` 为唯一权威源，两 skill 的 `schemas/` 下持有发布拷贝（便于独立发布/部署）；**CI 强制校验两份拷贝与 canonical 的 SHA-256 一致**（**M0 必须实现**），不一致即 fail，避免 schema 漂移。运行时统一通过 `common/schema_validate.py` 加载 canonical schema。Workflow 是唯一同时知道 A 和 B 的组件，其"知道"体现在编排代码里，**不写 SKILL.md、不做触发描述**。
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

**两阶段（关键，见 §3A 设备模型）**：Skill A 显式分 **Capture（需设备）** 与 **Analyze（纯 host、离线）** 两段，中间隔一个自包含的 **Capture Bundle**。x86 本地分析是「设备=host」的退化情形。

**流程（SKILL.md 正文，imperative）**：

1. **Preflight**（`scripts/preflight.py`）：检测 `perf` 版本、`perf_event_paranoid`、`CAP_PERFMON`、容器；检测符号/分离 debuginfo/build-id；探测设备可达性以决定采集模式（§3A）。**决定自适应 callgraph 策略**：frame pointer 可用→`fp`；否则 dwarf/CFI 可用→`dwarf`；否则→`none`（地址/DSO 级降级）。Tizen 走 §7。绝不静默 sudo，缺权限给明确补救步骤。
2. **Capture**（`scripts/capture.py`，**需设备**）：经 Device Transport 在板上 `perf record -F <freq> -g --call-graph <mode> -- <command>`（或 `-p <pid>`）；可选 `perf stat` 填 `summary_metrics`；**采前填 `run_context`**，按 `repeat_count`/`warmup_count` 多次采集。产出 **Capture Bundle**（§3A.2）。**静态 binary-size 扫描**（`readelf -S`/`size`/`bloaty`，在 host 对构建产物做，不需设备）。
3. **Symbolize + Attribute**（`scripts/postprocess.py`，**纯 host**）：用 bundle 的 build-id 匹配 debuginfo/`--symfs` 完成符号化；折叠栈 → 火焰图 + speedscope；`perf report` 取 Top-N；对每个热点做 **ownership 判定 + caller-attribution**（§3B），确定 `code_anchors`/`attribution_anchor`/`ownership`/`actionability`。
4. **Diagnose**（由**宿主 Agent/LLM** 按 `references/bottleneck-taxonomy.md` 执行）：只对 `actionable` 的热点，读其**归属到你 repo 的真实源码**，结合 `summary_metrics` 分类瓶颈，写 `diagnosis` 与 `candidate_optimizations`，并按 §6.4 rubric 评 `anchor_confidence`。**脚本只负责收集源码上下文、生成待诊断输入、校验输出；任何脚本都不得调用 LLM API。**
5. **Report**（`scripts/build_report.py`）：组装并**条件校验** `performance-findings.json`，渲染 `analysis-report.md`，`report_types` **由脚本据 `findings[].kind` 自动派生**（见 §6.6）。

**Finding 类型**：v1 实现 `function-hotspot`（perf）+ `binary-size-large`（无基线，必带 `threshold`）+ `binary-size-regression`（两版 ELF 对比，必带 `baseline`+`delta`）。`memory-mapping`（smaps/PSS）留 v1.1。`.rodata`/`.eh_frame`/`.dynsym/.dynstr` 这类需基线才能判异常，衔接既有 LLVM/GCC size 分析。

**binary-size-large 的 v1 默认 threshold 策略**（先能跑，后校准）：对 ELF 的 alloc section，满足任一即生成 finding——① top-n：最大的 Top 5 alloc sections；② section-ratio：单 section ≥ alloc 总大小的 10%；③ absolute：section ≥ 64KB。命中后把触发规则写入 `evidence.threshold`（如 `{"type":"top-n","value":5,"reason":"top 5 largest allocated sections"}`）。

> **降噪默认**：`type=top-n` 触发的 finding 默认 `actionability=informational`（top-N 一定会命中,正常构建也会触发,做 patch 价值低）；`type=section-ratio` 与 `type=absolute` 默认 `actionability=actionable`。用户给了 `user_budget` 时 top-n 才升级 `actionable`。这条进 §3 与 §6.2 的语义说明。

---

## §3A 设备执行与数据搬运（perf 在开发板上跑）

`perf` 在**开发板（Tizen 目标机）**上执行；代码、debuginfo、AI 都在 **host（开发服务器）**。本节钉清楚整条 host↔target 链。

**认知前提**：AI 不直接碰硬件。"让 AI 控制开发板"= AI 产出一份 `capture-job.yaml`（采什么），`capture` 脚本经 **DeviceRunner** 在 target 上跑 perf 并 `scp` 拉回 **Capture Bundle**；AI 只负责编排（采什么、怎么分析），ssh/scp 由脚本做。

```
   HOST(开发服务器)                                 TARGET(Tizen 开发板)
   ┌────────────────────────────┐                  ┌─────────────────────┐
   │ AI 产 capture-job.yaml      │  ssh(指令)        │ runner.sh:          │
   │ ↓                           │ ───────────────►  │   perf record/stat  │
   │ DeviceRunner.shell          │                  │   perf script→folded │
   │   .push(scp host→target)    │ ◄─────────────── │   收 kallsyms/maps/  │
   │   .pull(scp target→host)    │  scp(回拷)         │   dso build-id     │
   │ ↓                           │                  │   打 tar 成 Bundle  │
   │ Capture Bundle(本节核心)     │                  │                     │
   │ ↓ (以下全在 host 离线)       │                  └─────────────────────┘
   │ 符号化 → 归属/归因(§3B) → AI 诊断 → findings 报告
   └────────────────────────────┘
```

**整链 8 个 Stage（捋一遍，后面字段都指它们）**：

```
1 Plan        host  AI 产 capture-job.yaml(采什么、目标谁)
2 Provision   host→target(ssh)  推 runner.sh + capture-job，探 perf 可用性/权限
3 Execute     target(ssh)       perf record/stat；板上导 perf-script.txt(主源)
4 Collect     target→host(scp)  拉回 Capture Bundle(自包含 tar)
5 Symbolize   host              build-id→debuginfo→--symfs→file:line
6 Attribute   host              ownership 判定 + caller-attribution(§3B)
7 Diagnose    host              AI 读 repo 真实源码片段 + 指标 → 诊断
8 Report      host              findings.json + analysis-report.md + 火焰图
```

**核心边界**：Stage 2–4 在 target；Stage 5–8 在 host。**target 不参与符号化和诊断**——它既没 debuginfo、也没源码、也没 AI。

### §3A.1 DeviceRunner（远程执行器）

`common/device_runner.py` 提供三个操作，仅此而已：

```python
class DeviceRunner:
    def shell(cmd: str, timeout_s: int) -> CompletedRun   # ssh <profile> "cmd"
    def push(local_path, remote_path) -> None              # scp host→target
    def pull(remote_path, local_path) -> None              # scp target→host
```

**配置只来自 device profile yaml**，不接受散参数。每条 ssh/scp 必须进 tracing 日志（命令、返回码、耗时）。

```yaml
# .perf-skill/devices/board-a.yaml  —— 用户配一次
name: board-a
backend: ssh                          # ssh | sdb | local
host: 192.168.1.42
user: root                            # Tizen 镜像多为 root
ssh_opts: "-i ~/.ssh/board_a -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5"
scp_opts: "-q"
remote_workdir: /tmp/perf-skill
perf_path: /usr/bin/perf              # 按目标 Tizen 版本确认
needs_sudo: false
arch: aarch64                         # Stage 5 选 sysroot 用
sysroot: ~/sysroots/board-a           # host 侧 sysroot
debuginfo_roots:                      # host 上的 debuginfo 搜索路径
  - ~/GBS-ROOT/local/repos/<profile>/<arch>/RPMS/debug
  - /usr/lib/debug
target_has_stackcollapse: false       # 板上是否装了 stackcollapse-perf.pl(默认 false,folded 由 host 生成)
```

> **Tizen 现实**：标准镜像未必预装 sshd——需要选 root 镜像或自己装 openssh。该写进 §7 的"先决条件"，不在文档假定。

**Backends**：

- `ssh`（主路径，本节默认）：用 OpenSSH `ssh`/`scp`，受益于 key 认证、ProxyJump、密钥透传等成熟特性；适合"host 与 target 在同一局域网"的开发场景。
- `sdb`（退路）：Tizen 自带设备桥。`needs sshd in image` 不成立或要快速接入时用。`DeviceRunner` 内部用 `sdb shell/push/pull` 实现同样三个操作。
- `local`（退化）：device=host，用于 x86 本地分析与 A1 把整条链先打通；ssh/scp 替换成本地 shell/cp。

### §3A.2 capture-job.yaml（AI 产、脚本消费、随 Bundle 回带的复现凭证）

AI 不直接拼 ssh 命令，而是产这份 yaml；脚本读它去构造执行：

```yaml
# .perf-skill/jobs/2026xxxx-bootup.yaml  —— AI 产出
device: board-a
target:
  kind: pid | command | service            # 三选一
  pid: 1234                                # 或
  command: "/usr/bin/my-daemon --foo"      # 或
  service: my-daemon.service               # systemd
perf:
  events: [cycles]
  freq_hz: 999
  callgraph: auto                          # auto: preflight 决定 fp/dwarf/none
  duration_s: 30
  repeat: 3
  warmup: 1
output:
  bundle_name: bundle-2026xxxx.tar.gz
```

这份 yaml 落盘进 Bundle（见下）——**等于本次采集的复现凭证**，任何 review/换人接手都能在你板子上重放。

### §3A.3 Capture Bundle（跨 target→host 的唯一自包含 artifact，10 件套）

target 上 Stage 3 末尾打成 tar，Stage 4 经 `scp` 一次拉回；host 侧后续 Stage 不再回连板子。

```
bundle-<ts>.tar.gz
├── manifest.json             # 自描述（schema 见 §6.7）
├── capture-job.yaml          # 复现凭证（从 host 推下来再回带）
├── perf.data                 # 原始
├── perf-script.txt           # ★ host 符号化主源：perf script -F comm,pid,tid,time,ip,sym,dso（保留 IP/DSO/offset）
├── out.folded                # 火焰图 / 粗粒度聚合用：perf script | stackcollapse-perf.pl
├── perf-report.txt           # 板上 perf report --stdio（host 跨架构 perf 不可用时的退路）
├── kallsyms                  # /proc/kallsyms 快照
├── proc-<pid>-maps           # /proc/<pid>/maps（DSO 加载地址）
├── dso-list.txt              # 进程加载 .so 列表 + 各自 build-id
├── run-context.json          # CPU governor / affinity / thermal / repeat / warmup
└── exec.log                  # 板上每条命令 + stdout/stderr + 退出码
```

**Symbolize 输入优先级（§3A 与 §6 都依这条）**：
1. `perf-script.txt`（含 IP/DSO/offset，host 可独立做 build-id → debuginfo → file:line）→ **主源**
2. `perf.data` + host perf + `--symfs`（host 装了能解 target 架构的 perf 才可用）→ 次源
3. `out.folded` 仅用于火焰图与粗粒度聚合，**不作为 file:line 锚定的唯一依据**（折叠后 IP/DSO 多半丢失）
4. `perf-report.txt` 退路（板上已符号化的文本，作 sanity check）

> 设计原因：`perf script` 直接输出的并不是 folded 栈；folded 由 `stackcollapse-perf.pl`（FlameGraph 工具集）从 perf-script 转换。folded 把多条栈合并、丢掉 IP/DSO/offset，只剩符号名，**host 拿到 folded 后再做 file:line 符号化会缺信息**。所以 Bundle 保留 perf-script 原文作为主源，folded 单独存以便快速出火焰图。

### §3A.4 执行流程（伪代码，看清楚就行）

```
host: capture.py 读 devices/board-a.yaml + jobs/<job>.yaml
  ssh_target = DeviceRunner(profile=board-a)
  ssh_target.shell("mkdir -p /tmp/perf-skill/<ts>")
  ssh_target.push(capture-job.yaml, runner.sh, → /tmp/perf-skill/<ts>/)
  ssh_target.shell("bash /tmp/perf-skill/<ts>/runner.sh")   # Stage 3 全在板上
        ├─ perf record -F<freq> -g --call-graph <auto> [-p <pid>|-- <cmd>] -- sleep <dur>
        ├─ perf script -i perf.data -F comm,pid,tid,time,ip,sym,dso > perf-script.txt  # ★ 符号化主源
        # out.folded 默认由 host 在 Stage 5 基于 perf-script.txt 生成(不依赖 target 有 perl/FlameGraph)；
        # 仅当 device profile 设 target_has_stackcollapse: true 时，target 端额外生成 out.folded:
        #   ├─ perf script -i perf.data | stackcollapse-perf.pl > out.folded
        ├─ perf report --stdio -i perf.data > perf-report.txt   # 退路
        ├─ cp /proc/kallsyms ./kallsyms
        ├─ cp /proc/<pid>/maps ./proc-<pid>-maps
        ├─ perf buildid-list -i perf.data > dso-list.txt        # 首选,无需 binutils
        │     # fallback: readelf -n / eu-readelf 取每个 DSO 的 build-id（嵌入式可能裁剪了 binutils）
        ├─ 收 run-context（governor/affinity/thermal）→ run-context.json
        └─ tar 打包成 bundle-<ts>.tar.gz
  ssh_target.pull(/tmp/perf-skill/<ts>/bundle-<ts>.tar.gz, ./captures/)
  ssh_target.shell("rm -rf /tmp/perf-skill/<ts>")   # 清场（默认开，可关）
```

**没有 ssh 时的退路**（诚实保留，不假装是一等公民）：
- `backend: sdb`：DeviceRunner 内部把 ssh/scp 换成 `sdb shell/push/pull`，其它不变。
- 手动模式：`capture.py --dry-run` 输出"该在板上跑的命令 + 回拷路径约定"，你拿过去手跑。Bundle 回到 host 后 Stage 5–8 不变。

---

## §3B 热点归属与归因（决定哪段代码才是"可优化点"）

`perf` 的热点大量落在**你不拥有、不该改、可能没源码的代码**里（gobject/glib、libc、内核）。直接拿它们出 patch 会让 skill 失效。核心不是"找到热点对应代码"，而是**先判定每个热点属于谁、该不该由你改**。

### §3B.1 按 ownership 分层（确定性，脚本做，不靠 AI 猜）

复用 §3A Bundle 里的 `dso-list.txt`(DSO 路径 + build-id) 与 `proc-<pid>-maps`，对每个热点帧判定：

```
ownership 决策（优先级从上到下）：
  build-id 在 host 的 owned_build_id_sources 里               → owned         (你的 GBS 构建)
  DSO 路径匹配 owned_paths 通配                                → owned         (e.g. /usr/lib/myplugin/*)
  DSO 路径匹配 third_party_paths 通配                          → third-party   (e.g. libgst*, libgobject*)
  DSO 是 libc / ld / [kernel.kallsyms]                       → system
  其它（无 build-id / 无符号）                                  → unknown
```

策略来自一份必备配置 `.perf-skill/ownership.yaml`（**M0 必须落地，不是未决项**）。Tizen + `/usr/lib` 量级模板，按你环境替换:

```yaml
# .perf-skill/ownership.yaml  —— 用户配一次,Codex 不要自己改
owned_build_id_sources:
  - ~/GBS-ROOT/local/repos/*/*/RPMS/                 # 你构出来的就是你的
owned_paths:
  - /usr/lib/myplugin/*.so*                          # 你的插件
  - /usr/lib/<your-pkg>/*                            # 你的包
  - /usr/bin/<your-binary>
third_party_paths:                                   # Tizen 上典型框架库（按需增减）
  - /usr/lib/libgst*.so*
  - /usr/lib/libgstreamer-*.so*
  - /usr/lib/libglib-2.0.so*
  - /usr/lib/libgobject-2.0.so*
  - /usr/lib/libgio-2.0.so*
  - /usr/lib/libgthread-2.0.so*
  - /usr/lib/libdbus-*.so*
  - /usr/lib/libecore*.so*                           # EFL（若你的栈用得到）
  - /usr/lib/libelementary*.so*
  - /usr/lib64/libgst*.so*                           # aarch64 / 多 ABI 镜像走 lib64
  - /usr/lib64/libg*.so*
  - /lib/lib*.so*                                    # 部分系统库可能在 /lib
  - /lib64/lib*.so*
system_paths:
  - /usr/lib/libc-*.so*
  - /usr/lib/libpthread-*.so*
  - /usr/lib/ld-*.so*
  - /usr/lib64/libc-*.so*
  - /usr/lib64/libpthread-*.so*
  - /usr/lib64/ld-*.so*
  - /lib*/libc-*.so*
  - /lib*/ld-*.so*
  - "[kernel.kallsyms]"
```

**规则**：通配用 glob；同一路径同时匹配 owned 与 third-party → owned 胜出（你能改的总优先）。任何决策必须在 Run Report（§11.2）里写出"为什么这么判"（命中哪条规则、build-id 是什么），不许 AI 私改。

### §3B.2 caller-attribution（归因帧）

**洞察：gobject 自己慢不可优化，但"你的代码高频调用 gobject"通常可优化。** 对 `third-party`/`system` 热点，脚本沿 callgraph **上溯**，标出栈里**第一个 `owned` 帧**作为 `attribution_anchor`（你能改的最近一帧）。例：`g_signal_emit` 很热 → 上溯发现是你的某 element 每帧发数千 signal → 真正能改的是你的代码，finding 锚到那里，`bottleneck_class` 标 `external-call-overhead`/`call-frequency`，优化方向是"减少调用/批量化/换 API"，而非"改 gobject"。

**两种归因策略**（ownership.yaml 里 `attribution_strategy`，默认 `nearest-to-hotspot`）：
- `nearest-to-hotspot`（默认）：自底向上找**最贴近热点**的 owned 帧。适合微观优化。
- `nearest-to-entry`：自顶向下找**最贴近用户入口**的 owned 帧。适合架构级问题（"我们最外层入口就高频调用 framework"）。

栈里穿插 owned/third-party/owned 的边界情况按所选策略走；Run Report 里要记录"选了哪个、为什么"。

### §3B.3 AI 在确定性结果之上决定 finding 形态 + actionability 闸门

脚本把"热点 + ownership + 归因帧源码 + 调用路径"打包给 AI，AI 决定：

| 情形 | finding 锚点 | actionability |
|------|-------------|---------------|
| 热点 owned | 锚到热点本身 | `actionable` |
| 热点 third-party，有 owned 归因帧 | 锚到 `attribution_anchor` | `actionable` |
| 热点 third-party/system，整栈无 owned 帧 | 仅记录 | `not-actionable` |
| 内核/unknown | 仅记录 | `informational` |

**B 据此再加一道闸门（接 advisory-first 哲学）：`actionability != actionable` 的 finding 永远不出 diff。**

> 诚实前提：这套强依赖**带符号的 callgraph**。若框架库无 debuginfo 或 `callgraph_mode=none`，归因帧找不到 → 脚本如实降级（`ownership=unknown`、`actionability=informational`），不硬编锚点。这也是为何 §3A 的"采 build-id + 尽量带 debuginfo + 选对 callgraph"是这一切的基础。

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

1. **Ingest / 归一化**（`scripts/ingest.py`，**不调 LLM API**）：格式探测→选 adapter：`analyzer-json`（直接用）、`google-benchmark`（结构化解析，有基线算 `regression_pct`）、`folded-stacks`（按符号聚合）、`generic-llm`（未知/自由格式）。逐份登记 `source_reports`，统一产出符合 schema 的 findings。
   **`generic-llm` 兜底协议（必须，否则违反 §13.1 第 2 条）**：脚本只做三件事——① 把原始文本写成 `prompts/<id>-normalize.prompt.md`（含 schema 片段 + 抽取指令）；② 等待宿主 Agent 把结果写回 `outputs/<id>-normalized.json`；③ 读回后过 `schema_validate`、标记 `source_format=generic-llm` 与低 confidence、进入 Anchor 与 Gate。**`ingest.py` 内部禁止 import 任何 LLM SDK**（openai/anthropic/...），违反则 CI 失败（§13.1）。
2. **benchmark 对比规则**：给 `baseline_report` → name-match 配对 → `benchmark-regression`；没给 → 只出 `benchmark-latency`（无基线即无"太慢"证据，除非给 `perf_budget`，否则默认 advisory，不出 diff）；重命名用 `comparison.renamed_map` 兜。
3. **Anchor**：findings 自带锚点直接用；仅符号/bench 名则在 `repo_root` 检索（符号→源码、bench 名→被测函数 `bench-name-map`）；按 §6.4 rubric 评 `anchor_confidence`；定位不到标记"不可出 diff"。
4. **Gate**（见 §4.1）。
5. **Design**：参考 `references/optimization-patterns.md`。
6. **Patch**（`scripts/make_patch.py`）：一 finding 一原子补丁，记 `chosen_anchor` + `files_touched_policy` + `patch_category` + `side_effects`，填 status / validation_status。
7. **PatchReport**：`suggestion-patches/*.patch` + `patches.json` + `patch-report.md`。

### 4.1 Gate：拒绝出 patch 硬规则 + 状态语义

```
能否出 diff（行为规则，不进 schema；以 `effective_anchor`(§6.6 第 10 条) 为唯一锚点判断对象，不看 code_anchors[0]）：
  finding.actionability != "actionable"                    -> 永远 advisory-only（§3B 归属/归因）
  effective_anchor 为 null 或其 anchor_confidence < 0.7    -> advisory-only
  benchmark-latency 且无 perf_budget                        -> advisory-only
  source_format=generic-llm                                -> 默认 advisory-only；
      仅当 effective_anchor.resolution_method ∈ {dwarf, addr2line, ctags, compile-db}
            且 effective_anchor.anchor_confidence ≥ 0.7
      时，才允许继续走后续 Gate（即自由格式经确定性方法二次锚定后可不再是终态降级）
  patch_category = api/semantic-change                     -> 不出 diff
  patch_category ∈ {algorithm-change, concurrency-change}  -> 默认 advisory-only
  patch_category = allocation-reduction                    -> 分两档：
      纯局部（reserve / 预分配 / 避免重复 malloc-free / 不改对象生命周期与所有权）
                                                              -> 可出 diff（needs-review 或 diff-ready）
      涉及缓存 / 对象池 / 共享所有权 / 生命周期延长 / 线程可见性  -> advisory-only
  patch_category ∈ {local-micro-optimization, build-flag}  -> 可出 diff

status：
  diff-ready    = 有可应用 diff + chosen_anchor（= 该 finding 的 effective_anchor，schema_validate 强制写入）；
                  effective_anchor.anchor_confidence≥0.7；
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
    "ownership":"owned|third-party|system|unknown",                                                  // [v1] §3B 归属
    "actionability":"actionable|informational|not-actionable",                                       // [v1] §3B 闸门
    "evidence":{ "metric":"self_cpu_pct|children_pct|section_bytes|regression_pct|latency_ms",
                 "value":38.2,"unit":"percent|bytes|ms","samples":45000,"rank":1,
                 "callers":["..."],"callees":["..."],
                 "hot_symbol":{ "symbol":"g_signal_emit","dso":"libgobject-2.0.so","ownership":"third-party" }, // [v1] 实际最热帧（可能非 owned）
                 "section":".rodata.str1.1","file":"/usr/lib/libxxx.so","symbol_or_object":"opt",
                 "baseline":{ "value":13024,"label":"gcc-build|main@abc123" },
                 "delta":{ "abs":46724,"pct":358.7,"direction":"increase|decrease" },
                 "threshold":{ "type":"absolute-bytes|section-ratio|top-n|user-budget",   // 仅 binary-size-large
                               "value":65536,"unit":"bytes","reason":"section exceeds 64KB / top-3" } },
    "code_anchors":[ { "symbol":"...","dso":"libxxx.so","file":"src/math.c","line_start":120,"line_end":156,
                       "language":"c","anchor_confidence":0.86,
                       "resolution_method":"dwarf|addr2line|ctags|compile-db|grep|bench-name-map|caller-attribution|llm","evidence":"..." } ],
    // 当 hot_symbol 非 owned 时，沿 callgraph 上溯到第一个 owned 帧；finding 的可改锚点指向它（§3B.2）：
    "attribution_anchor":{ "symbol":"my_element_chain","dso":"libmyplugin.so","file":"src/element.c",
                           "line_start":88,"line_end":120,"language":"c","anchor_confidence":0.82,
                           "resolution_method":"caller-attribution","evidence":"hot g_signal_emit called from element.c:101" }, // [v1] 仅非 owned 热点
    "bottleneck_class":["cpu-bound","cache-unfriendly","external-call-overhead","call-frequency"],"diagnosis":"...","confidence":0.8,
    "candidate_optimizations":[ { "id":"O1","strategy":"loop-tiling","expected_impact":"high","confidence":0.7,"risk":"medium","rationale":"..." } ]
  } ],
  "notes":"...","provenance":{ "generated_by":"...","version":"1.0.0","timestamp":"..." }
}
```

### 6.2 per-kind 条件校验（JSON Schema `if/then/else`，只约束结构）

| kind | evidence 必填 | 其它必填 |
|------|--------------|---------|
| `function-hotspot` | `metric∈{self_cpu_pct,children_pct}`, `value`, `rank`；`evidence.hot_symbol` 必填 | 按 actionability/ownership 分三档（见下）；顶层 `profiling` 必填 |
| `binary-size-large` | `metric=section_bytes`, `value`, `section`, `file`, **`threshold`** | — |
| `binary-size-regression` | `section`, `file`, **`baseline`**, **`delta`** | — |
| `benchmark-regression` | `metric∈{regression_pct,latency_ms}`, **`baseline`**, **`delta`** | 顶层 `comparison.baseline_report` 非空 |
| `benchmark-latency` | `metric=latency_ms`, `value` | —（diff-ready 限制是 Gate 行为，不在 schema） |

**`function-hotspot` 锚点要求按 ownership/actionability 分三档（消除与 §3B 降级策略的冲突）**：

```
actionability=actionable, ownership=owned         -> code_anchors[] 长度 ≥ 1
actionability=actionable, ownership!=owned        -> attribution_anchor 必填且 anchor_confidence ≥ 0.7
actionability ∈ {not-actionable, informational}   -> code_anchors[] 可空；evidence.hot_symbol 必填
```

这条由 `schema_validate.py` 第 9 条校验（§6.6）。`evidence.hot_symbol` 在所有档位都必填（即使 anchor 缺失，也至少知道是哪个符号热）。

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
0.80  caller-attribution：callgraph 中存在唯一 owned 帧，DSO/build-id/path_mapping 可确认，file:line 可映射
0.75  ctags/compile_commands 唯一函数定义
0.65  caller-attribution：只有符号名/DSO,owned 帧可疑或多候选,需 LLM/人工选择
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
7. **actionability 一致性（§3B）**：`ownership != "owned"` 的 finding，若无 `attribution_anchor`，则 `actionability` 必须为 `informational|not-actionable`（不得标 actionable）。
8. **attribution 完整性**：`actionability=="actionable"` 且 `ownership != "owned"` 时，必须有 `attribution_anchor`（且其 `anchor_confidence≥0.7`），否则降级。
9. **function-hotspot 锚点分档**（实现 §6.2 表后的三档规则）：`actionable+owned`→`code_anchors[].length≥1`；`actionable+!owned`→`attribution_anchor` 必填且 `anchor_confidence≥0.7`；`!actionable`→可无锚点但 `evidence.hot_symbol` 必填。
10. **`effective_anchor` 派生规则**（B 的 Gate / `chosen_anchor` / patch 生成一律基于它，不准看 `code_anchors[0]`）：
    ```
    若 finding.attribution_anchor 存在               -> effective_anchor = attribution_anchor
    否则若 code_anchors[] 非空                       -> effective_anchor = code_anchors 中
                                                       (anchor_confidence 最高 → resolution_method 最可靠) 的那一项
    否则                                            -> effective_anchor = null（finding 强制 advisory-only / 不出 diff）
    resolution_method 可靠性序：dwarf > addr2line > ctags > compile-db > grep > bench-name-map > caller-attribution > llm
    ```
    `schema_validate.py` 在序列化产物时把 `effective_anchor` **显式写入 patch.chosen_anchor**（便于审计），不能让 Codex 在 B3 里临时挑。

### 6.7 Capture Bundle manifest（§3A.2，Capture→Analyze 的内部交接格式）

`capture` 阶段产出、`analyze` 阶段消费；自描述，使 host 侧分析不回连板子。

```jsonc
{
  "schema_version":"capture-bundle/v1",
  "backend":"ssh|sdb|local",                                         // §3A.1
  "device":{ "name":"board-a","host":"192.168.1.42","arch":"aarch64","tizen_version":"..." },
  "capture_job":"capture-job.yaml",                                  // §3A.2 复现凭证（同包带回）
  "target":{ "kind":"pid|command|service","pid":1234,"cmdline":"...","service":null,"commit":"sha" },
  "perf":{ "events":["cycles"],"freq_hz":999,"callgraph_mode":"fp|dwarf|none",
           "duration_s":30,"repeat":3,"warmup":1 },
  "run_context":{ "cpu_governor":"...","affinity":"...","thermal_state":"..." },   // 同 §6.1
  "artifacts":{ "perf_data":"perf.data",
                "perf_script":"perf-script.txt",                  // ★ host 符号化主源
                "folded":"out.folded",                            // 火焰图/粗聚合用,非锚定主源
                "perf_report":"perf-report.txt",                  // 退路
                "kallsyms":"kallsyms","proc_maps":"proc-<pid>-maps","dso_list":"dso-list.txt",
                "exec_log":"exec.log" },                          // 板上每条命令+返回码
  "dsos":[ { "path":"/usr/lib/libgobject-2.0.so","build_id":"ab12…","load_addr":"0x7f01…",
             "has_debuginfo_on_device":false } ],
  "provenance":{ "captured_by":"perf-hotspot-analyzer/capture","timestamp":"..." }
}
```

`dsos[].build_id` 是 host 侧符号化与 §3B 归属判定的依据；`backend` 记录用了哪种连入；`capture_job` 让 bundle 自带复现凭证（任何 review/换 AI 接手都能在你板子上重放）。

---

## §7 Tizen / GBS 专项（`references/adapters/tizen-gbs.md`）

> 命令为形态示意，**实施时按目标 Tizen 版本确认**；所有 target↔host↔debug↔source 映射写进 `tizen.path_mapping`，作为 B 锚定依据。

**镜像先决条件（不绕过）**：本套件**默认走 ssh+scp**（§3A.1 `backend: ssh`）。Tizen 标准镜像通常**不预装 sshd**，需要：① root 镜像；② 镜像里启用或自己装 `openssh-server`；③ 在板上 `systemctl enable sshd && systemctl start sshd`；④ host 把公钥写到板上 `~/.ssh/authorized_keys`。完成这些前 ssh backend 不可用。**退路是 `backend: sdb`**（Tizen 自带，装了 tizen-studio 即有），DeviceRunner 把 ssh/scp 内部换成 `sdb shell/push/pull`，其它逻辑不变。

1. **设备侧采集（§3A 执行）**：经 `DeviceRunner` 用 ssh/scp(或 sdb)在板上 `perf record / perf stat`；app 经 launcher/aul 起后按 pid 附加，daemon/service 经 systemd 附加。**板上必出 `perf-script.txt`(host 符号化主源)**放进 Capture Bundle（§6.7）;`out.folded` 默认由 host 在 Stage 5 基于 perf-script.txt 生成(target 不强依赖 Perl/FlameGraph),仅当 device profile 设 `target_has_stackcollapse: true` 时才在板上生成。
2. **host 侧解析**：目标常 stripped，符号在分离 `-debuginfo`/`-debugsource` RPM，用 **build-id**（`.note.gnu.build-id`）匹配；**优先消费 `perf-script.txt` + `--symfs <sysroot>` 完成 file:line 符号化**;fallback 用 host perf 加 `--symfs` 解 `perf.data`(host 需有匹配 target 架构的 perf);`out.folded` 仅作火焰图与粗聚合,不作 file:line 锚定唯一依据。按 §3B 用 DSO 路径/build-id 做 ownership 判定与 caller-attribution。
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

ubuntu + python 3.11 → 装依赖(含 universal-ctags) → ruff + mypy → **LLM SDK 静态扫**(以下命令命中即 fail，§13.1 第 2 条;扫主代码目录,**显式豁免 `tests/`**)：
```bash
grep -rnE '^\s*(from|import)\s+(openai|anthropic|google\.generativeai|cohere)\b' \
  common/ skills/ workflows/ cli/ mcp/ integrations/ --include='*.py'
# 任何命中即 CI fail；测试目录可独立写桩,不受此扫描约束
```
→ `pytest tests/unit --cov` → schema 契约测试(正/负向 fixtures + canonical/拷贝 SHA-256 一致) → 功能/e2e → `coverage --fail-under=80`。

> 注：真机 perf 采集与 Tizen 交叉符号化无法在 CI 自动化；CI 用预采 fixture，真验证靠 §10/§14 的真机 guide。
> **live perf 测试默认 skip**：x86 live `perf record` 在 GitHub Actions 容器内 `perf_event_paranoid` / 权限可能受限。默认 skip，本地或真机 guide 才跑；要在 CI 启用须设 `PERF_SKILL_ENABLE_LIVE_PERF=1` 环境变量。CI 必跑的是**预采 perf fixture** + 全部确定性逻辑。

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
| M0 schema | 条件校验正/负向全覆盖 | 12 fixtures 校验判定正确 | canonical 在 `common/schemas/`；两 skill 拷贝 CI 字节一致 |
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
├── common/{tracing.py, schema_validate.py, cli_base.py, device_runner.py,
│           schemas/performance-findings.schema.json,            # canonical 单源(§2)
│           schemas/suggestion-patch.schema.json,                # canonical 单源
│           schemas/capture-bundle.schema.json}                  # §6.7
│           # §11 共享库 + canonical schemas；device_runner=§3A.1
├── .perf-skill/                          # 用户配置（每环境/每板一份，进 .gitignore 看需要）
│   ├── devices/<name>.yaml               # §3A.1 device profile（ssh/sdb/local）
│   ├── jobs/<ts>-<tag>.yaml              # §3A.2 capture-job（AI 产，落盘留存）
│   └── ownership.yaml                    # §3B.1 owned/third-party/system 路径清单
├── skills/
│   ├── perf-hotspot-analyzer/{SKILL.md, schemas/, scripts/{preflight,capture,postprocess,build_report,flamegraph}.py,
│   │     target-side/runner.sh,          # §3A.4 板上执行脚本，push 到 target/tmp 跑
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
2. **任何 Python 代码不得调用 LLM API**（OpenAI/Anthropic/等）；诊断/方案推理由宿主 Agent 提供。具体禁条：主代码目录(`common/`、`skills/`、`workflows/`、`cli/`、`mcp/`、`integrations/`)任何文件**不得 `import` 或 `from … import` LLM SDK**（openai/anthropic/google.generativeai/cohere/…），`tests/` 豁免。CI 静态扫(具体命令见 §9.4)，命中即 fail。`generic-llm` 兜底走"脚本写 prompt → 宿主 Agent 写回 json → 脚本读回校验"三步（见 §4 流程第 1 点与 §4.1）。
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
| **M0** | 仓库骨架 + 两份 schema(含 per-kind/per-status 条件校验) + 校验器 + 共享 tracing + CLI 骨架 | 共享 | 条件校验正/负向正确；canonical 在 `common/schemas/`，两 skill 拷贝经 CI 字节一致校验、互不 import |
| **M0.5** | Golden fixtures(正①-⑦ + 负⑧-⑫) + capture-bundle manifest 样例 + ownership/attribution/actionability 各形态样例 | 共享 | 正向全过、负向全拦（含 §6.6 第 7/8 条）；先于业务脚本 |
| **A1** | x86 perf → findings；Capture/Analyze 两阶段(§3A，x86 用 `backend: local` 跑 DeviceRunner，把"远程执行链"先打通) + ownership.yaml 配齐 + caller-attribution(§3B) | A | Top-1 命中；产出 capture-bundle(local backend)；第三方热点正确归因或标 not-actionable；报告过校验 |
| **A2** | binary-size finding(large + regression) | A | section_bytes 与 size 一致；regression delta 正确 |
| **A3** | Tizen 设备采集：**ssh+scp 主路径**（device profile + capture-job 落地，DeviceRunner ssh backend）+ 交叉符号化（symfs/build-id + tizen.path_mapping）；`sdb` backend 作退路 | A | ssh backend 端到端：host→target 推 runner.sh→target 跑 perf+导 perf-script.txt→scp 拉回 bundle→host 基于 perf-script.txt + symfs 锚到 file:line，confidence≥0.7；sdb backend smoke 通 |
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

1. 目标 Tizen 版本的精确 `gbs`/`perf` 路径与 GBS-ROOT 布局（待用户提供，写入 §7 与 path_mapping）。
2. Compiling Agent 接入 API（待用户提供，定 §12.3 实方案）。
3. anchor_confidence rubric 各档阈值的 fixture 校准。
4. binary-size-large 的 `threshold` 默认策略**已定**为 top-n / section-ratio / absolute 三规则并行（见 §3）；后续仅据 fixtures 校准阈值，非阻塞。
5. run-report 性能基线的具体目标值（M1/B1 实测后定）。
6. **Tizen 镜像 sshd 部署要求**（§7 先决条件）：选用 root 镜像 + 装 openssh-server + 起 sshd + 公钥分发。无法满足时切 `backend: sdb` 退路。
7. 框架库无 debuginfo / `callgraph_mode=none` 时的降级行为细则（默认 ownership=unknown、actionability=informational，不硬编锚点；阈值随实测调整）。
8. `ownership.yaml` 的真实工程值校准（§3B.1 模板已给 `/usr/lib/*` 量级；具体 owned_paths 按你的 vendor 路径替换）。

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
- **Capture Bundle**：板上采集产出的自包含 artifact（10 件套：manifest + capture-job + perf.data + **perf-script.txt(host 符号化主源)** + out.folded + perf-report + kallsyms + proc-maps + dso-list + run-context + exec.log），跨 device→host 的唯一交接物（§3A.3/§6.7）。
- **ownership**：热点帧的归属（owned / third-party / system / unknown），决定该不该由你改（§3B）。
- **caller-attribution / attribution_anchor**：非 owned 热点沿调用栈上溯到的第一个 owned 帧，即"你能改的最近一帧"（§3B.2）。
- **actionability**：finding 是否可作代码级优化（actionable / informational / not-actionable）；非 actionable 永不出 diff。
- **advisory-only**：不出可应用 diff，只给建议的补丁状态。
- **dev_memory**：milestone 开发产物记录，支持接续与追溯。

### 附录 B：契约顶层字段简表

`performance-findings`：`schema_version, report_types[], target, source_reports[], comparison?, run_context, profiling?, tizen?, summary_metrics?, findings[], provenance`。
`suggestion-patch`：`schema_version, source_reports[], patches[]{finding_id, source_ref, patch_category, chosen_anchor?, diff?, recommendation?, files_touched_policy, expected_impact, measured_impact, side_effects, risk, status, validation_status}, apply_instructions, provenance`。

### 附录 C：演进归档
v1~v3.1.1（含多轮 ChatGPT review）归档于 `docs/archive/`，仅供决策追溯。

---

**v1.0.6 文档完结。Codex 实施基线已冻结，进入实施阶段。启动见 `docs/CODEX_PROMPT.md`。**
