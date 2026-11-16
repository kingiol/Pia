# P1 Implementation Plan

状态：**Implemented; local verified; external gates pending**；执行日期：2026-11-12；源码调查基线：2026-11-11、`11f64df`，施工起点 `a311380`。本文件保留施工规格，实际交付与配置见 [使用说明](CAPABILITY_DELIVERY.md)，验证见 [执行状态](CAPABILITY_IMPLEMENTATION_STATUS.md)。真实模型与远端 CI 验收仍需独立证据。

先读 [总路线图](CAPABILITY_ROADMAP.md) 与 [P0 计划](P0_IMPLEMENTATION_PLAN.md)。路径简写沿用 P0：`runtime/` 表示 `packages-py/pia_runtime/pia_runtime/`。以下新增接口、配置和测试文件都需要在实施时创建。

## 1. P1-01：版本化选股策略与解释

### 目标与改动位置

将当前固定扫描逻辑提取成可验证、可复算的策略。第一版只注册一个与现有行为一致的 `legacy_momentum_v1`，不默认加入新的投资公式，也不把候选排名当作买入授权。

| 文件 | 工作 |
|---|---|
| `runtime/screening.py`（新增） | Manifest 校验、因素注册表、确定性执行与解释 |
| `config/strategies/legacy_momentum_v1.yaml`（新增） | 首个版本化策略，使用 JSON-compatible YAML |
| `runtime/runtime.py` | `scan_candidates()` 复用策略执行器，保留现有 Profile / Rules 过滤 |
| `runtime/db.py`、`postgres.py`、迁移目录 | Manifest 内容与 scan 输入 / 输出冻结 |
| `runtime/api.py`、OpenAPI、生成客户端 | 策略列表、显式创建 scan 与历史读取 |
| `contracts/schemas/screening-strategy.json`（新增） | 严格 Manifest 契约 |
| `tests/test_screening.py`（新增）、现有 Runtime / 契约测试 | 等价性、异常、权限与历史复算 |

### 策略合同与默认行为

Manifest 示例是拟支持的完整第一版格式：

```json
{
  "schema_version": "1",
  "strategy_id": "legacy_momentum_v1",
  "version": "1.0.0",
  "required_capabilities": ["market_snapshot"],
  "filters": ["profile_universe", "eligible_instrument", "rules_liquidity"],
  "factors": [
    {"id": "momentum_breadth", "weight": 1},
    {"id": "turnover_scaled", "weight": 1}
  ],
  "missing_policy": "legacy_zero_with_warning",
  "score_round_digits": 4,
  "sort": ["score_desc", "input_ordinal_asc", "symbol_asc"]
}
```

- `momentum_breadth = change_pct * (1 + market.breadth)`；`turnover_scaled = average_turnover / 100000000`。保留当前 change_pct 的原始单位，不自行乘除 100。
- 先按现状 round 到 4 位再排序；相同 rounded score 按冻结输入顺序排列，symbol 作最后确定性键。这保留现有 Python stable sort 的有效输入行为。
- Profile 资产 / 板块、ST / 停牌 / 退市、新股观察期与最低成交额过滤继续执行；Manifest 只能收紧，不能关闭 Rules。
- 明确记录缺失与零的区别。legacy 策略保留现有缺值默认零语义但附 warning；其他新策略默认 `exclude_with_reason`。NaN / Infinity、非法类型与未知因子直接拒绝。
- 使用标准库 JSON 解析 `.json` 或 JSON-compatible `.yaml`，不执行 `eval`、Python 导入、Jinja 或任意表达式，不增加 YAML 依赖。
- Manifest hash 覆盖规范化完整内容；同 strategy / version 不允许不同内容。修改参数必须升级版本，不能覆盖历史。

### 实施步骤与 API

