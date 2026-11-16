# Monorepo Structure and Code Reuse

## 1. 总体决策

项目采用“共享协议和业务核心，平台独立 UI”的 Monorepo，MVP 以 Tauri Desktop 为唯一正式入口：

```text
Shared Backend / Contracts / Protocols
              |
      +-------+--------+---------+---------+
      |                |         |         |
    Web             Tauri      iOS     Android
 React + Vite    React + Vite SwiftUI Compose
```

核心结论：

- Web 和 Tauri 共享 React DOM UI；
- iOS 使用 SwiftUI；
- Android 使用 Kotlin + Jetpack Compose；
- Python Agent、Rules、Data、Audit 首先由 Tauri Sidecar 本地运行，未来可部署到 Cloud Agent；
- Web、iOS/Android 在 MVP 只保留契约和客户端骨架，不阻塞本地闭环；
- 移动端通过协议、生成客户端和产品模型共享底层能力。
- Agent 通过 `local`、`cloud`、`auto` 三种运行策略抽象执行位置，MVP 固定使用 `local`。

## 2. 推荐目录

```text
pia/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   ├── public/
│   │   └── vite.config.ts
│   │
│   ├── desktop/
│   │   ├── src/
│   │   │   └── main.tsx
│   │   └── src-tauri/
│   │       ├── src/
│   │       ├── capabilities/
│   │       └── tauri.conf.json
│   │
│   ├── ios/
│   │   ├── PiaApp/
│   │   ├── PiaAppTests/
│   │   └── Package.swift
│   │
│   └── android/
│       ├── app/
│       ├── build.gradle.kts
│       └── settings.gradle.kts
│
├── packages/
│   ├── contracts/
│   │   ├── openapi.yaml
│   │   ├── events/
│   │   ├── schemas/
│   │   └── generated/
│   │       ├── typescript/
│   │       ├── swift/
│   │       └── kotlin/
│   │
│   ├── app-web/
│   │   ├── routes/
│   │   ├── layouts/
│   │   └── providers/
│   │
│   ├── features/
│   │   ├── research/
│   │   ├── portfolio/
│   │   ├── watchlist/
│   │   ├── market/
│   │   ├── alerts/
│   │   └── approvals/
│   │
│   ├── api-client/
│   │   ├── typescript/
│   │   ├── swift/
│   │   └── kotlin/
│   │
│   ├── domain/
│   ├── auth/
│   ├── telemetry/
│   ├── design-tokens/
│   ├── ui-web/
│   └── tooling/
│
├── services/
│   ├── api/
│   ├── agent-runtime/
│   ├── data-worker/
│   └── event-worker/
│
├── packages-py/
│   ├── pia-core/
│   ├── pia-contracts/
│   ├── pia-adapters/
│   ├── pia-rules/
│   ├── pia-tools/
│   └── pia-data/
│
├── infra/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── replay/
│   └── contract/
├── docs/
├── package.json
├── pnpm-workspace.yaml
├── turbo.json
└── pyproject.toml
```

MVP 的平台优先级是 macOS 首发、Windows 同期支持。`apps/desktop` 和
`packages-py` 是首批发布目录；`apps/web`、`apps/ios` 和 `apps/android`
已经提供可构建的客户端、认证、任务/通知、设备注册和增量同步能力，
但不进入 Local-first MVP 的桌面发布门。移动端推送凭据和真机后台运行仍
需要平台验收。

## 3. 代码复用边界

### 3.1 100% 共享

这些内容只保留一个事实来源：

- OpenAPI 和 JSON Schema；
- 事件类型和任务状态；
- Decision、Evidence、Approval、Portfolio 等领域模型；
- 错误码和权限语义；
- 云端 Agent Runtime；
- Rules Engine；
- 数据标准化和质量检查；
- 审计模型；
- 产品验收场景。

### 3.2 Web 与 Tauri 共享

Web 和 Tauri 都使用 React + TypeScript + Vite，可以共享：

