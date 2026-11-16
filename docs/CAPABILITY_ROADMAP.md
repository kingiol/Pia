# Capability Roadmap

状态：**Implemented; local verified; external gates pending**。执行日期：2026-11-12；施工起点 `a311380`。九个任务包已接入工作树，交付和验证见 [执行状态](CAPABILITY_IMPLEMENTATION_STATUS.md) 与 [使用说明](CAPABILITY_DELIVERY.md)。下文“当前基线”保留 2026-11-11、`11f64df` 的调查结论，不能作为本次实现后的能力清单；本地通过不代表发布就绪。

## 1. 目标与范围

围绕 Pia 的研究闭环交付九个可独立验收任务包：让研究输入稳定、结果有依据、依赖故障可解释、执行成本可控制，再扩大策略与模型配置能力。

最小路径是继续复用现有 Runtime、ProviderRegistry、Rules、ModelRouter、Trace、SQLite / DuckDB 和标准库 API，在模块化单体内补齐协议与验证。相比先重写 Agent 框架，这条路径迁移范围较小、历史数据可保留，每个任务包都能独立合并。

不在本批次实现：多市场、社交舆情、Bot、GitHub Actions 托管个人研究、Docker 分发、自动下单、新的 Cloud 服务或把移动端变成 Local-first MVP 的发布阻塞项。现有 Cloud / PostgreSQL 行为需要兼容。

本计划跨越超过 8 个实现文件，涉及数据、Runtime、契约、UI 与 CI；必须按下列任务包分批交付，不能一次性重写工作台或 Runtime。

## 2. 当前基线：已有能力与真实缺口

| 模块 | 已有实现 | 本批次要补齐的能力 |
|---|---|---|
| 研究上下文 | 快照、Evidence、创建任务时的 rule snapshot | 统一且不可变的输入包；Profile / Memory 冻结；原始上下文回放 |
| Provider | 能力声明、调用链、重试、Provider 级熔断与质量检查 | capability 级健康、完整尝试链、可解释 last-good 降级 |
| Agent / Decision | 固定顺序图、通用 Pydantic 信封、Rules、人工审批 | 真实图返回值接入；观点与证据校验；确定性合成 |
| 预算 | 任务超时默认 300 秒、重试与 LLM usage | 阶段预算、阻塞调用边界、显式跳过与缺失 |
| 可解释性 | Trace、事件、Audit 与 Agent Timeline | 基于已有事实的执行拓扑、耗时和产物定位 |
| 候选扫描 | Profile 过滤、固定评分公式 | 版本化策略、因素解释、历史复算 |
| LLM | ModelRouter、DeepSeek、能力选择、流式与工具调用 | 运行失败后的安全 fallback、隔离计费、预算预留 |
| CI | 单元 / 契约 / 构建、freshness、平台发布工作流 | 按影响面分流、pnpm 一致性、可靠的聚合门 |
| 降级结果 | TaskStatus、质量字段和事件 | 统一对 API / UI / 导出 / 历史暴露的降级协议 |

需要特别修正的实现假设：

- 当前多数 Agent 节点输出是确定性的模板 / 规则结果；不能把它们宣传成已经完成的独立 LLM 研究。
- `task_context()` 目前会读取当前 Profile / 已确认记忆；`replay_task()` 的新任务会绑定当前规则。历史输入不可变性仍需 P0-01 实现。
- `_decision_for()` 目前可能接受 `target.suggested_action`，并固定输出 `medium` confidence；P0-03 需要消除这种无证据提权。
- Provider fallback 和 ModelRouter 已存在；本计划是在已有模块上增强。
- 某些 Evidence ID 是预先拼接的。证据充分性必须查询真实持久化内容，不能仅计算 ID 数量。

## 3. 不可破坏的约束