1. 提取当前实现的 golden fixture，覆盖普通股票、ETF、同分、空市场、缺值和全部过滤原因，再接入策略执行器。
2. 注册表仅从仓库 `config/strategies/` 的已校验文件加载；API 按 strategy ID 查找，不接受客户端任意路径或脚本。首版不做在线编辑 / 上传入口。
3. 新增 `screening_strategy_versions` 表冻结 Manifest；新增 `candidate_scans` 表冻结 `scan_id, user_id, strategy_id, version, strategy_hash, input_hash, as_of, profile/rules bindings, data references, output_json, created_at`。输入引用使用 P0 冻结内容，不依赖会覆盖的快照。
4. 新增 `GET /api/screening-strategies`、`POST /api/candidate-scans`、`GET /api/candidate-scans/{id}`。POST 接收 `as_of, strategy_id, strategy_version`，默认上述 legacy 版本，返回 201 与 scan；历史 GET 不取数。
5. 保留 `GET /api/candidates` 的现有字段和默认策略行为，增加 strategy 元信息与缺失解释；需要持久化复算的工作台扫描操作改用 POST。参数错误返回 400，未知策略 / 版本返回 404，跨用户 scan 遵循既有不可见资源规则。
6. 每个候选返回各因素原值、变换后值、weight、contribution、score、通过的过滤条件与 Evidence 引用；被排除标的在 scan 明细提供稳定原因。分页列表不携带全量原始数据。
7. 工作台新增紧凑策略选择与因素展开，默认选择 legacy；复算只使用冻结 scan 输入与该版本，不请求 Provider。算法版本缺失或 hash 不匹配时明确拒绝复算，不以最新版代替。

ASCII 示意：

```text
Candidates   Strategy [legacy_momentum_v1 v1.0.0 v] [Scan]
-------------------------------------------------------
Symbol      Score     Snapshot       Quality
600000.SH   12.3400    market-001     verified
  momentum_breadth    value  9.3400   contribution 9.3400
  turnover_scaled     value  3.0000   contribution 3.0000
  [Evidence] [Scan inputs]
```

### 验收、验证与回退

| ID | 必须通过的场景 |
|---|---|
| CAP-P1-01-A | 同一有效输入下新旧默认扫描候选、分数、顺序一致，包含 round 后同分情况 |
| CAP-P1-01-B | 缺值 / 零可区分；非法数值、未知因子、路径穿越和脚本字段拒绝 |
| CAP-P1-01-C | 同版本不同内容拒绝；修改策略 / Profile 后历史 scan 复算不变 |
| CAP-P1-01-D | 策略不能放宽 Rules；stale 数据或高分候选不能绕过 P0 合成与审批 |
| CAP-P1-01-E | 用户隔离、解释与实际分数一致；无候选也返回明确排除原因 |

