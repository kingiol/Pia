# Pia UI/UX Design System

## 1. Purpose

本文档定义 Pia 在 macOS Desktop、Windows Desktop、Web、iOS 和 Android 上的 UI/UX 设计规范。

Pia 是一个 Local-first、Evidence-first 的 A 股投资研究工作台。界面需要帮助用户快速回答：

1. 当前发生了什么？
2. 这个结论依据什么？
3. 哪些 Rules 通过或阻断了建议？
4. 用户现在需要做什么？

跨平台共享设计语义和视觉 Tokens；导航、手势、系统能力和平台控件由各平台原生实现。

## 2. Design Direction

```text
Calm        安静，不制造交易焦虑
Dense       信息密度高，但保持可扫描
Explainable 每个结论都能追溯到 Evidence 和 Rules
Native      尊重各平台交互习惯
Actionable  清楚表达下一步动作和审批状态
```

Pia 的界面应像专业研究工具，不像营销网站、社交产品或高频交易终端。

设计原则：

1. **Evidence before conclusion**：结论旁边必须有证据入口。
2. **Status before decoration**：颜色、图标和文字优先表达状态。
3. **Rules are visible**：阻断原因、规则版本和数据时间必须可见。
4. **Progressive disclosure**：默认显示摘要，逐层展开 Trace 和计算细节。
5. **Human approval is explicit**：审批、拒绝、稍后处理和无动作必须区分。
6. **One primary action**：一个区域只保留一个主要动作。
7. **Platform-native interaction**：共享语义，不强行共享导航和手势。
8. **No false certainty**：不使用暗示确定收益的文案、颜色或图表。

## 3. Information Architecture

### Desktop and Web

```text
Overview
├── Today
├── Market
├── Portfolio
└── Alerts

Research
├── Research Queue
├── Research Workspace
├── Watchlist
└── Replay

Controls
├── Rules
├── Data Health
├── Providers
└── Audit

System
├── Settings
└── About
```

### iOS and Android

```text
Today
Research
Portfolio
Alerts
Settings
```

移动端只保留高频任务。复杂 Rules 编辑、Provider 诊断和完整 Audit 优先放在 Desktop/Web。

## 4. Desktop Layout

```text
+------------------------------------------------------------------+
| Topbar: Search | Date | Data Health | Agent Status | Account     |
+------------+------------------------+----------------------------+
| Sidebar    | Research Queue         | Research Detail            |
|            |                        |                            |
| Overview   | [RUNNING] Market       | Decision                   |
| Market     | [WAITING] 600519       | Evidence                   |
| Portfolio  | [BLOCKED] Risk        | Bull / Bear                |
| Research   | [DONE] Daily Review    | Risk Review                |
| Rules      |                        | Agent Trace                |
+------------+------------------------+----------------------------+
```

| 区域 | 推荐值 |
|---|---:|
| App window 最小宽度 | 1120px |
| Sidebar | 220px 至 256px |
| Queue panel | 280px 至 360px |
| Main content | `minmax(520px, 1fr)` |
| Inspector | 320px 至 400px |
| Topbar | 48px |
| Toolbar | 40px |
| Section gap | 24px |
| Panel gap | 16px |
| Compact row | 36px |
| Standard row | 44px |

窗口变窄时，Inspector 变成侧滑面板；Queue 保留，主内容不能压缩到不可读。

交互要求：

- macOS 支持 `Command+K`、`Command+P`、`Command+Enter`。
- Windows 支持 `Ctrl+K`、`Ctrl+P`、`Ctrl+Enter`。
- 长任务必须提供取消、重试和详情入口。
- 关闭窗口不等同于删除任务。
- 托盘菜单提供打开工作台、查看运行状态、暂停新任务和退出 Sidecar。

## 5. Web Layout

Web 和 Tauri 共享 React UI 与 feature modules，但 Web 必须支持 URL 定位：

```text
/overview
/research
/research/:taskId
/portfolio
/rules
/data-health
/audit
```

刷新页面后必须保留当前任务和筛选条件。Web 使用 `history` routing；Tauri 优先使用 hash routing 或等价的静态资源安全方案。

## 6. Mobile Layout

### iOS

- SwiftUI `TabView` 作为一级导航。
- `NavigationStack` 作为层级导航。
- `Sheet` 用于 Evidence、Risk Review 和审批确认。
- iPad 使用 `NavigationSplitView`。
- 支持 Dynamic Type。

### Android

