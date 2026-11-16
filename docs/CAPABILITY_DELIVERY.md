# Capability Delivery

执行日期：2026-11-12，基于 `a311380` 的工作树。对应 [P0 计划](P0_IMPLEMENTATION_PLAN.md)、[P1 计划](P1_IMPLEMENTATION_PLAN.md)；验收证据见 [执行状态](CAPABILITY_IMPLEMENTATION_STATUS.md)。

## 研究与回放

创建任务时冻结 Profile、Rules、已确认 Memory；取数后生成 `DecisionContextPack v1`。SQLite / PostgreSQL 的输入与 pack 表禁止更新、删除。回放创建子任务，保持内容 hash 和原始 data_mode，记录 source_pack_id，不重新请求 Provider 或模型。

`GET /api/tasks/{id}/context` 默认 overview，返回块状态、时间、来源和 hash；`?view=full` 返回所属用户的冻结内容，并记录审计。旧任务没有 pack 时返回 `legacy_incomplete`，回放拒绝 `REPLAY_CONTEXT_INCOMPLETE`；不会从当前设置补齐。

图节点实际输出转换为 AgentOpinion。行情、持仓、规则计算与模板观点区分 origin；证据必须属于 pack，符合标的、业务时间与质量要求。无效观点隔离、同命题多空冲突降低 confidence。新任务只生成 WATCH、NO_ACTION、BLOCKED；`suggested_action` 不具有授权效果，high confidence 不自动授予。

## 数据来源与执行边界

Provider 熔断按 provider / capability / credential scope 隔离。`provider_attempts` 保存每次实际尝试，结果和 Evidence 保存选中来源及尝试链。配置中的 `retry_attempts=2` 表示总共最多两次尝试，Runtime / DataWorker 不再重复套用整批重试。

live 不会退到 Fixture。所有 live 来源失败时，只读取同用户、同能力、同标的、`as_of <= analysis_as_of` 的 last-good；保留原始时间与过期年龄。过期数据不能生成新可行动结果。公开 health 不携带用户快照或凭据错误全文。

七个阶段使用 monotonic 运行预算，暂停时间扣除，阶段尝试写入 `task_stage_runs`。行情等必需数据与可选补充数据分开；可选故障进入结果缺口。真实 AKShare / Tushare 阻塞调用使用 spawn 子进程；超时 / 取消后 terminate、join、必要时 kill。冻结 Sidecar 入口调用 freeze_support。

必需阶段临时来源故障进入 RETRYABLE，预算耗尽为 TIMEOUT；数据 / Rules 不满足时保留 BLOCKED。公告来源所在阶段按必需阶段执行。暂停在 Provider 调用边界生效，已发送的请求仍按原期限回收；已经完成的阶段不会重复占用后续预留预算。

交易日历统一 ISO 日期。AKShare 缺少真实日历时的工作日估算标为 partial；不会充当已验证的必需日历，允许切换到合格来源或由数据门禁阻断。

LLM 每请求输入 32 KiB、输出 1024 tokens、两轮工具往返与累计八次工具调用，阶段总 HTTP 尝试最多六次。可选内容按固定优先级裁剪，无法满足大小上限时失败，不截断 JSON 或 Rules。服务端已经接收的请求不能保证取消收费。

## 工作台与结果协议

研究详情增加折叠 Flow、结果完整性、缺口和费用状态。Flow 来自真实事件，保留顺序、重试与 fallback，不虚构 Agent 并行。

Flow 随现有 SSE 更新按序号增量合并；每轮分页固定 snapshot_seq，断线后从最后已合并序号继续。取消 / 失败将仍在运行的节点标为终止，不遗留永久 running。

```text
Research
  Decision WATCH        Result complete / partial / none / unknown
  [Execution flow]
    stage -> agent -> rules -> synthesis -> decision
  Limitations -> Flow / Evidence
  [Replay] [Export]
```

- `GET /api/tasks/{id}/flow?after_seq=0&limit=100`：稳定节点 upsert；limit 为 1–500。分页可携带首屏 `snapshot_seq` 固定上界。
- `GET /api/tasks/{id}/export`：所属用户显式导出，包含冻结上下文、Decision、ResultMetadata；复用 full-context 脱敏与审计。
- 浏览器保留服务端 JSON 原文下载，避免 JavaScript 重新编码数值改变 Context Pack 的 hash。校验时使用 Runtime 的 `validate_pack`。
- `result_metadata` 区分结果完整性与 TaskStatus；旧记录缺少证明时为 unknown，不回填 complete。API、SSE 终态、历史、导出读取同一持久化值。
- `action_eligible=false` 是本批次的保守默认值。服务端再次限制审批；继续研究、加入观察、暂不行动等研究操作保留。旧客户端的 APPROVE 请求也受限制。
- 费用界面分开显示已知费用、保守占用、未知次数，日预算按 UTC 日期结算。未知费用不表示免费。

