# Capability Implementation Status

执行日期：2026-11-12。起始 commit：`a311380`。验收基于实际代码与产物，计划文档的状态不能替代验证结果。

| Package | Status | Evidence |
|---|---|---|
| P0-01 | Implemented; local verified | `test_decision_context.py`、Runtime、SQLite / PostgreSQL 备份恢复、Cloud 离线回放 |
| P0-02 | Implemented; local verified; live gate pending | `test_provider_provenance.py`、Adapter / DataWorker；capability 熔断、真实尝试链、last-good、用户隔离 |
| P0-03 | Implemented; local verified | `test_decision_synthesizer.py`、Rules / Runtime；有效证据计数、冲突隔离、禁止 suggested_action 授权 |
| P0-04 | Implemented; local verified; Windows gate pending | `test_stage_policy.py`、`test_isolated_call.py`、recovery / chaos、macOS frozen Sidecar spawn / timeout cleanup |
| P0-05 | Implemented; local verified | `test_run_flow.py`、分页 upsert / 取消终态；浏览器键盘选择和 390px 布局 |
| P1-01 | Implemented; local verified | `test_screening.py`；legacy 公式 / 稳定排序 / 因素解释 / 冻结复算；浏览器扫描和复算 |
| P1-02 | Implemented; local verified; real endpoint gate pending | `test_model_fallback.py`、`test_llm_budget.py`、PostgreSQL 多连接预算竞争；白名单、UTC 跨日、未知费用占用 |
| P1-03 | Implemented; local verified; remote CI gate pending | classifier 路径与聚合门测试、actionlint、frozen pnpm 安装和构建 |
| P1-04 | Implemented; local verified | `test_result_metadata.py`；API / 历史 / SSE / 导出一致、跨用户拒绝、审批受限、恢复后元数据一致 |

## Verification

以下命令在 2026-11-12 本机运行，数据源为 fixture 或 fake transport，没有付费模型调用。改动保留在 `a311380` 之上的工作树，未提交或推送。

最终完整回归：253 项 unittest，252 项通过、1 项 PostgreSQL 专用测试在普通离线套件中跳过；该项在 `postgres-cloud-e2e.sh` 的临时 PostgreSQL 集群中单独通过。

| Command | Result / Coverage |
|---|---|
| `./scripts/test.sh` | unittest、compileall、Runtime schema / TS client 生成检查、CI 分类、30 篇文档链接与导航、TypeScript strict、Desktop 构建 |
| `pnpm install --frozen-lockfile` | 成功；React 类型声明加入开发依赖与锁文件 |
| `pnpm run build:web` | 成功；Web 使用同一工作台组件 |
| `./scripts/replay.sh` | 成功；冻结输入离线回放 |
| `./scripts/e2e.sh` | 成功；本地 API、事件、设备和 SSE |
| `./scripts/postgres-cloud-e2e.sh` | 成功；临时 PostgreSQL、多用户 Cloud、回放、暂停恢复、独立连接预算竞争 |
| `./scripts/cloud-backup-restore-e2e.sh` | 成功；PostgreSQL + DuckDB 恢复、pack / binding hash、metadata、归属与回放结果一致 |
| `./scripts/recovery-e2e.sh` | 成功；重启 checkpoint 与冻结绑定恢复 |
| `./scripts/chaos-e2e.sh` | 成功；异常恢复与子任务 |
| `./scripts/trust-ui-smoke.sh` | 成功；无效深链、数据视图、390px 无横向溢出 |
| `./scripts/build-sidecar.sh` + `health --json --isolation-check` | macOS arm64 打包与 spawn 成功；阻塞 worker 超时后清理 |
| `cargo tauri build --bundles app` | macOS Pia.app 构建成功；未签名发布 |
| `xcodebuild -scheme PiaApp -destination 'generic/platform=iOS Simulator' ... build` | BUILD SUCCEEDED；执行目录 `apps/ios/PiaMobileClient` |
| `swift test --package-path apps/ios/PiaMobileClient` | 8 tests passed |
| `ANDROID_HOME=$HOME/Library/Android/sdk ./apps/android/gradlew --no-daemon --project-dir apps/android :app:assembleDebug` | BUILD SUCCESSFUL；本机现有 Android 36 SDK |
| `actionlint` v1.7.7 | workflow 语法检查通过；工具临时安装在 `/tmp/pia-ci-tools/` |
| `git diff --check` | 通过 |

浏览器流程已执行：创建研究、Flow 展开、键盘 Enter 选择节点、JSON 导出、策略扫描、历史复算、因素展开、桌面和 390px 视口检查。截图和导出在被 Git 忽略的 `output/playwright/`，不作为仓库必需文件：

- `capability-flow-desktop.png`
- `capability-flow-mobile.png`
- `capability-scan-mobile.png`
- `capability-export.json`

浏览器下载的 JSON 已重新读取并通过 `validate_pack`，核对内容 hash。下载保留响应原文，避免重新编码整数形式的浮点数改变 hash。Adapter 测试还覆盖 Tushare 紧凑日期归一化，以及 AKShare 工作日估算只能为 partial。

## Implementation Boundaries

- 结论保持 WATCH / NO_ACTION / BLOCKED，`action_eligible=false`。complete 表示研究输入与适用阶段完整，不代表可交易，也不代表当前时间仍在 Evidence 有效期内。
- 必需行情、交易日与标的信息在 required_data 获取；已有冻结信息直接复用。可选基本面、公司介绍和新闻不会覆盖必需标的身份。公告触发的 supplemental 阶段提升为必需。
- 阶段预算为必需 LLM 和公告阶段预留时间；已完成的 Rules 不重复预留。暂停在调用边界生效，不承诺挂起已发送的外部请求。
- LLM 崩溃时未结算预留保留为 unknown，重启不清零。显式重试创建子任务并保留父任务费用，日预算继续累计；不会自动重发无法确认计费状态的 HTTP 请求。
- 首版仅提供 legacy 策略，不新增投资阈值。第二模型端点必须由用户配置并授权数据类别。
- 保留旧 `contracts-and-runtime` 检查作为过渡。新 `ci-required` 远端实际成功前，不能先删除原保护规则。

## External Gates

以下项目尚无验收证据，不能据此宣告发布就绪：

| Gate | Remaining Action |
|---|---|
| Windows frozen Sidecar / Tauri 生命周期 | 在 Windows runner 执行 workflow、`health --isolation-check` 与 Windows acceptance |
| 真实 AKShare / Tushare fallback 和 freshness | 用明确业务日期执行 provider-freshness；Tushare 需要授权凭据 |
| 真实模型端点与费用 | 用户确认端点、个人数据类别、价格与 token 上界后专门验收 |
| GitHub CI 状态传播 | 推送后验证 docs-only / 各执行面 / failed / cancelled / skipped 并保留运行链接 |
| 分支保护与 live-release Environment | 管理员启用 `ci-required` 与 Environment 保护 |
| 签名 / 公证 / 发布 | 沿用原发布门；本次未部署或发布 |

这些是外部证据与管理操作的待办；没有把未执行项标为通过。