1. Rules / Risk 门禁决定可行动边界；LLM、策略评分和个人记忆都无权改写规则。
2. 不新增自动交易。研究的 confidence 表示证据可信程度，不表示盈利概率。
3. Fixture 不得成为 live 数据缺失时的隐式备用源。
4. stale / unavailable 的关键数据不能用于新建可行动候选。last-good 只提供明确标注的背景研究。
5. 历史回放使用原始输入与分析时间；当前时间用于审批有效期。回放结果不是新的可交易建议。
6. 所有读取都保留用户与任务归属检查；全局 health 不返回持仓、记忆、prompt 或凭据。
7. additive schema / migration，保持现有 TaskStatus；`PARTIAL` 不作为新增 TaskStatus。
8. 本批次增强验收 ID 使用 `CAP-P0-*` / `CAP-P1-*`，不替换 [原有 MVP 验收](ACCEPTANCE.md)。

## 4. 任务包与顺序

工期为熟悉代码的单名工程师的净开发日估计，包含对应测试，不是交付日期承诺；外部账号、平台设备和 CI 等待不计入。

| ID | 交付物 | 前置依赖 | 估计 | 状态 |
|---|---|---|---|---|
| P0-01 | DecisionContextPack、冻结与回放 | 无 | 4–6 日 | Implemented |
| P0-02 | capability health、provenance、last-good | P0-01 | 3–5 日 | Implemented; live gate pending |
| P0-03 | DecisionSynthesizer | P0-01；接入 P0-02 来源字段 | 4–6 日 | Implemented |
| P0-04 | 阶段预算与内部降级记录 | P0-01、P0-03 | 4–6 日 | Implemented; Windows gate pending |
| P0-05 | Run Flow API 与工作台视图 | P0-02、P0-04 | 2–4 日 | Implemented |
| P1-01 | 策略注册、解释与复算 | P0-01、P0-02、P0-03 | 3–5 日 | Implemented |
| P1-02 | 多路由 fallback 与成本预算 | P0-04 | 4–6 日 | Implemented; real endpoint gate pending |
| P1-03 | 按影响面分层 CI | 无；可在 P0 期间先实施 | 2–3 日 | Implemented; remote CI gate pending |
| P1-04 | 公共部分结果 / 降级契约 | P0-04、P0-05；接入 P1-02 成本原因 | 3–5 日 | Implemented |

合计约 29–46 净开发日，另预留约 20% 集成缓冲。以验收结果推进，不把九个任务包挤进原始 12 周 MVP 排期。

```text
P0-01 -> P0-02 -> P0-03 -> P0-04 -> P0-05
   |         |       |       |         |
   +---------+-------+-> P1-01|         |
                             +-> P1-02 |
                             +---------+-> P1-04

P1-03: independent CI improvement
```

详细施工步骤、接口、验收与回退分别见 [P0 执行计划](P0_IMPLEMENTATION_PLAN.md) 和 [P1 执行计划](P1_IMPLEMENTATION_PLAN.md)。

## 5. 端到端数据路径

```text
Task + frozen Profile / Rules / Memory
                |
Provider -> Raw / Normalized / Snapshot + Attempt Records
                |
       DecisionContextPack (immutable)
                |
       Stage Policy / Agent Graph
                |
Validated Opinions + Rules -> DecisionSynthesizer
                |
       Decision + Result Metadata
                |
      API -> Workspace / Export
                |
     Approval (current-time checks)

Trace / Events / Audit -> Run Flow projection
Frozen Pack + versioned outputs -> Offline Replay
```

这是单向研究链；Run Flow 只读投影，不触发 Agent 或 Provider。策略只生成候选 / 研究输入，不回写 Rules。

## 6. 统一施工与完成门槛

每个任务包按以下顺序执行：

1. 核对当前分支与工作树，保留并行修改；对照实际函数名、Schema 和迁移序号调整定位。
2. 增加契约与高价值 fixture / 边界测试；新增测试文件在各计划中列明。
3. 实现最小垂直切片，SQLite 与 PostgreSQL 的事务行为保持一致。
4. API 改动时同步 OpenAPI、JSON Schema、TypeScript 生成器及 Desktop API wrapper。
5. 运行任务包验证与统一离线回归，记录命令、commit、环境、退出码和脱敏产物。
6. 更新本表状态、[实现说明](IMPLEMENTATION.md)、[需求矩阵](REQUIREMENT_MATRIX.md) 和相应操作文档；评审后再进入下一包。

