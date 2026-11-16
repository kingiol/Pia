# System Architecture

## 1. 架构原则

1. **Rules-First**：确定性规则优先于 LLM 判断。
2. **Evidence-First**：结论必须带证据、时间点和来源。
3. **Human-in-the-Loop**：AI 只能提出建议，用户拥有最终授权。
4. **Event-Driven**：系统由市场、数据和组合事件触发主动工作。
5. **Replayable**：任务、状态、工具调用和数据快照可回放。
6. **Least Privilege**：每个 Agent 只获得完成职责所需的 Tools。
7. **Modular Monolith First**：早期保持模块边界，避免过早拆成微服务。

## 2. 总体结构

```text
+-------------------------------+
| Tauri Desktop UI (MVP)        |
| React Workspace + Timeline    |
+---------------+---------------+
                | Local IPC / HTTP / SSE
+-----------v-----------+
| Python Local Runtime  |
| API + Orchestrator    |
| Agent + Rules + Events|
+-----+------------+----+
      |            |
      |            +------------------+
      |                               |
+-----v-----------+           +-------v--------+
| Agent Runtime   |           | Rules Engine    |
| LangGraph       |<--------->| Deterministic   |
| Pydantic        |           | Gates / Risk    |
+-----+-----------+           +-------+--------+
      |                               |
+-----v-----------+           +-------v--------+
| Tool Layer      |           | Audit / Memory  |
| Market / News   |           | Postgres        |
| Research / Port |           | SQLite/DuckDB   |
+-----+-----------+           +-------+--------+
      |                               |
+-----v-----------+           +-------v--------+
| Data Workers    |           | Notifications   |
| ETL / Quality   |           | Web / Email     |
+-----------------+           +-----------------+
```

## 3. 运行组件

| 组件 | 职责 | MVP 形态 |
|---|---|---|
| Tauri UI | Workspace、配置、审批和复盘 | React + TypeScript + Vite |
| Local Runtime | 用户、任务、研究结果、SSE | Python API + Sidecar |
| Orchestrator | 任务编排、状态机、人工暂停 | LangGraph |
| Agent Runtime | LLM、结构化输出、工具调用 | Python + Pydantic |
| Rules Engine | 数据、市场、组合和个股门禁 | Python pure functions |
| Event Engine | 事件检测、去重、优先级、调度 | Python Worker |
| Data Worker | 数据拉取、标准化、质量检查 | Python Worker |
| Adapter Layer | Provider 路由、能力声明、归一化和故障切换 | Python Ports & Adapters |
| Storage | 事务、分析和审计 | SQLite + DuckDB |
| Queue/Cache | 任务队列、冷却和锁 | MVP 可选 Redis |
| Notification | 邮件、Web Push、站内消息 | Web/PWA |

## 4. Agent 组织

```text
                    +----------------------+
                    | Investment Chief     |
                    | Plan / Route / Merge  |
                    +----------+-----------+
                               |
       +-----------------------+-----------------------+
       |                       |                       |
+------v------+        +-------v------+        +-------v------+
| Market      |        | Sector       |        | Portfolio    |
| Analyst     |        | Analyst      |        | Analyst      |
+------+------+        +-------+------+        +-------+------+
       |                       |                       |
+------v------+        +-------v------+        +-------v------+
| Technical   |        | Stock        |        | News         |
| Analyst     |        | Researcher   |        | Analyst      |
+------+------+        +-------+------+        +-------+------+
       +-----------------------+-----------------------+
                               |
                    +----------v-----------+
                    | Bull / Bear Debate   |
                    +----------+-----------+
                               |
                    +----------v-----------+
                    | Risk / Rules Review  |
                    +----------+-----------+
                               |
                    +----------v-----------+
                    | Decision Proposal    |
                    +----------------------+
```

### Agent 责任边界

| Agent | 负责 | 不负责 |
|---|---|---|
| Investment Chief | 规划、路由、汇总 | 修改规则、提交订单 |
| Market Analyst | 解释市场广度和环境 | 重新计算原始指标 |
| Sector Analyst | 行业轮动和相对强弱 | 访问订单权限 |
| Stock Researcher | 基本面、公告和公司事件 | 绕过数据有效性 |
| Technical Analyst | 趋势、量价和形态解释 | 直接决定买入 |
| Portfolio Analyst | 持仓、集中度、暴露 | 修改用户持仓 |
| News Analyst | 新闻和公告提取 | 生成无来源结论 |
| Bull/Bear | 结构化多空论证 | 更改数据或规则 |
| Risk/Rules | 执行门禁、风险分级 | 用自然语言替代确定性规则 |
| Decision | 形成建议状态和下一步 | 提交订单 |