- Compact width 使用 Bottom Navigation。
- Expanded width 使用 Navigation Rail。
- 使用 Material 3 主题和系统返回行为。
- 使用 `WindowSizeClass` 或等价策略决定布局。

### Research Detail

```text
Research Task
├── Decision Summary
├── Why this result
├── Evidence
├── Rules
├── Bull / Bear
├── Agent Trace
└── Approval
```

移动端默认只展开 `Decision Summary`、`Why this result` 和 `Approval`。

## 7. Design Tokens

### Semantic Color

业务组件只能使用语义 Token，不能直接写十六进制颜色。

```text
color.bg.canvas
color.bg.surface
color.bg.elevated
color.border.subtle
color.border.strong
color.text.primary
color.text.secondary
color.text.muted
color.action.primary
color.action.primaryHover
color.status.info
color.status.success
color.status.warning
color.status.danger
color.market.up
color.market.down
color.market.flat
```

`market.up` 和 `market.down` 不能单独作为结论，必须同时显示数值、方向文字或图标。

### Typography

```text
font.family.ui       platform system font
font.family.mono     platform monospace font
font.size.xs         11px
font.size.sm         12px
font.size.md         14px
font.size.lg         16px
font.size.xl         20px
font.size.2xl        24px
font.weight.regular  400
font.weight.medium   500
font.weight.semibold 600
```

- 正文默认 14px，辅助信息 12px。
- 数值、百分比、代码和时间可以使用等宽字体。
- 不使用负字距。
- 重要数值必须配合标签和时间点。

### Spacing and Shape

```text
space.1  = 4px
space.2  = 8px
space.3  = 12px
space.4  = 16px
space.5  = 20px
space.6  = 24px
space.8  = 32px
space.10 = 40px
```

- 默认圆角 4px，Dialog 和单个重复 Item 最多 8px。
- 普通 Section 使用背景层级、边框和分隔线，不做浮动大卡片。
- 阴影只用于 Popover、Menu 和 Dialog。

## 8. Core Components

### Status Badge

```text
[RUNNING] [WAITING_APPROVAL] [BLOCKED] [NO_ACTION] [DONE]
```

Badge 必须包含文字；颜色和图标只作辅助。

### Decision Panel

```text
Decision: WATCH
Confidence: Medium
As of: 2026-11-06 16:00
Rule result: Passed with warnings
Next action: Add to watchlist

[View evidence] [View rules] [Add to watchlist]
```

禁止只显示 `BUY`、`SELL` 或一个大颜色箭头。

### Evidence Panel

每条 Evidence 显示 `source`、`title`、`observed_at`、`as_of`、`expires_at`、`quality`、`excerpt` 和 `snapshot_id`。过期证据必须显示 `STALE`。

### Rules Panel

```text
Rules v1
├── Data freshness        PASS
├── Universe eligibility  PASS
├── Market gate           WARN
├── Position limit        BLOCKED
└── Final result          NO_ACTION
```

每条规则显示输入值、阈值、结果和规则版本。

### Agent Trace

```text
Investment Chief       DONE      1.2s
Market Analyst         DONE      2.8s
Technical Analyst      RUNNING   4.1s
Risk Review            WAITING   -
```

Trace 默认不展示完整 Prompt；Audit 或开发诊断权限下才显示脱敏输入和输出。

### Approval Panel

允许的动作：

- `Approve recommendation`
- `Reject`
- `Snooze`
- `Create follow-up research`
- `No action`

审批前必须显示 Decision、风险等级、Rules version、Data snapshot 和失效时间。

## 9. Charts and Data Visualization

- 每张图必须有标题、单位、时间范围和数据来源。
- Hover、touch 或 keyboard focus 显示精确值。
- 图表不能只用红绿颜色表达差异。
- 空数据、部分数据、过期数据和加载失败必须有独立状态。
- 图表数据必须与 `data_snapshot_id` 关联。

MVP 图表：

- Market breadth；
- Index trend；
- Portfolio exposure；
- Drawdown；
- Agent timeline。

Desktop 支持 crosshair、zoom、range selection 和 keyboard focus；Mobile 优先支持 tap、long press 和 range preset。

## 10. Content and States

推荐文案：

```text
该建议被仓位规则阻断：当前行业暴露 34%，上限为 30%。
数据截至 2026-11-06 16:00，来源为 akshare。
```

避免：

```text
强烈看多
马上买入
AI 认为一定会上涨
```

所有行动建议必须使用结构化状态：

