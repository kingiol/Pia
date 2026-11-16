# Requirements Traceability Matrix

这张表把产品需求、实现模块、里程碑和验收项连接起来，避免“写了需求但没有交付路径”。

| Requirement | Implementation | Milestone | Acceptance |
|---|---|---|---|
| FR-001 Profile | `investor_profiles` + Profile UI | M0/M3 | AC-001, AC-005 |
| FR-002 Versioned Rules | `rulesets` + `rule_snapshots` + versioned Rules API/Desktop editor | M0/M3 | AC-004, Replay |
| FR-003 Portfolio | `portfolio_snapshots` + Portfolio Tools | M3 | AC-004, AC-010 |
| FR-010 Market Observation | Data Worker + Market Tools | M2/M4 | AC-002, AC-003 |
| FR-011 Candidate Scan | Market/Sector/Stock Agents | M4 | AC-001, AC-003 |
| FR-012 Event Deduplication | Event Engine + `dedupe_key` | M6 | AC-002, AC-010 |
| FR-020 Research Task | Task API + State Machine | M4/M5 | AC-001 |
| FR-021 Structured Agent State | Agent Runtime + Pydantic | M4 | AC-003, Replay |
| FR-022 Evidence Citation | Evidence Store + Evidence Panel | M2/M4/M5 | AC-003, AC-008 |
| FR-023 Bull/Bear Debate | Debate Nodes + Workspace | M4/M5 | AC-009 |
| FR-024 Retry/Takeover | Orchestrator + Task Controls | M4/M6 | AC-007 |
| FR-024a Context Export | Task Context API + generated clients + Workspace action | M4/M7 | AC-003, AC-007 |
| FR-030 Rules Gate | Rules Engine | M3 | AC-004 |
| FR-031 Risk Review | Risk Agent + Risk Panel | M3/M4/M5 | AC-004, AC-010 |
| FR-032 Human Approval | Approval API + Decision Panel | M5 | AC-005, AC-006 |
| FR-033 Audit Record | `approvals` + immutable audit | M3/M5/M7 | AC-005, AC-006 |
| FR-034 Rule Retrospective | `task_retrospectives` + retrospective API/Desktop panel | M7 | Replay, Audit |

## 需求变更规则

- 新增 P0 需求必须补充实现模块、里程碑和验收项。
- 删除或降级 P0 需求必须由 Product Owner 记录原因。
- 任何涉及订单、实时数据、用户隐私或规则优先级的变更必须更新 ADR 和风险登记。
- 需求状态以 PRD 为准；执行状态以 MILESTONES 和 EXECUTION_PLAN 为准；是否可发布以 ACCEPTANCE 为准。
