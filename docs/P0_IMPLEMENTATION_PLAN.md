# P0 Implementation Plan

状态：**Implemented; local verified; external gates pending**；执行日期：2026-11-12；源码调查基线：2026-11-11、`11f64df`，施工起点 `a311380`。本文件保留施工规格，实际交付与验证见 [执行状态](CAPABILITY_IMPLEMENTATION_STATUS.md) 和 [使用说明](CAPABILITY_DELIVERY.md)。真实服务和 Windows 验收仍需独立证据。

## 1. 执行约定

- 顺序：P0-01 → P0-02 → P0-03 → P0-04 → P0-05；每包单独评审、验证和交付。
- 下文路径相对于仓库根目录；`runtime/` 简写为 `packages-py/pia_runtime/pia_runtime/`。
- “新增”路径、接口、表和事件均是施工目标，目前不可假定存在。现有契约变更同步 `contracts/openapi.yaml`、对应 JSON Schema、`scripts/generate_ts_client.py`、生成 TypeScript 和 `apps/desktop/src/api.ts`。
- 所有预算常量均为建议的工程初始值，不是投资风险阈值。投资阈值继续来自用户确认的 Rules。
- 不引入新服务、Agent 框架或数据库；不重构无关工作台页面。UI 接入前重新读取并行修改。

## 2. P0-01：冻结研究上下文

### 目标与改动位置

使研究、展示、导出和回放使用同一份可验证输入，解决当前 Context API 读到最新 Profile / Memory、回放可能采用当前规则的问题。

| 文件 | 工作 |
|---|---|
| `runtime/decision_context.py`（新增） | Pydantic pack / block 模型、纯 builder、规范化与 hash 校验 |
| `runtime/runtime.py` | 创建任务冻结个人输入；`_run_task()`、`task_context()`、`replay_task()` 接入 |
| `runtime/db.py`、`runtime/postgres.py`、迁移目录 | 不可变输入与 pack 存取；用户隔离与一致事务 |
| `runtime/analytics.py`、`runtime/backup.py` | 冻结后的数据引用完整性与备份恢复覆盖 |
| `runtime/api.py`、契约及客户端 | Context overview / full 视图 |
| `contracts/schemas/decision-context-pack.json`（新增） | 公共 pack 结构 |
| `tests/test_decision_context.py`（新增）、现有 Runtime / 契约测试 | 冻结、篡改、隔离与回放验证 |

### 合同与持久化

`DecisionContextPack` v1 必须包含：

| 字段 | 约定 |
|---|---|
| `schema_version` | 固定 `"1"`；未知主版本拒绝参与合成 |
| `pack_id / task_id / input_binding_id / source_pack_id` | pack、任务、创建时个人输入与原始 pack 的关系；非回放 source_pack_id 为空 |
| `analysis_as_of / created_at` | 分析业务时间与生成时间分离；时间含时区 |
| `subject / trigger_type / data_mode` | 标的、触发原因、原始数据模式 `fixture|live`；回放保持原始模式 |
| `execution_mode` | `run|replay`，属于执行元数据，不改变输入内容 |
| `profile_snapshot / rule_snapshot / confirmed_memories` | 内容、原始 ID / 版本、内容 hash；只冻结已确认记忆 |
| `blocks` | `market / portfolio / instrument / fundamentals / sources / events`；缺失块仍保留状态 |
| `evidence` | 真实持久化 Evidence 的任务相关副本，包含内容与时间元数据 |
| `versions` | builder、graph、rules evaluator、synthesizer 与代码版本 |
| `content_hash` | 内容规范化后的 SHA-256；排除自身、pack/task/input_binding/source_pack ID、execution_mode 与生成时间，覆盖完整冻结输入与算法版本 |

每个 block 包含 `status=verified|partial|stale|unavailable`、`required`、`as_of`、`observed_at`、`expires_at`、`snapshot_ids`、`content_hash`、`data`、`missing_fields`、`warnings`、`provenance`。非适用块用 `required=false` 与原因表达，不伪造空数据为 verified。

