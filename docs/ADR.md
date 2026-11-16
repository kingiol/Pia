# Architecture Decision Records

## ADR-001：采用 Rules-First

**状态：Accepted**

### 背景

金融研究需要灵活解释，但市场指标、仓位和风险门禁需要可复现。

### 决策

LLM 负责理解、研究、解释和编排；程序负责数据计算、规则判断、权限和审计。

### 结果

- 规则可测试、可回放；
- Agent 不能通过措辞绕过门禁；
- 需要维护结构化规则和版本。

### 复审条件

只有在发现规则 DSL 无法表达真实策略时，才调整规则模型，不把规则判断移回自然语言。

## ADR-002：MVP 采用日线 + 收盘后研究

**状态：Accepted**

### 背景

实时行情需要授权、稳定连接、时钟一致性和更高运维成本。

### 决策

先完成日线、收盘后事件和研究闭环；盘中版本另行评估。

### 结果

- 可以优先验证产品价值；
- 降低供应商和系统复杂度；
- 不代表未来不支持实时。

## ADR-003：模块化单体优先

**状态：Accepted**

### 背景

一人公司早期最昂贵的是跨服务联调和运维，而不是单体内部模块调用。

### 决策

保持 API、Agent、Rules、Tools、Data Worker 的清晰模块边界，在一个可部署单元内交付。

### 复审条件

当多用户并发、实时数据或团队边界要求独立扩缩容时再拆服务。

## ADR-004：MVP 不自动下单

**状态：Accepted**

### 背景

自动交易的风险、合规和故障影响远高于研究辅助。

### 决策

MVP 只生成建议并请求人工审批；订单写权限默认不存在。

### 结果

- 用户保留最终授权；
- 可以先验证研究、规则和审计；
- 后续半自动交易需要独立 ADR。

## ADR-005：采用 Tauri 2 作为桌面宿主

**状态：Accepted**

### 背景

桌面端适合本地优先和常驻。用户已决定采用 Tauri 2，主要风险集中在 Python Sidecar、系统 WebView、权限配置和跨平台打包。

### 决策

桌面端直接采用 Tauri 2，并把 Python Sidecar 作为 MVP 的正式本地执行面。Web/PWA 保留为后续 Cloud Agent 的访问入口。

### 集成验证输出

- 启停和崩溃恢复；
- SSE Trace；
- 托盘与通知；
- 退出清理；
- macOS/Windows 包；
- 资源和兼容性测量。

## ADR-006：Evidence-First

**状态：Accepted**

### 背景

没有来源和时间点的金融结论无法复核，也容易被过期数据误导。

### 决策

研究结论必须引用证据；证据必须有 source、observed_at、as_of、expires_at、quality。

### 结果

UI、数据库、Agent State 和验收都围绕证据链设计。

## ADR-007：内部 Service/RPC，外部 MCP

**状态：Accepted**

### 背景

MCP 适合让外部 Agent 和开发工具使用能力，但内部高频调用需要更轻量、更可控的接口。

### 决策

内部 Agent 优先调用 Python Service/RPC；对外开放的工具能力再封装为 MCP Server。

### 结果

- 内部性能和权限更易控制；
- 外部扩展保留标准化入口；
- Tool Schema 需要单独版本管理。

## ADR-008：Tauri UI 采用 React + Vite，不采用 Next.js

**状态：Accepted**

### 背景

Tauri 桌面端最终加载的是前端构建产物。当前系统已经由 Python API、Agent Runtime 和 Sidecar 承担 API 服务、任务编排和数据访问职责。

Next.js 的静态导出适合生成静态资源，但不能使用 SSR 和 API Routes；如果保留 Next.js Server Runtime，则需要额外运行 Node 服务，增加桌面安装包、进程管理和故障恢复复杂度。

### 决策

Tauri UI 使用：

- React；
- TypeScript；
- Vite；
- React Router；
- 共享 UI、类型和 API Client packages。

Tauri 桌面端不使用 Next.js。Web/PWA 与桌面端共享 React 组件和领域模型；需要 SEO 或独立 SSR 页面时，再创建独立的 Next.js Web App。