当前可用的统一验证命令：

```bash
./scripts/test.sh
./scripts/replay.sh
./scripts/e2e.sh
./scripts/python.sh scripts/generate_ts_client.py --check
git diff --check
```

`test.sh` 使用 unittest，不使用 pytest。计划中标为“新增”的测试文件必须先创建，再运行指定命令；当前执行该模式若匹配到 0 个测试不能算通过。

涉及持久化时增加备份 / 恢复验证；涉及多用户或共享表时运行 `./scripts/cloud-e2e.sh`。PostgreSQL 环境准备妥当后运行 `./scripts/postgres-cloud-e2e.sh`，缺少环境必须记录未验证，不得以 SQLite 结果代替；该脚本缺少 PostgreSQL 工具时会以 0 退出并打印 SKIP，因此还须检查实际执行产物，不能只看退出码。

涉及 UI 时同时验证 Desktop / Web，因为 Web 当前复用 Desktop 的 App 与样式；准备现有 smoke 所需的 Playwright CLI 后运行 `./scripts/trust-ui-smoke.sh`（脚本自行启动临时服务），补充移动视口与键盘检查。

## 7. 发布、迁移与回退

- 每个任务包一个可独立评审的改动集。已有数据库先备份；迁移分别位于 `migrations/` 与 `migrations/postgres/`，使用实现时下一个空闲序号，SQLite / PostgreSQL 成对维护。禁止在本计划中固定可能被并行工作占用的迁移编号。
- 新记录保留 `schema_version` / 算法版本。历史数据不做伪造回填，无法恢复的信息显式记为 `legacy_incomplete`。
- 新能力不可用时可退回旧 UI 或只读展示。不得退回“直接信任 suggested_action”的决策路径；缺少有效上下文或合成器时只允许保守研究或阻断。
- 历史上下文与审计不随功能回退删除。已含新记录的数据库不直接交给不兼容旧二进制；恢复旧备份时须先归档新增记录并说明数据时间边界。
- P0 / P1 通过不自动关闭 Windows、Tushare、外部通知或真实服务 SLA 发布缺口。发布前另跑 `./scripts/release-preflight.sh` 并对照原有验收标准。

## 8. 配置、账号与主要风险

默认离线验收不需要新账号、新服务或新框架。真实 AKShare 需要网络；Tushare live 需要用户自己的 Token 与对应权限；真实 DeepSeek 需要 API Key 与可用余额；P1 第二模型仅在用户显式配置端点并同意数据去向后启用。任何密钥均通过现有 CredentialStore / 环境注入，不写进上下文、策略、导出或日志。

最脆弱的前提是：现有 Agent 输出能否提供足够真实、可绑定的证据。如果不能，P0 合成器仍交付可验证的 `WATCH / NO_ACTION / BLOCKED`，不通过放宽门禁制造买卖候选；方向性投资策略需另行校准和产品决策。

| 风险 | 处理与验证 |
|---|---|
| 上游断网、限流、部分能力故障 | capability 级 fallback；必需数据阻断；可选缺失显式降级 |
| 任务量或数据量扩大 10 倍 | pack 只包含任务相关字段与引用；分块存储，列表接口不返回完整包；flow 按事件序号增量读取 |
| 并行任务费用串账 | P1 使用 request / attempt 级不可变 usage 与事务预算预留，不依赖全局 active route |
| 外部 SDK 不响应取消 | P0 阻塞调用隔离与晚到结果拒收；不把线程 timeout 宣称为可杀死网络请求 |
| 历史数据被覆盖 | pack 保存规范化内容和摘要；快照 ID 不作为不可变性的唯一证明 |
| 文档与实现再次漂移 | 每包交付更新状态与证据；新增公共字段同步契约和导航 |