SQLite / PostgreSQL 新增：

- `task_input_bindings`：`id, user_id, task_id, schema_version, payload_json, content_hash, created_at`，任务唯一，只允许插入。
- `decision_context_packs`：`id, user_id, task_id, schema_version, payload_json, content_hash, created_at`，任务唯一，只允许插入。

表内保存规范化的任务相关内容，而不仅是可被 `INSERT OR REPLACE` 覆盖的快照 ID。大体量日线保留该任务实际使用的窗口，不复制全市场原始响应；原始响应继续在既有 Raw 层。hash 使用排序键、固定数值表达、拒绝 NaN / Infinity 的 JSON 编码；读取时重新验证。

### 实施步骤

1. `create_task()` 在同一事务中冻结 Profile、Rules 内容 / ID、已确认 Memory 内容 / 版本；从未创建的显式空仓与读取失败必须区分。
2. 取数、归一化与 Evidence 持久化完成后，纯 builder 只接受已加载数据，不调用 Provider、网络或当前 Profile / Memory 查询。缺失 sector 时不生成不存在的 sector Evidence ID。
3. 保存一次 pack；重试重用冻结输入与已经完成的 pack，需刷新数据时创建新任务并保留父子关系。崩溃后依据输入绑定与数据 checkpoint 恢复，不能改用当前个人设置。
4. Agent 输入、Rules 与合成器消费该 pack；LLM 的只读工具也从冻结块读取，不能在研究中另取最新快照污染同一次输入。需要新数据时创建新任务。`task_context()` 返回历史绑定数据，并用 `context_source=frozen|legacy_incomplete` 表示来源。现有字段保持兼容，另需当前资料时使用独立 `current_*` 字段，不覆盖历史值。
5. 保留 `GET /api/tasks/{id}/context`，新增 `view=overview|full`，默认 overview。overview 只返回块状态、时间、来源、hash 与缺失原因；完整视图需同一任务归属校验，并按现有审计通道记录读取。日志只记 pack ID / hash / 字节数。
6. full 视图和本地导出均移除凭据、HTTP headers、URI 中的敏感查询参数；允许所属用户读取冻结持仓 / 记忆内容。不要将 full pack 附到全局 health、SSE 或默认 LLM prompt。
7. `replay_task()` 为子任务创建新 pack 身份，复制原始冻结内容与内容 hash，记录 `source_pack_id`；Evidence 使用原始只读引用与内容副本，不复用全局主键写回覆盖父任务。Opinion 的执行身份重新绑定子任务，保留 `source_opinion_id`；比较 Decision 时只比较语义内容。离线执行可确定性部分，不重新取数、不重新调用 LLM；LLM 观点重用已持久化输出并附 `replay_source=recorded`，原始 origin 不变。另一次真实模型调用应创建新的 live 研究任务。
8. 老任务缺 pack 时仍可查看既有 Trace / Decision；回放返回明确 `REPLAY_CONTEXT_INCOMPLETE`，不从当前状态“补齐”。当前算法版本与历史不符时返回 `REPLAY_VERSION_MISMATCH`，历史展示仍可用，禁止伪称一致回放。

### 验收

| ID | 必须通过的场景 |
|---|---|
| CAP-P0-01-A | 建立任务后修改 Profile / Rules / Memory，原任务、Context API 与回放仍使用原始内容和相同内容 hash |
| CAP-P0-01-B | Provider spy、网络 spy 证明 builder 与 replay 不发起取数；实际传给 Agent 的输入可追溯到 pack |
| CAP-P0-01-C | 快照被替换后冻结内容不变；篡改 pack、跨用户请求、未知版本被拒绝 |
| CAP-P0-01-D | missing、显式空仓、未来数据、过期证据和 legacy task 各有独立 fixture，不制造 verified |
| CAP-P0-01-E | 备份恢复后输入 hash、用户归属和回放一致；日志、overview 与 SSE 无敏感内容 |