### 结果

- 桌面包结构更简单；
- 不重复引入 Node Server Runtime；
- Tauri 与 Python Sidecar 的职责边界清晰；
- UI 可通过静态构建产物部署到 Web/PWA 和桌面端。

### 复审条件

只有在产品需要独立的 SEO、SSR 或 Next.js 专属 Web 能力时，才增加 Next.js Web App；不因此改造 Tauri 桌面壳。

## ADR-009：iOS 和 Android 使用原生 UI

**状态：Accepted**

### 背景

产品需要同时支持桌面研究工作台和移动端快速查看、提醒与审批。移动端的导航、生命周期、通知、后台任务和安全存储都高度依赖平台。

### 决策

- iOS 使用 SwiftUI，必要时通过 UIKit bridge 接入平台能力；
- Android 使用 Kotlin + Jetpack Compose，必要时通过 Android Views 接入平台能力；
- 不使用 React Native；
- 移动端默认连接云端 Agent，不在手机上运行 Python Agent；
- 跨语言共享通过 OpenAPI、JSON Schema、事件协议和生成客户端模型完成。

### 结果

- 移动端遵循各自平台的交互和生命周期；
- 不需要维护 React Native 与原生桥接层；
- 云端 Agent、Rules、Data 和 Audit 仍然由所有客户端共享；
- iOS/Android 的 API Client 可以从同一份 Schema 生成。

### 复审条件

只有在移动端需要大量本地业务计算，且 Swift/Kotlin 重复逻辑已经成为主要维护成本时，才评估 Kotlin Multiplatform 或其他共享核心方案。

## ADR-011：采用 Local-first Agent Runtime

**状态：Accepted**

### 背景

首个可验证产品需要尽快验证 Agent、Rules、数据、审计和 Research Workspace 的完整闭环。若一开始依赖云端、远程数据库和多端同步，会把基础产品验证与部署、账号、网络和运维问题耦合。

### 决策

采用 Local-first，并保留未来的执行面抽象：

- Tauri + Python Sidecar 是 MVP 默认执行面；
- SQLite/DuckDB 是 MVP 的本地存储；
- Cloud Agent 是 Local-first MVP 完成后的扩展执行面；
- Web、iOS、Android 在 MVP 不作为发布阻塞项；
- `AgentGateway` 屏蔽云端和本地执行位置差异；
- MVP 固定使用 `local`，Cloud 扩展后再启用 `cloud` 和 `auto`；
- MVP 不承诺跨设备同步和冲突解决。

### 结果

- 同一套 Agent、Rules、Tools 和数据契约可以运行在云端或本地；
- 桌面端可以在本地完成可验证闭环；
- Cloud 扩展只替换执行宿主和存储，不复制 Agent、Rules 和 Adapter；
- 需要在 Cloud 扩展阶段再为任务租约、结果同步、规则版本和审计权威建立协议。

### 复审条件

当 Cloud 扩展需要跨设备合并、远程调度或离线审批时，必须新增同步协议和冲突解决 ADR，不允许通过隐式覆盖解决。

## ADR-012：Local-first MVP 的范围冻结

**状态：Accepted**

### 决策

首个 MVP 只交付 Tauri Desktop、Python Local Agent、SQLite/DuckDB、日线数据、收盘后研究、Rules、Evidence、Audit 和人工审批。Cloud Agent、Web/PWA、iOS、Android、实时行情、跨设备同步和真实下单均不属于 MVP 发布门。

### 结果

- 测试可以使用固定 fixtures、回放和本地 E2E；
- 用户数据默认留在本机；
- Tauri Sidecar 生命周期、休眠恢复、备份和升级成为 MVP 的主要工程问题；
- 后续 Cloud Agent 必须遵守同一契约和 `AgentGateway`，不能创建第二套领域模型。

## ADR-010：所有外部能力通过 Adapter 接入

**状态：Accepted**

### 背景

市场数据、新闻、财报、券商、LLM、通知和存储供应商都会发生接口、限流、授权和可用性变化。若 Provider-specific SDK 直接进入 Agent 或 Rules，会导致业务逻辑被供应商锁定。