## 5. 任务状态机

```text
QUEUED -> PLANNING -> RUNNING -> REVIEWING -> WAITING_APPROVAL
   |         |           |            |              |
   |         |           |            |              +-> APPROVED
   |         |           |            |              +-> REJECTED
   |         |           |            +-> BLOCKED
   |         |           +-> RETRYABLE
   |         |           +-> FAILED
   |         +-> CANCELLED
   +-> EXPIRED
```

状态约束：

- `BLOCKED` 必须包含阻断规则、输入数据和修复建议。
- `WAITING_APPROVAL` 只允许展示建议，不允许写入订单。
- `APPROVED` 在 MVP 中只代表用户批准“记录该行动意图”，不代表已成交。
- 任何 `RUNNING` 任务超过 SLA 必须转为 `RETRYABLE` 或 `TIMEOUT`。

## 6. 数据流

```text
External Sources
    -> Raw Landing
    -> Normalization
    -> Quality Checks
    -> Point-in-Time Snapshot
    -> Tools / Rules
    -> Agent State
    -> Evidence + Decision
    -> Workspace + Audit
```

所有研究结果必须携带：

- `task_id`
- `as_of`
- `observed_at`
- `source`
- `data_snapshot_id`
- `rule_snapshot_id`
- `confidence`
- `expires_at`

## 7. 部署形态

### 7.1 MVP：Tauri Desktop + Local Agent

```text
Tauri Desktop
      |
      v
React UI + Local IPC/HTTP
      |
      +-- Python Agent Sidecar
      +-- SQLite
      +-- DuckDB
      +-- Local Scheduler
      +-- Local Notifications
```

首版只要求单机闭环，不依赖 Cloud Agent、远程数据库或多设备同步。这样可以用固定 fixtures 和本地快照验证 Agent、Rules、Adapter、Event、Audit 和 UI 的完整行为。

### 7.2 后续：Cloud Execution Plane

```text
Web / iOS / Android
      |
      v
Cloud API + Agent Workers
      |
      +-- PostgreSQL (business + analytical tables)
      +-- Scheduler/Queue
      +-- Notifications
```

Cloud Agent 只在 Local-first MVP 完成后扩展，用于 Web、移动端、多设备同步、远程调度和集中运维。Cloud Execution Plane 替换执行宿主，不复制 Agent、Rules 和 Adapter 领域逻辑。

Cloud 存储于 2026-11-16 统一为 PostgreSQL，不再依赖 DuckDB 或 SQLite 文件。
Local 继续使用 SQLite + DuckDB。两种宿主复用相同分析存储方法，Cloud 的业务与
分析操作共享 PostgreSQL 连接及事务。部署与验收见 [Cloud Storage](CLOUD_STORAGE.md)。

### 7.3 Tauri 2 桌面宿主

桌面端直接采用 Tauri 2。MVP 阶段通过一个短周期集成验证确认 Python Sidecar、系统能力和打包链路可用：

- Python Sidecar 启动、心跳和崩溃恢复；
- SSE Agent Trace；
- 系统托盘和通知；
- 退出时资源清理；
- macOS/Windows 打包；
- 冷启动、空闲内存、研究任务峰值；
- 前端图表和 Markdown 兼容性。

Tauri 只负责窗口、托盘、通知、文件系统能力、Sidecar 生命周期和更新；Agent、Rules、数据和审计仍由 Python 运行时负责。

### 7.4 UI 技术选型

Tauri UI 采用：

```text
React
  + TypeScript
  + Vite
  + React Router
  + shared UI / domain packages
```

桌面端不使用 Next.js Server Runtime。Next.js 的 `output: "export"` 可以生成静态资源，但会关闭 SSR 和 API Routes；保留这些能力则需要额外运行 Node 服务，与 Python API/Agent Runtime 重复。

路由建议：

- Tauri 桌面端：优先使用 hash 路由，避免静态资源部署下的深链接回退问题；
- Web/PWA：可使用 history 路由；
- 业务组件、类型和 API Client 放在共享 package，不复制两套 UI。