新增测试文件创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_decision_context.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_runtime.py' -v
./scripts/cloud-e2e.sh
```

交付时补充 SQLite / PostgreSQL 迁移与恢复证据。回退可关闭 full 视图和新入口，但保留冻结记录；缺有效 pack 的新候选不得退回不受验证的建议生成路径。

## 3. P0-02：按能力展示 Provider 健康与来源

### 目标与改动位置

已有 ProviderRegistry、重试、熔断和 fallback 不重写；将它们细化为 capability 状态，并让结果明确记录实际使用来源与失败链。

修改 `runtime/adapters.py`、`data_worker.py`、`data_quality.py`、`analytics.py`、`runtime.py`、`api.py` 与 Evidence / Context 契约；扩展 `tests/test_adapters.py`、`test_data_worker.py`、`test_provider_freshness.py`，新增 `tests/test_provider_provenance.py`。

### 合同与默认值

- health 内部键：`provider_id + capability + credential_scope`。scope 使用内部不透明标识；单能力失败不熔断其他能力，多账号凭据不得互相污染。
- 状态包含 `closed|open|half_open`、最后成功 / 失败时间、连续失败、剩余冷却时间、latency。原 Provider 汇总字段保留，新增 capability 明细。
- 初期沿用实际配置：重试 `2`、退避 `0.25s`、退避上限 `2s`、失败阈值 `3`、冷却 `30s`；测试明确“重试次数”与“总尝试次数”，避免加倍重试。
- 每次 capability 调用生成 `call_id`，每次尝试记录 `attempt_id, ordinal, provider_id, capability, started_at, duration_ms, outcome, quality, reason_code, fallback_from`。
- provenance 增加 `selected_provider_id, source_type, snapshot_ids, fallback_used, stale_age_seconds, coverage, attempts`；保留现有 source 时间语义。错误文本脱敏，使用稳定 reason code。
- 追加 `provider_attempts` 持久化表，关联用户 / 任务；非任务预取用空 task ID 和明确 scope。既有 DuckDB 快照保留来源元数据，pack 冻结被选中的来源和尝试链。

### 实施步骤

1. 在 Registry 的能力调用入口统一记账，去掉 Runtime 与 DataWorker 对同一调用重复循环重试的路径；一个 `call_id` 只有一条有序尝试链。
2. 复用已声明 capability 与现有优先级，不虚构 Provider 支持。例如只有声明 `fundamentals` 的 Provider 才进入该能力链。
3. 同一 Provider 能力返回异常、结构不完整或不符合 quality gate 时才转下一个合格源；已成功的其他能力不必因一次 supplemental 失败整体重抓。
4. 所有 live Provider 失败后，查询“同能力、标的、用户权限、业务时间”的 last-good。只选 `as_of <= analysis_as_of`、在原时间点通过质量检查的已有快照，绝不选未来数据。
5. last-good 必须保留原始 provider / as_of / expiry，并标明 `source_type=last_good_snapshot`；到期按现有 Data Gate 标 stale。`stale_age_seconds=max(0, evaluation_time-expires_at)`，历史分析使用 pack 的 evaluation time。
6. 已过期 last-good 只供背景展示并阻断新可行动候选；未过期但备用的结果仍显示 fallback。不存在快照时输出 unavailable，不退到 Fixture。
7. `/api/providers` 增加 capability 级摘要，Context / Evidence / flow 展示尝试链。全局 health 不返回用户快照、原始响应、source URI 或凭据错误全文。

### 验收

| ID | 必须通过的场景 |
|---|---|
| CAP-P0-02-A | 一个 capability 断开，其他能力仍正常；主源失败、备源成功，记录两段正确来源 |
| CAP-P0-02-B | 主源返回 partial 也能切换；尝试次数有上限，无 Registry / Runtime 重试相乘 |
| CAP-P0-02-C | 无备源时 last-good 的过期年龄、来源、覆盖率正确；无缓存明确 unavailable |
| CAP-P0-02-D | stale、未来快照、不同标的 / 用户缓存不能产生新行动候选；live 故障不读取 Fixture |
| CAP-P0-02-E | 熔断开闭与 half-open 并发探测受控；错误脱敏；回放保留原尝试链 |

新增测试创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_provider_provenance.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_adapters.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_data_worker.py' -v
```