新增测试创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_screening.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_runtime.py' -v
./scripts/python.sh scripts/generate_ts_client.py --check
pnpm run build:web
```

回退到 legacy 默认策略即可；保留已记录的策略版本与 scan，不删除历史。新投资因子及其阈值需另外评审，不能以“配置化”绕开产品判断。

## 2. P1-02：多路由 LLM fallback 与成本预算

### 目标与改动位置

增强已有 `ModelRouter`，支持显式授权端点之间的运行失败切换，解决全局 `_active` / `last_usage` 导致的并发串账，并让预算在实际发请求前生效。

修改 `runtime/llm.py`、`runtime.py`、`config.py`、`credentials.py`、`db.py`、`postgres.py`、usage / metrics API；新增 `runtime/llm_budget.py`、`config/llm-policy.example.json`、`tests/test_llm_budget.py`、`tests/test_model_fallback.py`。保留 DeepSeek 现有 Port；第二路由复用 OpenAI-compatible HTTP 适配方式，不要求新 SDK 或新订阅。

### 配置合同

新增可选环境变量 `PIA_LLM_POLICY_PATH`。未设置时保持现有单 DeepSeek route 与凭据方式，沿用当前 model / base URL；不自动发现其他服务商或上传个人上下文。

策略文件的严格字段：

| 字段 | 默认 / 约束 |
|---|---|
| `schema_version` | `"1"` |
| `routes` | 按 priority、route_id 排序；包含 endpoint、model、credential_ref、capabilities、价格与 allowed_data_classes |
| `allowed_data_classes` | 最小默认 `market_public`；`portfolio`、`confirmed_memory` 需用户对每个端点显式允许 |
| `max_routes_per_stage` | `2`，仅在确有第二条已配置 route 时生效 |
| `max_http_attempts_per_stage` | `6`，包含所有 route、retry、tool round；同时服从 P0 时间与工具上限 |
| `task_budget_usd / user_daily_budget_usd` | 默认 null，表示未设置金额上限；仍受 P0 工程预算限制 |
| `input_cost_per_1k / output_cost_per_1k` | 十进制非负价格；未填或旧配置的 0 按 unknown 处理，不当成免费 |

不在示例中写真实模型账号、当前价格或密钥。新增第二端点是数据去向决策：只有用户配置并允许相应数据类别才可传输；每个 route 发送经过白名单筛选的 prompt，完整 pack 不直接发往模型。

### fallback 与 usage 合同

| 情况 | 行为 |
|---|---|
| Rate limit、网络不可达、服务端暂时故障，且尚未暴露输出 | 在剩余预算内尝试下一条已授权合格 route |
| 缺凭据、认证失败、内容安全拒绝 | 明确失败，不用 fallback 绕过权限或拒绝 |
| JSON / Schema 错误 | `LLM_INVALID_RESPONSE`；不自动跨模型反复“修答案” |
| 任一 stream delta 已展示，或任一 tool 已执行 | 不透明重试 / 切换被禁止；保留部分输出与原因，用户可显式新建任务 |
| route 能力不足、价格未知且配置了金额硬上限 | 调用前排除，返回清楚的能力 / 预算原因 |

每次调用使用局部 `GenerationRequestContext`，结果与事件携带不可变的 `request_id, attempt_id, route_id, provider_id, model, usage, cost_status`。Runtime 以该上下文结算，禁止从全局 active route 推断谁调用了什么。所有失败尝试、工具轮次和 retries 都进入账本，不能只记录最后成功模型。

### 实施步骤

1. 将模型选择、执行与 usage 归属分离；同一 client 不复用可变 history 作为跨任务账本，单请求中记录完整 attempts。
2. 复用现有错误映射与重试退避；Router 负责总次数 / 时间，client 不另起不受控重试链。流式开始后遵守不可透明切换边界。
3. 新增 `llm_attempts` 与 `llm_budget_reservations` 表，记录用户 / 任务 / request / attempt、价格版本、预留、已知费用与未知 usage。日预算按 UTC 日期分桶，UI 说明该边界。
4. 每次 HTTP 调用前，在事务内同时检查任务和用户日预算，预留本次允许输入 / 输出的成本。SQLite 使用写事务；PostgreSQL 对预算行加锁，竞争失败不得发出请求。十进制计算，禁止二进制浮点金额累计。
5. 已知 tokenizer 时按该模型准确计算；没有 tokenizer 时使用 UTF-8 字节数作为保守估算并标记 estimated。估算不能被宣传为服务商账单硬上限；金额严格模式只接纳已声明、可验证 token 上界的 route，其余调用前拒绝。
6. 成功响应以真实 usage 结算并释放差额。超时 / 断流且缺 usage 时标 `unknown`，保留本次预留作为保守已用额；不能按 0 释放后继续无限切换。崩溃后按持久化 request 状态恢复，避免重复扣账或重复发请求。
7. 同任务预算和用户日预算都耗尽时，必需 LLM 阶段明确失败，可选阶段跳过。沿用 P0 stage policy，不因为“模型贵”悄悄用未经授权的便宜端点。
8. metrics 与任务详情显示已知成本、保守预留、未知次数和 route 尝试链。现有 `cost_estimated` 兼容保留，新增 `cost_status=known|estimated|unknown`；旧未知金额不能显示成“免费”。

### 验收、验证与回退

| ID | 必须通过的场景 |
|---|---|
| CAP-P1-02-A | 假主路由 429 / 503 → 假备路由成功，次数、顺序、时间和所有尝试费用可追溯 |
| CAP-P1-02-B | 缺凭据、401、安全拒绝、Schema 错误不跨模型；delta / tool 后失败不透明重播 |
| CAP-P1-02-C | 同一用户并发任务只允许预算容纳的请求发出；不同用户费用不串账 |
| CAP-P1-02-D | 失败 / 断流 usage unknown 不计 0；重启、午夜 UTC 切换与重复结算保持一致 |
| CAP-P1-02-E | 未声明 token 上界或价格时金额严格模式调用前拒绝；未设置金额上限也有工程预算 |
| CAP-P1-02-F | 第二端点未授权持仓 / 记忆时不收到这些字段；凭据不进入日志、flow 或 export |

新增测试创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_model_fallback.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_llm_budget.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_llm.py' -v
./scripts/cloud-e2e.sh
```