如果未来需要 SEO、公开营销页或独立的 SSR Web 产品，再单独增加 Next.js Web App，不把 Next.js 强行嵌入 Tauri。

### 7.5 Native Mobile UI

iOS 和 Android 使用各自原生 UI：

```text
iOS:
SwiftUI -> Native API Client -> HTTPS/SSE -> Cloud API

Android:
Jetpack Compose -> Native API Client -> HTTPS/SSE -> Cloud API
```

移动端共享的不是 UI 代码，而是：

- OpenAPI/JSON Schema；
- 事件和任务协议；
- 认证和权限语义；
- 错误码和状态机定义；
- 云端 Agent、Rules、Data 和 Audit；
- 产品文案、设计 Token 和验收场景。

移动端独有：

- SwiftUI / UIKit；
- Jetpack Compose / Android Views；
- iOS/Android 导航和生命周期；
- 推送、后台刷新、生物识别和安全存储；
- 各自的图表、Markdown 和手势适配。

MVP 不引入 Kotlin Multiplatform 或其他跨语言共享运行时。先通过协议和生成代码共享稳定边界，避免移动端为了复用少量客户端逻辑而引入新的架构复杂度。

### 7.6 Agent Runtime：Local-first，Cloud later

MVP 采用“本地执行默认、云端执行后续”的运行模式：

```text
                         Control Plane
       +------------------------------------------------+
       | Auth | Profile | Rules | Tasks | Audit | Events |
       +----------------------+-------------------------+
                              |
                    AgentGateway / Task Lease
                       /                    \
                      /                      \
       +-------------v------------+   +-----v----------------+
       | Cloud Execution Plane   |   | Local Execution Plane |
       | API + Agent Worker       |   | Tauri + Python Sidecar|
       | Data Worker + Scheduler  |   | SQLite/DuckDB          |
       +-------------+------------+   +----------+-------------+
                     |                           |
                     +------------+--------------+
                                  |
                       Evidence / Decision / Trace
```

运行模式：

| 模式 | 执行位置 | 主要客户端 | 当前定位 |
|---|---|---|---|
| `local` | Tauri 本地 Python Sidecar | Desktop | MVP 默认 |
| `cloud` | 云端 Agent Worker | Web、iOS、Android | 后续扩展 |
| `auto` | 根据任务策略选择云端或本地 | Desktop | Cloud 扩展后再启用 |

控制面职责：

- 用户、Profile、Ruleset 和权限；
- 本地任务元数据和执行状态；
- 本地事件调度；
- 本地审计和通知。

执行面职责：

- Agent 推理和 Tool 调用；
- 数据读取和本地计算；
- Rules Engine；
- Trace、Evidence 和 Decision 生成。

当前边界：

- MVP 只要求 Tauri 启动本地 Python Sidecar；
- Web、iOS、Android、远程账号和跨设备同步不属于第一版完成条件；
- MVP 的 Ruleset、Approval 和 Audit 以本地 SQLite 为权威；
- Cloud 扩展时再增加任务租约、结果同步和冲突解决协议；
- Tauri 可以预留远程 Transport，但不能让远程依赖阻塞本地任务。

因此，“Local-first”描述的是 MVP 的执行优先级；“Cloud Agent”是后续执行宿主；“Multi-Agent”描述的是内部 Agent 协作方式，三者属于不同维度。

## 8. 安全边界

- 前端不持有模型供应商长期密钥。
- Tool 层校验调用者 Agent 身份和权限。
- 订单相关能力默认不存在或只读。
- 所有用户输入、外部内容和 Tool 返回值都视为不可信数据。
- Prompt 中的外部内容不能覆盖系统规则和用户规则。
- 审计日志追加写入，不能被普通用户流程删除。

## 9. 扩展路径

当以下信号出现时再拆服务：

- 多用户并发导致 Worker 资源隔离成为问题；
- 实时行情和分钟级事件需要独立扩缩容；
- 数据采集失败影响 Agent 任务隔离；
- 需要独立的通知、回测或券商适配团队。

## 10. 推荐目录

```text
pia/
  apps/
    web/
    desktop/
    ios/
    android/
  services/
    api/
    agent_runtime/
    data_worker/
    event_worker/
  packages/
    contracts/
    generated_clients/
    adapters/
    rules/
    tools/
    ui/
  migrations/
  tests/
    unit/
    integration/
    replay/
  docs/
```