离线 fake Provider 必须覆盖全部切换场景。真实验证另行执行 `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_LOOKBACK_DAYS=5 ./scripts/provider-freshness-e2e.sh`；需要网络，Tushare 另需 Token，未跑不得声称 live fallback 已验收。回退时可隐藏 health 明细，保留 provenance 和 stale 门禁。

## 4. P0-03：确定性 DecisionSynthesizer

### 目标与改动位置

让 Agent 只提交观点；程序验证证据、识别冲突并合成最终研究结论。消除任意 `target.suggested_action` 直接影响最终候选状态和固定 confidence 的问题。

新增 `runtime/decision_synthesizer.py`；修改 `agent_contracts.py`、`agent_graph.py`、`runtime.py`、`models.py` 与 Decision 契约。新增 `tests/test_decision_synthesizer.py`，扩展现有 Rules / Runtime / 契约测试。

### 观点与输出合同

新增 `AgentOpinion` v1：

| 字段 | 约定 |
|---|---|
| `opinion_id / agent_name / pack_id / subject` | 所属 Agent、上下文、标的必须一致 |
| `claim_key / dimension` | 同一命题标识；维度限 `market|portfolio|technical|fundamentals|sources|risk` |
| `stance` | `support|oppose|neutral`，仅表示对 claim 的观点 |
| `evidence_ids / rationale` | 必须引用本任务真实存在、标的 / 时间匹配的证据 |
| `origin` | `computed|llm|fixture|stub`；fixture / stub 不参与 live 可信度提升 |
| `limitations` | 缺失与未解决问题；LLM 自报 confidence 不作为系统依据 |

合成结果保留现有 Decision 字段，追加 `synthesizer_version, pack_id, valid_opinion_ids, rejected_opinions, conflicts, confidence_reasons`。拒绝项只保存稳定原因与引用，不把错误原始 prompt 回传给 UI。

### 确定性决策表

按下列优先级从上往下处理：

| 条件 | 行为 |
|---|---|
| 原 Rules 结果为 BLOCKED / NO_ACTION | 原样保留对应状态、原因与 rule_snapshot_id；观点不能覆盖 |
| pack hash / 所有权错误、关键证据不可用 | BLOCKED，并给出可定位的数据原因 |
| 同一 `claim_key` 有有效 support 与 oppose | WATCH，confidence=low，保留双方证据与未解决问题 |
| 观点无效、证据不足、仅 stub / fixture 支撑 live 任务 | WATCH，confidence=low，列明缺口 |
| 有效真实观点、相关必需维度覆盖且无冲突 / warning | WATCH，confidence=medium，提供研究解释 |
| 其他可继续研究的情况 | WATCH，confidence=low |

P0 不新增买卖信号公式，也不自动生成 `BUY_CANDIDATE / SELL_CANDIDATE`。这些枚举为历史兼容保留；原先依赖 `suggested_action` 的测试与 UI 提示要改为明确验证它不具备授权效果。新方向性策略需单独确认投资逻辑、阈值和校准验收后才接入。`high` 枚举保留，本批次不自动授予。

“覆盖”按任务必需维度计算：MarketClose 为 market / portfolio / risk；StockResearch 另需 instrument 对应 technical 与事件所需 sources；同一源转载、同一快照或同一计算派生的重复引用只算同一证据组，不通过增加 Agent 数量提升 confidence。

### 实施步骤

1. 消费 `graph.invoke()` 实际返回的 outputs；保留原有通用信封，新增类型化 opinion 层。现有模板节点标明 stub，不伪装为 computed；由真实行情计算出的观察才能标 computed。
2. 先校验 schema、pack / subject / user，再查询 Evidence 内容、时间、质量与来源组。外部新闻内容作为不可信资料，不执行其中的指令。
3. 无效 opinion 单独隔离；若缺失项属于必需维度，降低结果能力，不把“隔离成功”视为证据充分。
4. 生成冲突清单与稳定排序结果；同 pack、同意见集合、同版本必须生成相同 Decision 内容，排除运行时 ID / wall-clock。
5. Rules 接收真实有效证据统计，保留当前阈值和 Risk Review。新合成器不能改规则；审批入口再次检查当前有效期与规则适用性。
6. Audit 记录合成器版本、输入 pack hash、有效 / 拒绝观点 ID 与最终 gate；新旧结果可在测试中对照，禁止旧路径旁路生效。