离线 fake transport 验收不产生费用。PostgreSQL 行锁预算竞争需另跑该后端集成测试，不用单线程 SQLite 测试代替。回退可移除第二 route，保留 request 账本与现有预算限制；禁用 fallback 不能清空已经发生的费用。

## 3. P1-03：按改动影响面分层 CI

### 目标与改动位置

让每个 PR 运行必要的离线验证，并把真实网络 / 凭据 / 平台证据留在明确的专门流程。先修正现有 `npm ci` / npm cache 与 `pnpm` 脚本、锁文件不一致的问题。

修改 `.github/workflows/desktop.yml`、`provider-freshness.yml`、`release-gates.yml`；新增 `.github/workflows/ci.yml`、`scripts/ci_changes.mjs`、`scripts/ci_changes.test.mjs`；`scripts/test.sh` 保留一键全量语义，按需新增 `scripts/test-runtime.sh` 抽取 Python 检查，避免重复跑所有前端构建。

### 影响面与工作流合同

`ci.yml` 总是运行 `changes` 与 `ci-required`，不要用顶层 paths 过滤使 required status 永远 pending。changes 使用 base / head 的 Git diff（支持新增、修改、删除、重命名），将文件列表交给受版本管理的脚本，输出固定布尔值。

| 改动路径 | 必须触发的离线 job |
|---|---|
| `packages-py/**`、`pyproject.toml`、Runtime 测试 | runtime；Sidecar 打包边界变化再触发 desktop |
| `contracts/**`、生成器、`packages/contracts/**` | contracts、runtime、web、desktop 前端编译 |
| `apps/desktop/src/**`、`apps/web/**` | web 与 desktop 前端编译；Web 复用 Desktop 必须同时覆盖 |
| `apps/desktop/src-tauri/**`、Sidecar spec / 构建与启动脚本 | macOS / Windows Sidecar + Tauri build / health |
| `apps/android/**`、`apps/ios/**` | 只触发对应平台；保留现有 Android build，iOS 使用可用 macOS 工具链编译验证 |
| `package.json`、`pnpm-lock.yaml` | contracts、web、desktop；依赖可能影响所有 JS 消费者 |
| workflow、CI 脚本、测试脚本、`.github/**` | CI 分类自测，并保守触发受影响执行面；无法分类则全量 |
| 仅 Markdown、docs 图片 | docs；不消耗真实服务凭据或跑平台打包 |

未知扩展名 / 根配置保守走全量，不默认跳过。`tests/**` 按对应执行面分类，无法对应时 runtime + contracts；受测脚本变更即使只改注释也不能当成 docs-only。

1. Node 版本保持 22；安装 package.json 指定的 `pnpm@12.18.0`，使用 `pnpm install --frozen-lockfile` 与 pnpm store cache。workflow 引用的 Action 在实施时按官方文档核对并固定经核验版本，不在本计划臆造 SHA。
2. runtime job 运行 unittest / compileall；contracts job 检查生成客户端与契约测试；web job 跑 `pnpm run build:web`；desktop 前端跑 `pnpm run build`。平台 job 保留 Sidecar health / 打包验收。
3. `ci-required` 使用 `always()` 汇总 needs：被 changes 判定必须运行的 job 只有 success 才通过；failure / cancelled / 意外 skipped 都失败，明确不需要的 skip 才接受。changed-files 分类失败时聚合门失败。
4. docs job 检查仓库内相对链接与文档导航，不依赖付费服务；新增 workflow classifier 测试覆盖所有上表路径。
5. freshness 保留 schedule / workflow_dispatch，不进普通 PR 离线门。没有凭据 / 确定交易日的结果写 skipped / not verified，不记 passed。
6. live release 仅人工触发且使用受保护 Environment 的 secrets；fork PR 不访问 secrets，不用 `pull_request_target` 执行 PR 代码。
7. `release-preflight` 保留机器可读报告与所有平台产物摘要。将“采集证据”和“发布判定”分离：收集步骤可继续上传报告，最终汇总门必须传播未满足 / 失败状态，不能被现有 `continue-on-error: true` 吞掉。
8. 发布前报告缺少凭据、缺平台或真实失败的区别；release 输入必须明确当前验收日期，不能长期默认沿用 `2026-11-06`。