```text
BUY_CANDIDATE
SELL_CANDIDATE
HOLD
WATCH
NO_ACTION
BLOCKED
WAITING_APPROVAL
```

Loading 使用结构化 Skeleton；长任务显示阶段、已完成 Agent、下一步和取消按钮。Error 必须包含 `error_code`、影响范围和重试动作。Offline 状态必须明确显示，不把旧数据伪装成最新数据。

## 11. Motion and Accessibility

- 默认动效 150ms 至 220ms。
- Trace 状态变化使用淡入和高度过渡。
- 支持 `prefers-reduced-motion`、iOS Reduce Motion 和 Android 动画缩减设置。
- 所有操作支持键盘或系统辅助技术。
- 状态不能只通过颜色表达。
- Icon Button 必须有 accessible name 和 tooltip。
- 图表和 Evidence 必须提供文本替代信息。
- 支持系统字体放大，内容不能裁剪。
- Dialog 打开后焦点进入 Dialog，关闭后返回触发控件。

## 12. Security and Privacy

- UI 不显示 API key、Token 或完整凭据。
- Logs、Trace 和错误状态必须脱敏。
- 持仓信息在分享、导出和截图模式下提供脱敏选项。
- Audit 区分用户操作、Agent 操作、Tool 调用和系统事件。

## 13. Platform Reuse Boundary

### Shared

- Design Tokens；
- semantic colors；
- typography and spacing；
- Decision 状态；
- Risk 等级；
- Evidence 字段；
- Rules 结果；
- loading/error/empty 语义；
- 文案和验收场景。

### Platform-specific

| 平台 | 独有实现 |
|---|---|
| Tauri Desktop | 托盘、快捷键、本地文件、Sidecar 状态、窗口布局 |
| Web | URL routing、浏览器权限、history navigation、远程连接状态 |
| iOS | TabView、NavigationStack、Sheet、Dynamic Type、Keychain、Push |
| Android | Material 3、Navigation Rail、Back handling、WorkManager、Keystore |

## 14. Component Naming

技术名称使用英文：

```text
ResearchQueue
ResearchWorkspace
DecisionPanel
EvidencePanel
RulesPanel
AgentTrace
ApprovalPanel
DataHealthBanner
ProviderStatus
PortfolioExposureChart
DrawdownChart
```

不要创建同义组件并存，例如 `DecisionCard`、`DecisionBox`、`DecisionSummaryCard`。

## 15. Design Acceptance

### Visual

- macOS 和 Windows 都能完成核心任务。
- Web 在 1280px、1024px 和 768px 宽度下不遮挡。
- Mobile 在 compact 和 expanded width 下导航正确。
- 文字、数值、按钮和图表不溢出。
- 深色和浅色主题下状态可读。
- 颜色不承担唯一语义。
- 不出现层层嵌套卡片。

### Workflow

- 用户能在两分钟内找到结论、证据和 Rules 结果。
- `BLOCKED`、`NO_ACTION` 和 `WAITING_APPROVAL` 不显示错误审批动作。
- 长任务可以暂停、取消、重试和查看 Trace。
- 应用重启后本地任务和 Audit 仍可访问。
- 离线时不会把过期数据标记为最新。

### Native

- macOS 使用原生窗口、菜单、快捷键和通知习惯。
- Windows 支持原生安装、窗口、通知和打包。
- iOS 使用 SwiftUI 原生导航和系统字体。
- Android 使用 Compose Material 3 和系统返回行为。
- 不使用 React Native。

## 16. Design References

- Apple Human Interface Guidelines：macOS、iOS/iPadOS、Sidebar、Split View、Typography 和 Accessibility。
- Microsoft Fluent 2：Windows 和 Web 的布局、控件、主题和响应式规则。
- Material 3：Android Compose 的主题、组件、动态颜色和自适应布局。
- TradingView Desktop：研究工作区、图表联动、多标签和市场数据密度。
- Linear：任务工作区、状态表达、快捷键、命令面板和跨平台工作流。

这些产品只作为交互和信息架构参考。Pia 的视觉语言必须围绕 Evidence、Rules、Risk 和 Audit 自己定义。

## 17. Desktop/Web Polish (2026-11-11)

### Approved Direction

- Product: evidence-led A-share research for individual investors, with explicit human decisions.
- Character: measured, rigorous, traceable.
- World: a research desk and review records; neutral surfaces with Pia's existing green accent.
- Moments: the research decision, evaluated rules, evidence and real snapshot data.
- Signature: a status dot paired with a readable status label.