### 验收

| ID | 必须通过的场景 |
|---|---|
| CAP-P0-03-A | LLM 强烈看多、用户传 BUY、Rules 阻断时仍 BLOCKED；NO_ACTION 同样不可提升 |
| CAP-P0-03-B | 伪造 Evidence ID、跨任务证据、过期 / 未来证据、错标的观点均被隔离并说明原因 |
| CAP-P0-03-C | 重复来源不提高 confidence；同命题多空冲突稳定降级；Agent 顺序变化不改变结果 |
| CAP-P0-03-D | live 模板输出不能提升 confidence；没有方向性策略时不生成新买卖候选 |
| CAP-P0-03-E | 冻结输入与记录观点回放结果一致；审批仍校验当前时间与门禁 |

新增测试创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_decision_synthesizer.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_rules.py' -v
./scripts/replay.sh
```

回退只能切换到保守 WATCH / 只读研究，不恢复 `suggested_action` 直通。历史 Decision 不改写，版本升级后展示其旧版本标记。

## 5. P0-04：阶段预算与内部降级

### 目标与改动位置

将当前任务级 300 秒超时细分为可执行的阶段边界，使可选取数或 LLM 不拖垮整个研究，并让缺失有明确记录。

新增 `runtime/stage_policy.py` 与 `runtime/isolated_call.py`；修改 `runtime.py`、`agent_graph.py`、`llm.py`、`adapters.py`、`config.py`、`db.py` 与 `postgres.py`。新增 `tests/test_stage_policy.py`、`tests/test_isolated_call.py`。

### 阶段策略 v1

阶段顺序可在不破坏依赖的前提下把 Rules 前置，最终 synthesize 仍必须读取 Rules 结果。

| stage_id | 上限 | 必需性 |
|---|---|---|
| `required_data` | 60s | 必需行情、交易日、标的与持仓；事件依赖的原始公告 / 来源也归入此阶段 |
| `supplemental_data` | 45s | 默认可选基本面 / 新闻；已经属于触发依据的来源不能再标可选 |
| `context` | 5s | 必需，纯本地冻结与验证 |
| `agents` | 50s | market / portfolio / risk 观察必需；补充解释与 debate 可跳过 |
| `llm_research` | 90s | `PIA_REQUIRE_LLM=1` 时必需；当前未开启时不调用模型 |
| `rules` | 10s | 必需 |
| `synthesize` | 10s | 必需 |

合计 270 秒，默认任务预算 300 秒，保留 30 秒用于持久化与清理。有效阶段预算为 `min(stage_cap, remaining_task_budget - required_remaining_reserve)`；剩余不足时先跳过可选工作。自定义任务总超时仍使用现有 `PIA_TASK_TIMEOUT_SECONDS`，不增加七个环境变量；策略版本与实际分配写入任务。

LLM 工程上限：每次请求输入 `32 KiB UTF-8`，每次输出 `1024 tokens`，每阶段最多 `2` 轮工具往返、累计最多 `8` 个只读工具调用。每次 HTTP 尝试超时不超过既有 `45s` 与剩余阶段预算的较小值；重试和工具往返共用阶段预算。输入超限按稳定的块优先级裁剪可选内容，并记录 omission；不得截断 Rules、必需证据或 JSON 结构，无法满足时明确失败。

这是字节 / 输出 token / 时间的可执行上限，不把近似输入 token 估算说成硬 token 上限。累计 token / 费用的事务预算在 P1-02 完成。

### 超时与取消实现

1. Runtime 使用 monotonic clock 计算运行预算，wall-clock 只用于审计与证据时效；暂停恢复后按已消耗运行时间结算。
2. 纯计算 / 图节点在前后检查预算、暂停和取消；已结束任务的晚到结果不能写 Decision 或推进状态。
3. Provider 阻塞 SDK 调用放入按调用创建的 leaf 子进程，使用标准库 `multiprocessing` 的 `spawn`；只传可序列化的 capability 请求和 Adapter 配置引用，不传 DB 连接或 Runtime 实例。子进程只返回取数结果，由父进程校验、持久化。
4. 超时 / 取消时父进程 terminate、限时 join（2 秒）、必要时 kill 后回收；Sidecar 退出也清理所有子进程。入口必须适配 PyInstaller `freeze_support`，macOS / Windows 打包验收列为本包门槛。
5. LLM 使用显式 socket timeout 与每个流式 chunk / tool round 的预算检查；结束后丢弃晚到内容。已发送到服务端的请求不能保证撤销收费，费用状态必须保留。不要用 `Future.result(timeout)` 冒充终止 SDK。
6. 必需阶段 transient 故障进入 RETRYABLE、无剩余预算进入 TIMEOUT、不可满足的关键数据由 Data / Rules gate BLOCKED；保留错误分类，不强行把所有失败转 DONE。
7. 可选阶段失败继续执行，写入内部 `completion=partial`、`missing_capabilities`、`degradation_reasons`、`stage_runs`；最终仍经 synthesize。P0 通过 Context / Trace 展示，公共稳定协议在 P1-04 增补，不增加 TaskStatus。

显式空仓可作为合法输入；live 持仓读取失败不能替换为 fixture 空仓。公告触发但原始公告缺失时不能当作“仅可选新闻缺失”。

新增 `task_stage_runs` 表：`user_id, task_id, stage_id, attempt, policy_version, required, allocated_ms, started_at, finished_at, outcome, reason_code, artifact_ids`，唯一键为任务 / stage / attempt。事件包含 `STAGE_STARTED / STAGE_COMPLETED / STAGE_SKIPPED / STAGE_FAILED`，payload 带 stage ID、预算与稳定原因，不包含全文输入。

### 验收

| ID | 必须通过的场景 |
|---|---|
| CAP-P0-04-A | 可选新闻慢 / 故障时产出带缺口的研究；必需行情 / 公告故障不能包装成完整成功 |
| CAP-P0-04-B | Provider 永久阻塞后按期限回收进程；取消 / 超时后无晚到写入，退出无遗留子进程 |
| CAP-P0-04-C | 重试、LLM tool round 共用预算；超输入 / 输出 / 工具上限有稳定错误与记录 |
| CAP-P0-04-D | 小于默认值的总预算不为负；暂停恢复、重启 checkpoint、时钟跳变不重复消费预算 |
| CAP-P0-04-E | fixture 离线无需 LLM；require_llm 缺凭据 / 超时遵循必需阶段失败语义 |
| CAP-P0-04-F | macOS 与 Windows frozen Sidecar 可启动子进程、取消、退出；未跑平台结果不得记为通过 |

新增测试创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_stage_policy.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_isolated_call.py' -v
./scripts/recovery-e2e.sh
./scripts/chaos-e2e.sh
```