## 版本化扫描

首个策略为 `legacy_momentum_v1@1.0.0`，Manifest 位于 `config/strategies/legacy_momentum_v1.yaml`，使用标准 JSON 解析。只允许注册因素和过滤器，不执行表达式、脚本、任意路径；同 ID / version 内容改变时启动拒绝。

默认公式保持 `round(change_pct * (1 + breadth) + average_turnover / 100000000, 4)`，先 round 后按输入顺序稳定排序。Profile、ST / 停牌 / 退市、新股和流动性过滤保留；缺值附解释，非有限值拒绝。

- `GET /api/screening-strategies`：策略版本列表。
- `POST /api/candidate-scans`：`as_of, strategy_id, strategy_version`，冻结策略 hash、输入及输出。
- `GET /api/candidate-scans/{id}`：所属用户历史。
- `POST /api/candidate-scans/{id}/replay`：离线复算，核对原策略及输入 hash。
- 兼容的 `GET /api/candidates` 保留；工作台显式扫描使用 POST。排名只用于研究，不自动成为买卖授权。

## LLM 路由与预算

不设置 `PIA_LLM_POLICY_PATH` 时保留现有 DeepSeek 单路由与凭据读取方式。设置时加载严格 JSON，示例为 [llm-policy.example.json](../config/llm-policy.example.json)。示例不包含真实密钥或价格。

每条 route 明确 endpoint、model、credential_ref、能力、priority 与 allowed_data_classes。`portfolio` / `confirmed_memory` 必须分别允许；默认只有 market_public。只读工具同样执行数据类别限制，完整 pack 不直接发送。

临时网络故障、429、服务端故障可在尚未展示任何 delta、尚未执行任何工具时切换到下一条已配置路由；缺凭据、认证、安全拒绝和 JSON 错误不会跨模型绕过。请求使用独立 GenerationRequestContext，路由与 usage 不通过全局可变 active 状态推断。

金额限制默认 null。启用 task_budget_usd / user_daily_budget_usd 时，route 必须有正数价格和显式 `token_upper_bound="utf8_bytes"` 声明；未声明可验证上界时调用前拒绝。UTF-8 字节数作为保守输入计量上界，需由端点配置者确认适用，不等同于服务商账单保证。

发请求前，SQLite 写事务 / PostgreSQL 预算行锁同时检查任务和用户日上限并预留。成功用真实 usage 结算；超时、断流或缺 usage 保留预留，费用为 unknown；重复结算幂等。`llm_attempts` 与 `llm_budget_reservations` 保留失败路由和所有 HTTP 尝试，备份一并保存。

## CI 与验证

`ci.yml` 总是运行 changes 与 ci-required；分类器使用 Git diff，未知路径保守全量。仅文档检查链接与索引，不使用真实凭据。共享 Desktop UI 同时编译 Web / Desktop；平台代码触发对应构建。必需 job 只有 success 才满足聚合门，异常 skip / cancelled / failure 都失败。

Node 22 与 package.json 指定 pnpm 配合 frozen lockfile。live release 仅 workflow_dispatch，绑定 `live-release` Environment，日期必须显式填写；预检失败传播到 job，证据始终尝试上传。

旧 `contracts-and-runtime` 检查暂时保留，避免先删除已有 required check。管理员须在新 CI 实际成功后，把 `ci-required` 设为必需检查，再决定移除兼容 job；本批次没有修改分支保护或推送代码。Environment 是否启用审批保护也需由管理员确认。

本地运行：

```bash
./scripts/test.sh
./scripts/replay.sh
./scripts/e2e.sh
./scripts/postgres-cloud-e2e.sh
./scripts/recovery-e2e.sh
./scripts/chaos-e2e.sh
./scripts/cloud-backup-restore-e2e.sh
pnpm run build:web
```

Windows、真实数据源 / 模型、远端 Actions 与发布验收必须分别提供运行证据。本地单元测试不替代它们。