### 决策

所有外部能力通过明确的 Port/Adapter 接入：

- Domain Port 定义稳定的业务接口；
- Provider Adapter 负责认证、请求、重试、限流和 Provider DTO 转换；
- Normalizer 将 Provider DTO 转成统一领域模型；
- Provider Registry 根据能力、健康度、优先级和数据时效选择实现；
- Adapter Contract Tests 验证每个实现遵守同一契约。

### 结果

- 可以替换或增加数据源而不改 Agent；
- 可以在数据源异常时降级、切换或阻断；
- 每条数据保留 Provider、版本和快照来源；
- Broker 和 LLM 能力可以在 MVP 以只读、模拟或受限模式接入。

## ADR-013：Ruleset 使用版本化快照

**状态：Accepted**

### 决策

MVP 先使用已确认的 Ruleset `v1` 初始值。规则允许后续修改，但每次修改必须创建新的 Ruleset version 和 `rule_snapshot_id`。

### 结果

- 新任务使用当前激活的 Ruleset；
- 已完成或运行中的任务继续引用创建时的 Ruleset snapshot；
- Replay 必须显式指定 `data_snapshot_id` 和 `rule_snapshot_id`；
- UI 必须展示任务使用的规则版本；
- 修改规则不会改写历史任务、审批记录或审计结果。

## ADR-014：MVP 使用 DeepSeek OpenAI-compatible Chat Completions

**状态：Accepted**

### 决策

MVP 使用 DeepSeek 的 OpenAI-compatible API：

```text
base_url: https://api.deepseek.com
endpoint: POST /chat/completions
model: deepseek-flash
```

Agent Runtime 通过统一的 `LLMProvider` Port 调用，不直接依赖 DeepSeek SDK。MVP 默认开启流式输出、结构化输出和 Tool Calling；未来可在同一 Port 下增加其他模型或 Responses API。

### 结果

- Tauri Trace 可以直接消费流式事件；
- Agent Contract 不绑定某个供应商 SDK；
- 真实 API Key 只在 Python Local Agent 运行时读取，不进入 React UI、任务结果或日志；
- LLM credential 缺失时任务必须失败并显示 `CREDENTIALS_REQUIRED`，不切换到 Mock LLM；
- 迁移到其他 LLM 只需要新增 Adapter 和 Provider 配置。

## ADR-015：Decision Journal 复用事实模型，Memory 独立为派生层

**状态：Proposed**

Decision Journal 需要跨任务组织研究判断、证据、规则快照、审批和后续结果。若新增一套 `decision_records` 事实表，会与现有 `research_tasks`、`decisions` 和 `task_retrospectives` 重复，并引入同步、审计和回放的不一致风险。

因此 MVP 采用 `DecisionJournal` 聚合模块读取现有事实模型；`Patterns` 和 `Derived Memory` 只由确定性统计派生；只有用户确认后，Memory 才作为 `Confirmed Memory` 进入未来研究上下文。任何 Memory 都不能回写或覆盖原始 Decision Record。

如果后续查询规模或性能需要独立 read model，可以增加投影表，但投影不拥有事实，也不能改变原始记录的所有权和回放语义。

## ADR-016: Unified PostgreSQL Storage for Cloud

**Status: Accepted (2026-11-16)**

Cloud stores business records and analytical data in PostgreSQL. Local continues
to use SQLite and DuckDB. Cloud requires `PIA_POSTGRES_DSN` and does not silently
fall back to file databases.

The analytical repository retains its existing interface; the PostgreSQL
implementation shares the business repository connection and transaction
boundary. This removes cross-engine writes and separate analytical file backups
from Cloud deployment. It does not make a full research task one transaction.

Cloud has not launched, so deployments initialize a fresh PostgreSQL database;
development databases can be recreated without legacy DuckDB imports or old
backup compatibility. Cloud backups use one PostgreSQL dump. Reconsider a
separate analytical engine only after measured workloads justify its cost.
See [Cloud Storage](CLOUD_STORAGE.md) for scope, deployment and verification.