进程测试使用本地可控阻塞 worker，不访问真实行情。平台测试使用现有 Sidecar 构建、health、生命周期与 Windows acceptance 脚本。回退可关闭可选阶段，但不能取消必需阶段预算和晚到写入保护。

## 6. P0-05：Run Flow 执行拓扑

### 目标与改动位置

从已有 Agent Run、Trace、事件、Audit 和新 stage / provider attempts 中投影出可读流程；它是只读解释视图，不是新编排引擎。

新增 `runtime/run_flow.py`、`contracts/schemas/run-flow.json` 与 `tests/test_run_flow.py`；修改 Runtime 查询、API、OpenAPI、生成客户端、`apps/desktop/src/api.ts`；新增 `apps/desktop/src/components/RunFlow.tsx`，在当前 App / 样式中局部接入，避免重写工作台。

### API 与 UI 合同

新增 `GET /api/tasks/{id}/flow?after_seq=0&limit=100`；`limit` 为 1–500。所有权 / Cloud auth 与现有 task 接口相同，越权使用相同的不可见资源响应。

响应字段：`schema_version, task_id, snapshot_seq, next_after_seq, has_more, completeness, nodes, edges`。

- Node：`id, stage_id, attempt, label, status, required, started_at, duration_ms, reason_codes, artifact_refs`。
- 状态限 `pending|running|completed|skipped|failed|blocked`；与 TaskStatus 分开。
- Edge：`source, target, relation=sequence|depends_on|fallback|produces`。只表示已记录依赖；当前固定链不能画成虚构的并行 Agent。
- 节点 ID 由 task / stage / attempt 等稳定身份生成，刷新不抖动；重试保留多个 attempt，fallback 画来源边。
- 从事件序号生成节点 upsert 增量，`snapshot_seq` 固定本次查询上界；超过 limit 分页。历史数据缺开始时间时返回 null / unknown，不补造耗时或完整拓扑。

