# Pia · A 股个人投资研究助理

> 本地优先、事件驱动、Rules-First。围绕市场与个人持仓发起研究，让每个建议都能追溯证据、检查规则、由你最终判断。

[能力概览](#能力概览) · [快速开始](#快速开始) · [开发与验证](#开发与验证) · [文档中心](docs/INDEX.md) · [P0/P1 路线图](docs/CAPABILITY_ROADMAP.md)

Pia 面向收盘复盘、个股研究和持仓风险检查。它把 Profile、个人规则、行情快照、研究过程和决策日志连接起来，保留人工审批与回放记录。当前以 A 股日线和收盘后研究为主，默认只读，不自动向券商提交订单。

```text
Market / Portfolio / Events
             |
             v
Data Quality -> Research -> Rules / Risk -> Decision -> Human Review
                    |             |            |
                    +-------- Evidence / Trace / Audit --------+
```

## 能力概览

| 能力 | 当前实现 |
|---|---|
| 个人研究工作台 | Profile、候选扫描、个股研究、任务进度、Evidence、Trace 和风险说明 |
| Rules-First | 数据质量检查、规则快照、风险门禁、人工审批和审计 |
| 可追溯研究 | Raw / Normalized / Analytical 数据分层、证据时间、快照、任务回放 |
| 冻结与确定性合成 | 不可变 Context Pack、内容 hash、离线回放、观点证据校验与冲突降级 |
| 可靠执行 | 能力级 Provider 溯源、last-good、阶段预算、阻塞 SDK 子进程隔离 |
| 扫描与可解释性 | 版本化 legacy 策略、因素贡献、排除原因、冻结扫描与离线复算 |
| 结果与执行流程 | Flow 分页、完整性与缺口协议、所属用户脱敏导出 |
| 数据接入 | Fixture、AKShare、Tushare Adapter；能力声明、重试、熔断和 fallback |
| 可选 LLM 研究 | DeepSeek 结构化输出、Tool Calling、流式事件和 usage 记录 |
| 长期个人上下文 | Decision Journal、复盘、待确认记忆和已确认记忆 |
| 本地运行与恢复 | Python Sidecar、SQLite / DuckDB、备份恢复、任务恢复和定时任务 |
| 多端与 Cloud | Desktop / Web 工作台、原生移动客户端、Cloud API / worker / scheduler 与同步代码 |

当前研究图按固定顺序执行，模板观点明确标为 stub / fixture；LLM 是可选补充研究。新结果默认只生成 WATCH、NO_ACTION 或 BLOCKED，不采用调用方传入的买卖建议。P0 / P1 的配置、接口及验证边界见 [能力交付说明](docs/CAPABILITY_DELIVERY.md) 和 [执行状态](docs/CAPABILITY_IMPLEMENTATION_STATUS.md)。

### 技术与运行边界

| 层 | 技术 |
|---|---|
| Desktop / Web | Tauri 2、React、TypeScript、Vite |
| Runtime / API | Python 3.11+、LangGraph、Pydantic、标准库 HTTP Server |
| 存储 | 本地 SQLite + DuckDB；Cloud 统一使用 PostgreSQL |
| 移动端 | iOS SwiftUI；Android Kotlin + Jetpack Compose |
| 外部服务 | AKShare；可选 Tushare Token、DeepSeek API Key |

首个可验证产品以 Local-first Desktop 为中心。移动端和 Cloud 的存在不代表它们已完成所有平台发布验收，范围见 [ADR](docs/ADR.md) 与 [实现说明](docs/IMPLEMENTATION.md)。

## 快速开始

### 1. 安装依赖

准备 Python 3.11+、Node.js 22+，以及 `package.json` 指定的 `pnpm@12.18.0`。以下命令在仓库根目录执行；首次安装需要网络。

```bash
python3 -m venv .venv
./scripts/python.sh -m pip install -e .
pnpm install --frozen-lockfile
```

### 2. 运行离线演示

```bash
./scripts/replay.sh
PIA_DATA_PROVIDER=fixture ./scripts/dev.sh
```

工作台默认地址为 `http://127.0.0.1:5173`，API 默认地址为 `http://127.0.0.1:8765/api`。API 端口被占用时，脚本会选择空闲端口并输出实际地址。Fixture 使用合成数据，无需外部服务凭据，适合先验证研究闭环。

### 3. 接入真实行情与 LLM（可选）

Desktop 的 Local 模式可在「设置」中保存或清除 DeepSeek API Key，后续请求立即生效。也可通过交互式命令保存本机凭据；未保存时读取环境变量 `DEEPSEEK_API_KEY`。不要把密钥提交到仓库。

```bash
./scripts/python.sh -m pia_runtime.cli credentials set DEEPSEEK_API_KEY
PIA_DATA_PROVIDER=akshare PIA_REQUIRE_LLM=1 ./scripts/dev.sh
```

真实行情依赖上游网络与可用性；LLM 调用可能产生服务费用。只需真实行情时，省略 `PIA_REQUIRE_LLM=1`。Tushare 和更多配置入口见 [Adapter 规范](docs/ADAPTERS.md)；实际运行默认值以 [Settings](packages-py/pia_runtime/pia_runtime/config.py) 为准。

### 其他启动方式

日常调试 Desktop 可直接运行：

```bash
pnpm run debug:desktop:local          # Local with AKShare
pnpm run debug:desktop:local:fixture  # Local with fixture data
pnpm run debug:desktop                # Local / Cloud
```

这些命令都会启动 Python 源码 API、Vite 和 Tauri debug 窗口，无需构建
Sidecar。`debug:desktop:local` 使用 AKShare 真实行情，`:fixture` 命令使用测试数据；
`debug:desktop` 保留现有默认行情源（未配置时使用 fixture）。
默认使用独立调试数据库 `.pia/debug/pia.sqlite3`；
退出时停止本次启动的 API。Local 专用模式忽略已保存的 Cloud 选择，
并隐藏 Cloud 入口；另一模式保留原有切换和 Cloud API 地址配置，
不会自动部署 Cloud 服务。5173 端口须空闲；API 端口被占用时自动选取空闲端口。
Python 源码变更后需重启命令，前端和 Rust 代码沿用开发模式热更新。

需要真实行情和 LLM 时，先保存 DeepSeek 凭据，再运行：

```bash
PIA_REQUIRE_LLM=1 pnpm run debug:desktop:local
```

原生 Tauri Desktop 还需要 Rust 与对应平台的 Tauri 构建依赖。首次构建 Sidecar 需要 PyInstaller：

```bash
./scripts/python.sh -m pip install pyinstaller
cargo install tauri-cli --version '^2'
PIA_DATA_PROVIDER=fixture ./scripts/desktop.sh
```

`desktop.sh` 未显式指定 Provider 时默认使用 AKShare。平台操作见 [试点用户指南](docs/PILOT_USER_GUIDE.md)。

Desktop 首次启动默认进入 Local 工作台，左下角导航底部可切换 Local / Cloud。选择 Cloud 时弹出 API 地址和访问令牌配置；运行模式与地址会被记住，令牌仅保留在当前会话。使用已保存的 Cloud 模式启动时不会启动本地 Sidecar。连接、凭据与进程生命周期说明见 [Desktop Runtime Selection](docs/DESKTOP_RUNTIME.md)。

Web Workspace 需要先有运行中的 API；独立启动时默认使用端口 `5174`：

```bash
VITE_API_BASE=http://127.0.0.1:8765/api pnpm run dev:web
```

Cloud 的认证、worker、scheduler、PostgreSQL 与备份步骤见 [运维指南](docs/OPERATIONS.md)；移动端分别见 [iOS](apps/ios/README.md) 和 [Android](apps/android/README.md)。

Cloud 必须配置 `PIA_POSTGRES_DSN`，业务记录与分析数据都保存在 PostgreSQL；
不会回退到 SQLite，也不再读写 DuckDB。Cloud 尚未正式上线，按全新 PostgreSQL
数据库部署，不提供旧 DuckDB 数据迁移。部署与备份见 [Cloud Storage](docs/CLOUD_STORAGE.md)；
Local 模式仍使用 SQLite + DuckDB。

## 开发与验证

```bash
./scripts/test.sh
./scripts/replay.sh
./scripts/e2e.sh
./scripts/python.sh scripts/generate_ts_client.py --check
pnpm run build:web
```

`test.sh` 包含 Python unittest、编译与契约生成检查，并在安装前端依赖后执行 Desktop 构建。外部服务、平台打包、故障恢复和发布检查的适用条件见 [验收标准](docs/ACCEPTANCE.md) 与 [运维指南](docs/OPERATIONS.md)。

### 实现状态与发布证据

Local-first 的研究、规则、审批、审计和恢复闭环已有实现及本地验证记录。[2026-11-08 审计](docs/MVP_AUDIT.md) 记录了真实 DeepSeek structured / tool / streaming 与 runtime task 的验收结果。

完整发布仍需核验 Windows Sidecar / MSI / 启动、Tushare 真实主备与 provenance、跨平台通知及长期真实外部服务指标。历史 fixture 成功率或 P95 不能替代这些证据；审计记录也不代表当前工作树已重新通过全部检查。

## 文档中心

完整分类导航见 **[docs/INDEX.md](docs/INDEX.md)**。

| 你想做什么 | 从这里开始 |
|---|---|
| 了解产品与边界 | [PRD](docs/PRD.md) · [架构](docs/ARCHITECTURE.md) |
| 开始使用与排障 | [试点用户指南](docs/PILOT_USER_GUIDE.md) · [运维](docs/OPERATIONS.md) |
| 开发 P0 / P1 增强能力 | [总路线图](docs/CAPABILITY_ROADMAP.md) · [P0](docs/P0_IMPLEMENTATION_PLAN.md) · [P1](docs/P1_IMPLEMENTATION_PLAN.md) |
| 修改接口或数据接入 | [OpenAPI](contracts/openapi.yaml) · [数据与规则](docs/DATA_RULES_EVENTS.md) · [Adapters](docs/ADAPTERS.md) |
| 修改工作台与客户端 | [研究工作台](docs/RESEARCH_WORKSPACE.md) · [设计系统](docs/DESIGN_SYSTEM.md) · [Monorepo](docs/MONOREPO.md) |
| 检查验收与发布缺口 | [验收标准](docs/ACCEPTANCE.md) · [需求矩阵](docs/REQUIREMENT_MATRIX.md) · [审计记录](docs/MVP_AUDIT.md) |
