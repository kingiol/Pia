# Documentation Index

Pia 文档导航。文档分为产品规格、当前实现说明、拟实施计划与历史验证记录；它们不能互相替代。

## 推荐阅读路径

| 目的 | 阅读顺序 |
|---|---|
| 首次了解项目 | [README](../README.md) → [PRD](PRD.md) → [架构](ARCHITECTURE.md) |
| 本地试用 | [README 快速开始](../README.md#快速开始) → [试点用户指南](PILOT_USER_GUIDE.md) → [运维](OPERATIONS.md) |
| 执行 P0 / P1 | [能力路线图](CAPABILITY_ROADMAP.md) → [P0 执行计划](P0_IMPLEMENTATION_PLAN.md) → [P1 执行计划](P1_IMPLEMENTATION_PLAN.md) |
| 开发与评审 | [实现说明](IMPLEMENTATION.md) → [Monorepo](MONOREPO.md) → [架构决策](ADR.md) → [验收](ACCEPTANCE.md) |
| 准备试点与发布 | [需求矩阵](REQUIREMENT_MATRIX.md) → [审计记录](MVP_AUDIT.md) → [试点验证](PILOT_VALIDATION_PLAN.md) |

## 产品与交互规格

| 文档 | 内容与使用场景 |
|---|---|
| [PRD](PRD.md) | 产品目标、用户、范围、需求与成功指标 |
| [Competitive Analysis](COMPETITIVE_ANALYSIS.md) | A 股投研与复盘产品比较、当前能力证据与试点假设 |
| [Research Workspace](RESEARCH_WORKSPACE.md) | 研究工作台、任务、证据、规则和审批交互 |
| [Design System](DESIGN_SYSTEM.md) | Desktop、Web、iOS、Android 的视觉与交互约定 |
| [Decision Journal Design](DECISION_JOURNAL_DESIGN.md) | 决策日志、复盘与个人记忆的领域设计 |

## 架构、契约与实现

| 文档 | 内容与使用场景 |
|---|---|
| [Architecture](ARCHITECTURE.md) | 系统分层、Agent、Local / Cloud 与技术边界 |
| [ADR](ADR.md) | 已记录的架构决策、理由与复审条件 |
| [Data, Rules & Events](DATA_RULES_EVENTS.md) | 数据、规则门禁、事件、工具与记忆模型 |
| [Adapters](ADAPTERS.md) | Provider、LLM、Broker、通知和平台接入约定 |
| [Monorepo](MONOREPO.md) | 代码目录与跨客户端复用边界 |
| [Implementation](IMPLEMENTATION.md) | 已落地代码映射、运行模式及扩展边界 |
| [Desktop Runtime Selection](DESKTOP_RUNTIME.md) | Desktop Local / Cloud 选择的规格、实现边界与验证方式 |
| [Cloud Storage](CLOUD_STORAGE.md) | Cloud PostgreSQL 统一存储、全新部署、备份恢复与验证边界 |
| [OpenAPI](../contracts/openapi.yaml) | API 契约；修改接口时同步 Schema 与生成客户端 |
| [JSON Schemas](../contracts/schemas/) | Task、Decision、Evidence 等公共数据结构 |
| [Settings](../packages-py/pia_runtime/pia_runtime/config.py) | 当前实际配置项、环境变量与默认值 |
| [Provider 配置示例](../config/providers.example.yaml) | 接入结构示例；不代表 Runtime 已实现该文件的配置加载 |

## 增强路线图与执行计划

计划基于 2026-11-11 源码核对，适配开发于 2026-11-12 执行；实现状态和实际验证证据分别记录，平台与真实服务验证不由离线测试替代。

| 文档 | 内容与使用场景 |
|---|---|
| [Capability Roadmap](CAPABILITY_ROADMAP.md) | P0 / P1 基线、依赖、顺序、工期假设、统一完成门槛 |
| [P0 Implementation Plan](P0_IMPLEMENTATION_PLAN.md) | 上下文冻结、Provider 溯源、决策合成、阶段预算、执行流程图 |
| [P1 Implementation Plan](P1_IMPLEMENTATION_PLAN.md) | 版本化选股策略、多模型路由与预算、分层 CI、公开降级契约 |
| [Capability Delivery](CAPABILITY_DELIVERY.md) | 本批次使用方式、配置、接口、保守默认行为与兼容性 |
| [Capability Implementation Status](CAPABILITY_IMPLEMENTATION_STATUS.md) | 九个任务包的实际实现、验证记录与剩余环境验证 |
| [Milestones](MILESTONES.md) | 原始项目阶段与里程碑；增强批次以新路线图为准 |
| [Execution Plan](EXECUTION_PLAN.md) | 初始 MVP 的 12 周安排、角色与垂直切片模板 |

## 验收、风险与运维

| 文档 | 内容与使用场景 |
|---|---|
| [Acceptance](ACCEPTANCE.md) | 原有 MVP 验收标准；新增计划不替换 `AC-000..AC-010` |
| [Requirement Matrix](REQUIREMENT_MATRIX.md) | 需求、代码、证据和未关闭项的对应关系 |
| [Traceability](TRACEABILITY.md) | 需求到实现、里程碑与验收的追踪关系 |
| [Risk Register](RISK_REGISTER.md) | 风险、触发器、责任与缓解措施 |
| [Operations](OPERATIONS.md) | 部署、监控、数据质量、备份恢复与故障处置 |
| [MVP Audit](MVP_AUDIT.md) | 按日期保留的历史审计与验证证据；同一文件包含多轮结果 |

审计中早期“缺少凭据”等结论可能被后续验收更新。判断当前状态应核对对应日期、运行环境、commit / 工作树与实际产物，再执行适用的发布预检；不能只引用文件中的某个旧段落。

## 试点与用户反馈

| 文档 | 内容与使用场景 |
|---|---|
| [Pilot User Guide](PILOT_USER_GUIDE.md) | 启动、研究、审批、回放和故障恢复操作 |
| [Pilot Validation Plan](PILOT_VALIDATION_PLAN.md) | 试点对象、统一任务、指标和继续 / 调整门槛 |
| [Daily Holdings Review](DAILY_HOLDINGS_REVIEW.md) | 收盘持仓复核范围、估值口径、交互和真实行情验收 |
| [Pilot Retrospective Template](PILOT_RETROSPECTIVE_TEMPLATE.md) | 记录试点观察、问题、证据与后续决策 |

## 初始规划与历史输入

| 文档 | 阅读边界 |
|---|---|
| [MVP Readiness](MVP_READINESS.md) | 初始文档包是否足够启动实现的审查，不是当前发布状态 |
| [Implementation Inputs](IMPLEMENTATION_INPUTS.md) | 初始实现所需输入、默认值与阻碍；实际默认值以 Settings 为准 |

## 平台入口

| 平台 | 文档 |
|---|---|
| Desktop / Web | [根 README](../README.md) · [实现说明](IMPLEMENTATION.md) |
| iOS | [客户端 README](../apps/ios/README.md) |
| Android | [客户端 README](../apps/android/README.md) |

## 维护约定

新增文档时，在此索引的对应分类增加入口，并说明它属于规格、实现、计划还是验证记录。能力交付后同步更新执行计划状态、实现映射与验收证据；只有重新执行的验证才能记为本次结果。涉及 API 时同时更新 OpenAPI、Schema 与生成客户端。