ASCII 交互示意（拟新增视图）：

```text
Research Task                         [Timeline] [Flow]
------------------------------------------------------
[Trigger] -> [Data: fallback] -> [Quality: verified]
                                      |
                           [Research: completed]
                                      |
[News: skipped] ------------> [Rules: passed]
                                      |
                              [Decision: WATCH]

Selected: Data
Source    akshare -> tushare
Duration  1.8s
Artifacts [Snapshot] [Evidence] [Trace]
Reason    PRIMARY_PROVIDER_UNAVAILABLE
```

1. 默认折叠 Flow；用户可在 Timeline 与 Flow 切换，选择节点后定位现有证据 / Trace / Rule panel。
2. 桌面用简单 DOM / CSS 顺序布局，窄屏纵向排列；本包无需引入大型图形库。
3. 状态同时有图标 / 文字，不依赖颜色；节点支持键盘聚焦、选择与清楚的 accessible name。
4. 运行中复用现有 SSE 更新，断线后通过序号恢复；接口本身不拉 Provider、不重跑任务。
5. legacy task 显示 `completeness=legacy_incomplete` 和已有节点，不画未经记录的阶段。

### 验收

| ID | 必须通过的场景 |
|---|---|
| CAP-P0-05-A | 成功、fallback、可选跳过、必需失败、取消与重试各有对应拓扑；可定位产物 |
| CAP-P0-05-B | 与同一事件上界的 Trace / Audit 一致；重连增量无重复，分页不丢最终状态 |
| CAP-P0-05-C | 跨用户隔离、敏感字段脱敏、legacy unknown 正确；读取不产生外部调用 |
| CAP-P0-05-D | Desktop / Web、390px 窄屏与键盘操作可用，长错误码 / 标签不溢出 |

新增测试创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_run_flow.py' -v
./scripts/python.sh scripts/generate_ts_client.py --check
pnpm run build
pnpm run build:web
```

准备现有 UI smoke 的 Playwright CLI 后执行 `./scripts/trust-ui-smoke.sh`（脚本自行启动临时 API / Vite），补充 Flow 交互与窄屏截图。回退可移除 Flow 入口，保留 API、事件和历史数据，不影响 Timeline 或研究执行。

## 7. P0 整体交付检查

- 五个任务包的验收 ID 均有可定位测试 / 产物，状态从 Planned 更新需引用实际 commit。
- “同上下文 + 同版本 + 记录观点”的离线回放一致；当前个人设置修改不改变历史。
- live 不会因数据 / LLM 故障静默注入 fixture、虚假证据或无来源买卖建议。
- required failure、optional partial、stale 与 Rules block 分别展示，审批路径继续受保护。
- 完成 [统一离线回归](CAPABILITY_ROADMAP.md#6-统一施工与完成门槛)、迁移 / 备份恢复、多用户与受影响平台验证；未具备环境的检查单独列为缺口。
- 更新实现说明、需求矩阵与操作指南；P0 完成不自动宣告原有 MVP 发布门关闭。