### 验收、验证与回退

| ID | 必须通过的场景 |
|---|---|
| CAP-P1-03-A | docs-only、Runtime、contracts、共享 Desktop UI、Rust、移动端、根配置各触发正确 jobs |
| CAP-P1-03-B | rename / delete / 未知路径 / 分类失败有正确回退，不漏执行面 |
| CAP-P1-03-C | 必需 job 故意失败、取消或意外 skip 时聚合门失败；docs-only 正常收敛 |
| CAP-P1-03-D | 从干净 checkout 用 frozen lock 安装与构建；无 npm ci / pnpm 缺失混用 |
| CAP-P1-03-E | fork PR 无 secrets；live 缺证据不能显示 release ready；报告始终可下载 |

新增脚本创建后运行：

```bash
node --test scripts/ci_changes.test.mjs
./scripts/python.sh scripts/generate_ts_client.py --check
./scripts/test.sh
pnpm run build:web
git diff --check
```

workflow 语法可用 `actionlint` 时另行检查，工具不存在记录未运行；本地脚本成功不能代替 GitHub 上对 success / skipped / failed 传播的验证。推送 / 改 branch protection 需相应授权；实施 PR 应附 CI 运行证据，并由仓库管理员将 `ci-required` 设为合并必需检查。

回退到全量离线 CI 即可，不恢复锁文件不一致或吞失败的发布门。不要在新聚合门实际运行前删除旧 required check，避免出现无法合并的配置窗口。

## 4. P1-04：公开部分结果与降级协议

### 目标与改动位置

把 P0 内部阶段缺口提升为 API、UI、历史与导出共同使用的稳定协议。TaskStatus 表示任务生命周期，ResultMetadata 表示结果完整性，两者分开。

新增 `contracts/schemas/result-metadata.json`、`tests/test_result_metadata.py`；修改 `runtime/models.py`、`runtime.py`、`api.py`、`db.py` / `postgres.py`、Decision / Task 契约、OpenAPI、生成器及 Desktop API / 详情组件。复用 P0 数据，不再新增另一套降级计算器。

### ResultMetadata v1

| 字段 | 语义 |
|---|---|
| `schema_version` | `"1"` |
| `completion` | `complete|partial|none|unknown`，unknown 用于无法证明完整性的历史记录 |
| `degraded` | 存在 fallback / stale / missing / budget omission 等限制 |
| `missing_capabilities` | 稳定 capability ID 数组 |
| `reasons` | `{code, stage_id, capability, required, retryable, artifact_refs}` 数组 |
| `quality_summary` | 沿用 verified / partial / stale / unavailable 质量，不与 completion 混用 |
| `context_pack_id / policy_version` | 指向 P0 冻结上下文与 stage policy |
| `action_eligible` | Data / Rules / synthesis 共同导出的布尔值；不是用户审批授权 |

初始 reason code 限定为 `PROVIDER_FALLBACK, LAST_GOOD_SNAPSHOT, STALE_DATA, CAPABILITY_UNAVAILABLE, OPTIONAL_STAGE_FAILED, STAGE_TIMEOUT, TOKEN_BUDGET_EXCEEDED, COST_BUDGET_EXCEEDED, LLM_STREAM_INTERRUPTED, CONTEXT_INCOMPLETE, LEGACY_RESULT_UNKNOWN`。复用已有错误码时建立显式映射，未知新错误以 `CONTEXT_INCOMPLETE` 与原始稳定码引用表达，不暴露异常全文。