Scope: the React interface shared by Desktop and Web. Preserve feature behavior,
section order, research contracts and approval gates. Native iOS and Android
interfaces are outside this pass. No new runtime dependencies or generated imagery.

```text
+------------+------------------------------------------------+
| Pia        | Research overview        Search / Tools / Review|
|            | Date / Data provenance / Runtime health         |
| Workspace  |------------------------------------------------|
| Overview   | Investment strategy       | Agent status        |
| Market     |------------------------------------------------|
| Watchlist  | Compact setup steps and completion progress    |
| Portfolio  |------------------------------------------------|
| Research   | Events that need attention                     |
| Journal    |------------------------------------------------|
|            | Active / Awaiting approval / Blocked / Rules    |
| Settings   |------------------------------------------------|
| ...        | Research queue       | Decision / Evidence     |
+------------+------------------------------------------------+
```

### Nine Passes

| Pass | Implementation |
|---|---|
| Spacing | Consolidate the two competing style layers; use a 4px spacing grid, 36px desktop navigation rows and aligned control groups |
| Color | Neutral canvas, white section bands, three text roles and the existing `#146b5f` accent; remove colored shadows and translucent navigation |
| Icons | Reuse Phosphor at 16px; replace character-based refresh, evidence, notification and setup icons; give icon tools names and native tooltips |
| Copy | Shorten the setup heading, name the investment context directly and retain source dates and replay provenance |
| Type | Platform system font, 12px minimum supporting text, 13px compact content, 14px navigation and 24px page titles; no negative tracking; tabular figures |
| Layout | Keep section order; compact the strategy, setup and attention sections; give the research queue 280px on wide screens |
| Details | Flat section bands and separators; 4px controls; visible keyboard focus, semantic navigation state and toggle state; explicit trace disclosure |
| Visuals | Use actual decisions, rule results, snapshot figures and existing charts as the visual focus; neutral completed Agent timing bars, highlighted running or failed runs; no decorative imagery or image prompts |
| Motion | Named 150ms transitions with one easing curve; no hover displacement, colored glow or animated layout dimensions; honor reduced motion |

### Responsive Contract

- Above 1120px: full sidebar and a queue beside the research detail.
- From 901px to 1120px: 200px sidebar; queue groups above the research detail.
- From 701px to 900px: 64px icon navigation with accessible names and tooltips.
- At 700px and below: brand header with an expandable navigation menu, stacked
  sections and a full-width primary action.
- Mobile navigation closes on selection. Escape closes it and restores focus to
  the menu toggle; selecting a destination moves focus to the page heading.
- Long identifiers, evidence metadata, form fields and action groups must wrap
  within their containers. Queue groups can scroll within their own region.
- A blocked decision never exposes approval controls. Waiting approval keeps all
  five existing actions; resolving it removes those controls.

### Validation

Verified in Chromium using an isolated local fixture database:

- All 11 navigation destinations at 1440, 1024, 768, 390 and 320px: 55 layout
  combinations without document, main-region or visible internal horizontal overflow.
- Overview also checked at 1280px. At 1440px, with the initial setup state, the
  research region starts at 702px instead of approximately 1036px.
- Menu open/select/close, Escape focus restoration, search shortcut, task queue
  keyboard selection, raw-data loading and trace disclosure.
- `BLOCKED`, `WAITING_APPROVAL` and the transition to `NO_ACTION`.
- Data synchronization displays the returned quality, completeness and failure
  counts; the missing `DataHealthView.onSyncResult` binding is corrected.
- Reduced-motion preference disables transitions.
- Primary button contrast: 6.37:1; muted text on the sidebar: 4.52:1.
- Desktop and Web production builds pass.

Full `tsc --noEmit` is not a passing gate in the existing repository: React type
declarations and Vite environment declarations are missing, alongside existing
application type errors. A temporary checkout of the original commit reproduces
these baseline failures. This UI pass does not add dependencies to repair that
separate tooling issue. Native desktop packaging has not been revalidated.
Native mobile validation is recorded in section 18.

Method: Unslop by Damir Sokolovsky (@heydamir), CC BY 4.0. The implementation
follows Pia's own design constraints and the direction approved for this project.

## 18. Native Mobile Polish (2026-11-12)

### Approved Scope

Extend the evidence-led, measured and traceable direction to the existing native
clients. Use neutral surfaces, Pia green for selection and primary actions, and
a status dot with readable text. Preserve the three existing destinations,
transport contracts, task controls and the five human approval actions.