- Research Workspace；
- Agent Trace；
- Evidence Panel；
- Bull/Bear Debate；
- Portfolio Dashboard；
- 路由和状态管理；
- API Client；
- 图表和 Markdown 渲染组件。

区别集中在 Transport：

```text
Web (后续):
React UI -> HTTPS/SSE -> Cloud API

Tauri:
React UI -> Local Sidecar Transport -> Python Agent
```

UI 不直接判断当前运行环境，而是依赖统一的 `AgentGateway`、`PortfolioGateway` 和 `NotificationGateway`。

### 3.3 iOS 与 Android 共享

iOS 和 Android 不共享 UI 实现，但共享以下边界：

- 同一份 API Schema；
- 同一套事件和任务状态；
- 同一套认证语义；
- 同一套错误处理语义；
- 同一套云端 Agent 和 Rules；
- 同一套产品文案和验收用例；
- 从 Schema 生成的 Swift/Kotlin 数据模型和 API Client。

平台 UI：

```text
iOS:
SwiftUI + Swift Concurrency + Native Navigation

Android:
Jetpack Compose + Kotlin Coroutines + Native Navigation
```

## 4. 传输层抽象

所有客户端使用等价的能力接口：

```text
AgentGateway
  - createResearchTask()
  - getTask()
  - subscribeTrace()
  - getEvidence()
  - approveDecision()

PortfolioGateway
  - getSnapshot()
  - getRiskReview()
  - getExposure()

NotificationGateway
  - registerDevice()
  - markRead()
  - listNotifications()
```

实现方式：

| 平台 | Transport |
|---|---|
| Tauri MVP | Tauri IPC 或本地 Sidecar HTTP/SSE |
| Web 后续 | HTTPS + SSE |
| iOS 后续 | URLSession + SSE/WebSocket |
| Android 后续 | Ktor/OkHttp + SSE/WebSocket |

Agent 执行位置由 `AgentGateway` 和任务策略决定：

```text
local  -> Tauri + Python Sidecar
cloud -> Cloud API + Agent Worker（后续）
auto   -> Cloud 扩展后根据任务策略和可用性选择
```

## 5. Native App 的职责

### iOS

- SwiftUI 页面和导航；
- Push Notifications；
- BackgroundTasks；
- Keychain；
- 生物识别；
- Widget 和 Share Extension（后续）。

### Android

- Jetpack Compose 页面和导航；
- FCM；
- WorkManager；
- Android Keystore；
- 生物识别；
- App Widget（后续）。

移动端只负责客户端体验和系统能力，不复制 Agent、Rules 或数据管道。

## 6. 单一契约来源

推荐流程：

```text
FastAPI OpenAPI / JSON Schema
              |
              +-- TypeScript Types + Client
              +-- Swift Models + Client
              +-- Kotlin Models + Client
              +-- Python Pydantic Models
```

每次 API 变更必须：

1. 先修改 Schema；
2. 生成各语言客户端；
3. 运行 contract tests；
4. 再修改平台 UI。

## 7. 为什么不使用 Kotlin Multiplatform

当前阶段不引入 Kotlin Multiplatform，原因是：

- Agent 和 Rules 已经在云端；
- 移动端本地业务计算量有限；
- 主要共享内容是协议和数据模型；
- KMP 会增加构建、调试和团队技能要求；
- SwiftUI 和 Compose 各自原生实现更符合当前目标。

当移动端离线能力显著增加，或 Swift/Kotlin 的客户端领域逻辑重复成为主要成本时，再复审 KMP。

## 8. 关键约束

- 不在 iOS/Android 中嵌入 Python Agent；
- 不在客户端复制 Rules Engine；
- 不让平台 UI 直接依赖数据库；
- 不让 Web/Tauri/iOS/Android 各自定义一套 Decision 状态；
- 不让 API Client 的字段脱离 Schema 独立演进；
- Tauri、iOS、Android 的原生能力必须通过适配层接入。
- Design Tokens 和跨平台语义以 [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) 为单一设计来源。