- 所有必需与适用可选阶段成功：complete；如使用了合格备源，仍可 `degraded=true`。
- 必需阶段成功、适用可选阶段缺失：partial；不适用的 optional skip 不算缺失。
- 没有可用研究结果：none；历史无法确认：unknown。
- 不满足关键数据 / 规则时 `action_eligible=false`；complete 不等于可行动，partial 也不自动突破门禁。P0 保守 WATCH 的新任务仍为 false。

### 实施步骤

1. 从 pack / stage / provider / synthesizer 生成一次 metadata，在 Decision 完成时与结果同事务持久化。列表只返回摘要，详情返回 reasons；SSE 发送与已持久化版本一致的终态事件。
2. 以 additive 字段 `result_metadata` 接入 Task / Decision 详情、历史与上下文导出，旧字段不删除。未知字段被旧客户端忽略；新客户端遇到缺字段显示“历史完整性未知”，不能默认 complete。
3. 新增 `GET /api/tasks/{id}/export` 供所属用户显式下载 JSON，包括契约版本、冻结上下文、Decision、metadata 与来源；共享 P0 full-context 脱敏和审计逻辑，不另做无权限导出路径。
4. UI 在结论附近展示完整性与缺口，点 reason 定位 Flow / Evidence。retryable 原因提供现有重试 / 新建任务入口；不会直接覆盖历史 pack。
5. 审批端再次以服务端当前数据时效、Rules 与 Decision 校验资格。隐藏按钮只是辅助，旧客户端直接请求也不能绕过。
6. legacy 结果按现有记录能证明的范围只读映射；不批量把旧 DONE 回填为 complete。导入 / 恢复后的 metadata 与 pack hash 必须一致。

ASCII 示意：

```text
Decision: WATCH                    Result: Partial
--------------------------------------------------
News unavailable; required checks completed.
Data: verified     Rules: passed    Action: review

Limitations
! CAPABILITY_UNAVAILABLE   sources.news   [Evidence]
! OPTIONAL_STAGE_FAILED    news           [Flow]

[View context] [Export]
```

实际界面文案按现有产品语言处理；英文示意仅表示结构。不能显示“Partial 但可以买入”等越过服务端资格的引导。

### 验收、验证与回退

| ID | 必须通过的场景 |
|---|---|
| CAP-P1-04-A | complete + fallback、partial、none、legacy unknown 分别建 fixture，生命周期状态保持原枚举 |
| CAP-P1-04-B | API、SSE 终态、历史、Flow 与导出对同一任务的原因 / metadata 一致 |
| CAP-P1-04-C | 新旧客户端互通；缺字段不当 complete；长原因列表、空列表与断线恢复显示正确 |
| CAP-P1-04-D | 旧客户端请求审批也受当前门禁限制；partial / stale 不绕过必需证据要求 |
| CAP-P1-04-E | 跨用户导出拒绝；无密钥 / header / 敏感 URI；备份恢复后内容与 hash 一致 |

新增测试创建后运行：

```bash
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_result_metadata.py' -v
PYTHONPATH=packages-py/pia_runtime ./scripts/python.sh -m unittest discover -s tests -p 'test_contracts.py' -v
./scripts/python.sh scripts/generate_ts_client.py --check
./scripts/e2e.sh
pnpm run build
pnpm run build:web
```

UI 验收覆盖 Desktop / Web、390px 视口、键盘和屏幕阅读器状态标签；必要的浏览器依赖按现有 smoke 脚本准备。回退 UI 时 metadata 与服务端 gate 保留，不能把 legacy unknown 改写成完整成功。

## 5. P1 整体交付与后续决策

完成条件：四包验收有证据、默认扫描保持兼容、并发费用账本正确、CI 聚合门实际运行、API / UI / 导出语义一致，并通过 [统一完成门槛](CAPABILITY_ROADMAP.md#6-统一施工与完成门槛)。

新增投资策略、开启新模型数据去向、调整真实预算金额及最终发布仍由用户决定。本计划提供可执行机制与保守默认值；不替用户决定投资参数、订阅付费服务、修改仓库保护设置或发布产品。