Android research detail becomes a scrollable screen with system Back support.
iOS retains native navigation and semantic text sizes. Both clients show
operation progress, prevent duplicate submissions and present errors in the
current context. The Today section distinguishes onboarding from repeat use.
Evidence and trace are progressively disclosed without discarding entries.

```text
+--------------------------------+
| < Research detail      Refresh |
| Operation / Error              |
|--------------------------------|
| Task status / Date             |
| Decision / Risk / Next action  |
| Rules                    >     |
| Evidence                 >     |
| Agent trace              >     |
|--------------------------------|
| Review actions / Task controls |
+--------------------------------+
```

### Acceptance Plan

- Build both native clients and run the existing Swift transport tests.
- Check empty, loading, failed and populated screens.
- Check full evidence lists and source/date/quality metadata.
- Check small screens, large text and light/dark appearances where tooling allows.
- Check refresh, Back, duplicate submission prevention and action errors.
- Check that blocked tasks have no approval controls and resolved tasks lose them.

No new dependencies, generated imagery, portfolio features or navigation
destinations are introduced. Tablet-specific navigation redesign remains a
separate task. Method: Unslop by Damir Sokolovsky (@heydamir), CC BY 4.0.

### Implementation

| Pass | Native implementation |
|---|---|
| Spacing | Consistent section rhythm, aligned metadata, scrollable detail and explicit icon dimensions |
| Color | Neutral light/dark surfaces; green selection and primary actions; readable status and error colors |
| Icons | Retain Phosphor; 20pt iOS / 20dp Android icons with native control targets |
| Copy | Contextual first-use and repeat-use Today text; readable task statuses and operation progress |
| Type | Semantic iOS text and Material typography; Android letter spacing is zero; metadata wraps |
| Layout | Preserve Today, Research and Notifications; Android detail has its own screen and system Back |
| Details | All five approval actions remain gated by verified waiting status; duplicate submissions are disabled |
| Visuals | Complete evidence provenance and all analysis steps remain available through disclosure |
| Motion | Retain native navigation and disclosure behavior; no decorative or continuous animation |

### Platform Constraints

- SwiftUI tab bars extract the underlying image and ignore view frame modifiers.
  Render the existing Phosphor assets at an intrinsic 20pt size before assigning
  them to native tab items. A frame alone produces overflowing icons.
- Light green primary buttons in dark appearance require an explicit dark
  foreground. The system's default white label does not provide enough contrast.
- Android permits the existing local HTTP preview endpoint in the Debug manifest
  only. Release network policy is unchanged.
- The approval endpoint returns an acknowledgement containing a task, rather than
  a complete detail payload. The Swift client decodes that acknowledgement and
  then fetches current detail. A regression test covers this sequence.
- Swift 6 native compilation requires the legacy BackgroundTasks callback to hand
  completion to the main actor. The framework import uses preconcurrency
  interoperability; no background scheduling behavior was redesigned.

### Validation Results

Verified against the isolated fixture API and database, without live investment
data or changes to backend contracts:

- Android Debug compilation and two JUnit approval-gate tests pass.
- Swift package compilation and eight transport tests pass, including approval
  acknowledgement followed by detail refresh.
- Native iOS simulator compilation passes. Four XCUITest scenarios pass across
  targeted runs: Today/Notifications navigation, blocked detail, resolved evidence
  disclosure, and waiting approval resolved to `NO_ACTION`.
- iOS Today/Notifications and evidence disclosure also pass in dark appearance
  with `accessibility-medium` text. Screenshots confirm correctly sized tab icons,
  dark primary-button labels, wrapping provenance and scrollable evidence.
- Android emulator checks cover light/dark appearance, a 320dp viewport with
  1.5x font scale, toolbar/system Back, three evidence entries and all ten trace
  entries. No content truncation or app-level horizontal overflow was observed
  in the checked screens.
- Both clients show all five waiting approval actions. Resolving `NO_ACTION`
  removes approval controls and updates task status. Blocked detail exposes no
  approval controls.
- `git diff --check` passes.

iOS UI automation used a temporary Xcode simulator host for the repository's
SwiftPM app shell. The UI harness is not a committed test target; the transport
regression and Android gate tests are retained in the repository. Physical
devices, tablet navigation, push delivery and OS-scheduled background execution
remain outside this validation. Only the `NO_ACTION` mutation was exercised
end-to-end; the other four approval actions were checked for availability.
