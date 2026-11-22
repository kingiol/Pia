# Operations

## 1. 环境

| 环境 | 用途 | 数据 |
|---|---|---|
| Local | MVP 运行、开发和规则调试 | 本机数据、脱敏或固定快照 |
| Staging | 集成、回放和试点前验证 | 受控测试数据 |
| Production | 真实用户研究 | 真实数据，最小权限 |

## 2. 部署基线

Local-first MVP 建议：

```text
Tauri Desktop
React UI
Python Local Agent
SQLite
DuckDB
Local Scheduler
Local Notification
```

Cloud API、PostgreSQL、远程队列和多设备通知属于后续扩展，不应成为本地 MVP 启动依赖。

Cloud 模式统一使用 PostgreSQL 保存业务记录和分析数据，启动必须设置
`PIA_POSTGRES_DSN`；不使用 SQLite / DuckDB 文件。Local 的部署基线不变。

开发环境允许使用 credential placeholders。真实 API key 和 Token 通过本机环境变量或系统 Credential Manager 注入，不提交到仓库、不写入任务结果和日志。DeepSeek 优先读取已保存的系统凭据，未保存时读取 `DEEPSEEK_API_KEY`。其他凭据仍优先读取环境变量；为空或为占位符时，读取 macOS Keychain、Linux Secret Service 或 Windows Credential Vault。

使用内置命令管理系统凭据：

```bash
./scripts/python.sh -m pia_runtime.cli credentials set DEEPSEEK_API_KEY
./scripts/python.sh -m pia_runtime.cli credentials status DEEPSEEK_API_KEY
./scripts/python.sh -m pia_runtime.cli credentials delete DEEPSEEK_API_KEY
```

`set` 使用隐藏输入，`status` 只返回是否已配置，不会打印凭据内容。Desktop 的 Local 模式也可以在「设置」中保存或清除 DeepSeek Key，后续请求立即生效。清除已保存的 Key 后恢复环境变量来源；修改环境变量后需要重启进程。

## 3. 监控

### 系统指标

- API latency/error rate；
- Worker heartbeat；
- queue depth；
- task age；
- database connections；
- storage usage。

### 产品指标

- 日终任务成功率；
- 任务 P95 完成时间；
- queue depth、active task count 和 oldest active task age；
- worker heartbeat age；
- SQLite/PostgreSQL backend 和存储大小；Cloud 的 database 为整个 PostgreSQL
  数据库大小，analytics_database 为其中分析表及索引大小，两者不可相加；
- `BLOCKED`、`NO_ACTION`、人工拒绝比例；
- evidence freshness；
- data completeness；
- agent/tool cost。
- LLM usage is persisted per task and user in `llm_usage`; configure
  `DEEPSEEK_INPUT_COST_PER_1K` and `DEEPSEEK_OUTPUT_COST_PER_1K` to report
  estimated USD cost through `GET /api/metrics`.

### 告警等级

- P0：未授权订单写入、数据时间错乱、密钥泄露；
- P1：日终任务大面积失败、持仓数据不可用、审计缺失；
- P2：单一数据源波动、某 Agent 延迟上升。

## 4. 数据质量检查

每次导入至少检查：

- 交易日是否匹配；
- 股票数量是否异常变化；
- 价格、成交量是否为空或负值；
- 重复记录；
- as-of 是否晚于 observed_at；
- 数据是否跨越未来时间；
- 供应商来源和版本。

可重复运行时间质量 soak：

```bash
./scripts/freshness-e2e.sh
```

该命令覆盖合法数据、未来 `as_of`、`observed_at` 顺序错误、过期证据和
未来公告时间；它验证本地质量门，不替代真实 Provider 的长期 freshness 监控。

质量不通过时：

1. 生成 `DataQualityDegraded`；
2. 阻断受影响的建议；
3. 保留可用的历史研究；
4. 通知用户数据状态。

## 5. 备份与恢复

### 桌面端数据隔离

`Pia` 和 `Pia Debug` 使用不同的应用标识。数据保存在系统应用本地数据目录中，每个目录只允许一个运行时写入。macOS 的默认目录如下。

| 版本 | 数据目录 |
| --- | --- |
| Release | `~/Library/Application Support/com.pia.investment` |
| Debug 真实行情 | `~/Library/Application Support/com.pia.investment.debug/live` |
| Debug 演示行情 | `~/Library/Application Support/com.pia.investment.debug/fixture` |

每个目录同时存放 `pia.sqlite3` 和 `pia.duckdb`。Debug 使用独立的凭据服务 `pia.debug`。通过环境变量传入调试凭据时，使用 `PIA_DEBUG_DEEPSEEK_API_KEY` 或 `PIA_DEBUG_TUSHARE_TOKEN`。Release 沿用现有的 `pia` 凭据服务。

**迁移旧数据**

1. 确认旧库的来源和目标版本。旧版调试脚本默认使用仓库内的 `.pia/debug`。旧打包版的临时解包目录可能在退出时清理。如果旧数据只存在于仍运行的临时目录，先保留进程并确认已有可用备份。
2. 对已关闭的旧数据目录留存完整副本。用副本制作备份时，显式设置 `PIA_DB_PATH` 和 `PIA_DUCKDB_PATH` 指向其中的 SQLite 和 DuckDB，再运行 `./scripts/python.sh -m pia_runtime.cli backup`，目标文件使用 `.zip` 后缀。
3. 退出目标应用，确认目标数据目录为空。将这两个变量改为目标目录下的对应文件路径，再运行 `./scripts/python.sh -m pia_runtime.cli restore` 并传入备份文件。打开目标应用，核对持仓、自选、规则和历史研究记录，再保留原副本用于回退。

验收时可用相同的绝对 `PIA_DESKTOP_DATA_BASE` 为两个版本指定临时根目录。两版仍会按应用标识写入各自的子目录。分别保存自选、同时运行两版并重启 Release，核对各自的数据和连接身份。

- SQLite：每日复制备份或用户可导出的备份文件；
- DuckDB：按快照版本保存；
- Ruleset/Profile：每次变更保留版本；
- 审计日志：追加保存，独立备份；
- 每月执行一次恢复演练。

本机通知 smoke：

```bash
./scripts/native-notification-smoke.sh
```

Windows 使用 `scripts/native-notification-smoke.ps1`。smoke 只验证当前
桌面会话能否接受通知，不替代跨用户、锁屏和系统策略下的发布验收。

Cloud PostgreSQL 统一备份：

运行模式的正式名称为 `local` 和 `cloud`。命令、环境变量、客户端配置、
脚本和产品文档使用 Cloud 命名。
旧 CLI 命令和认证环境变量保留兼容读取，新配置优先。iOS 的正式配置为
`pia.cloud_base_url` / `PIA_CLOUD_URL`，Android 为 `-PpiaCloudUrl`；
旧客户端配置仍可读取。Web 会话使用 `pia.cloud_token` 并兼容读取旧令牌。
旧脚本路径需要改为 `cloud`，验收包含单元测试、Local/Cloud API、调度、
PostgreSQL、备份恢复和客户端构建。

2026-11-16 起 Cloud 分析存储也使用 PostgreSQL。Cloud 尚未正式上线，直接使用
全新 PostgreSQL 数据库；开发数据库可以重建，不提供旧 DuckDB 数据迁移或旧备份兼容。
启动时自动初始化业务表与分析表；重建开发数据库前停止 API、worker 和 scheduler。
详细要求见 [Cloud Storage](CLOUD_STORAGE.md)。

```bash
PIA_POSTGRES_DSN='postgresql://...' \
  ./scripts/cloud-backup.sh .pia/backups/cloud-current

PIA_POSTGRES_DSN='postgresql://...' \
  ./scripts/cloud-restore.sh .pia/backups/cloud-current
```

备份目标必须是新目录。恢复前停止 Cloud 进程，脚本校验 manifest 中的文件大小和
SHA-256；`pg_restore` 在单次事务内恢复业务和分析数据，仅支持统一 PostgreSQL 备份。

本地临时 PostgreSQL 集群的备份恢复演练：

```bash
./scripts/cloud-backup-restore-e2e.sh
```

该命令会创建临时 UTF-8 PostgreSQL 集群，将任务和分析快照写入同一数据库，执行
`pg_dump`、删除快照、`pg_restore`，最后验证上下文 hash、分析表和离线回放。
它不会使用
`PIA_POSTGRES_DSN`，避免误操作外部数据库。

Cloud API 的临时 PostgreSQL 验收：

```bash
./scripts/postgres-cloud-e2e.sh
```

该命令会启动隔离的 PostgreSQL 集群，并运行认证、任务控制、人工审批、租约、
用户隔离、事件、设备生命周期和幂等性 E2E。

恢复目标：

- RPO <= 24 小时；
- RTO <= 4 小时（MVP，使用本地备份恢复）。

Push deployment configuration:

- `VITE_WEB_PUSH_PUBLIC_KEY` is the browser VAPID public key used by the Web
  client to create a subscription;
- `PIA_WEB_PUSH_GATEWAY_URL` / `PIA_WEB_PUSH_GATEWAY_TOKEN` route Web Push
  subscriptions;
- `PIA_APNS_GATEWAY_URL` / `PIA_APNS_GATEWAY_TOKEN` route iOS tokens;
- `PIA_FCM_GATEWAY_URL` / `PIA_FCM_GATEWAY_TOKEN` route Android tokens.

The gateway owns provider-specific signing and quota handling. Pia records
delivery receipts in `notification_deliveries` and does not report a notification
as delivered when the configured gateway returns an error. Operators can inspect
the receipts through `GET /api/notifications/{notification_id}/deliveries`.

Release acceptance for configured external push gateways:

```bash
PIA_WEB_PUSH_GATEWAY_URL='https://...' \
PIA_WEB_PUSH_GATEWAY_TOKEN='...' \
PIA_PUSH_ACCEPTANCE_WEB_TOKEN='test-subscription-or-device-token' \
  ./scripts/push-acceptance.sh
```

The same command accepts `PIA_APNS_GATEWAY_URL` with
`PIA_PUSH_ACCEPTANCE_IOS_TOKEN`, and `PIA_FCM_GATEWAY_URL` with
`PIA_PUSH_ACCEPTANCE_ANDROID_TOKEN`. It registers a scoped device, emits a
synthetic acceptance event, and requires a persisted `DELIVERED` receipt from
the platform gateway. It is intentionally separate from the local gateway
contract test because it sends a real external notification.

Provider resilience configuration:

- `PIA_PROVIDER_RETRY_ATTEMPTS` bounds request attempts;
- `PIA_PROVIDER_RETRY_BACKOFF_SECONDS` and
  `PIA_PROVIDER_RETRY_MAX_BACKOFF_SECONDS` control exponential backoff;
- `PIA_PROVIDER_CIRCUIT_FAILURE_THRESHOLD` opens a provider circuit after
  consecutive transient failures;
- `PIA_PROVIDER_CIRCUIT_RESET_SECONDS` controls the cooldown before a new
  probe is allowed.

`GET /api/health` exposes each provider's runtime circuit state, retry count,
failure count and last error. Circuit-open providers are skipped by routing;
when fallback is enabled, the next eligible provider is attempted.

DeepSeek uses the same bounded retry policy shape with
`PIA_LLM_RETRY_ATTEMPTS`, `PIA_LLM_RETRY_BACKOFF_SECONDS` and
`PIA_LLM_RETRY_MAX_BACKOFF_SECONDS`. JSON requests and streams are retried only
for transient transport or 429/5xx errors; a stream that already emitted output
is surfaced as failed instead of being replayed into duplicate text.

## 6. 任务运维

任务必须支持：

- 超时；
- 重试；
- 断点继续；
- 取消；
- 人工接管；
- 导出上下文。

本地或 Cloud API 提供：

- `POST /api/tasks/{task_id}/takeover`：记录人工接管人、原状态和备注；
- `GET /api/tasks/{task_id}/context`：导出任务、Trace、Evidence、审批、Profile
  和 Rules 快照，供人工排障与回放。

禁止：

- 静默删除失败任务；
- 无审计地手工修改决策；
- 将旧任务重新绑定到新规则快照。

## 7. 发布流程

1. 运行 unit、integration、replay、security tests。
2. 在本地回放固定日期任务。
3. 检查迁移、备份和回滚。
4. 运行发布预检，确认制品、平台、凭据和外部推送状态：

```bash
./scripts/release-preflight.sh
```

该命令会明确输出 `mvp_release_ready`、`full_milestone_release_ready`
以及每个未验证能力的原因；缺少凭据或平台运行证据时返回非零状态，
不会把本地 contract test 伪装成外部发布通过。
   在已配置真实 Provider 凭据后，可用多个已确认的交易日运行 freshness gate：

   ```bash
   PIA_DATA_PROVIDER=akshare \
   PIA_FRESHNESS_DATES=2026-11-04,2026-11-05,2026-11-06 \
   ./scripts/provider-freshness-e2e.sh
   ```

   该 gate 会逐日执行完整 DataWorker 同步，检查聚合质量、市场快照质量、
   字段完整率和失败列表。也可以让 Provider 根据交易日历自动选择最近的
   N 个开市日：

   ```bash
   PIA_DATA_PROVIDER=akshare \
   PIA_FRESHNESS_LOOKBACK_DAYS=5 \
   ./scripts/provider-freshness-e2e.sh
   ```

   没有显式日期或 lookback 设置时会返回跳过状态，不会访问外部 Provider。

手动运行 `.github/workflows/release-gates.yml` 时，填写一个已收盘的交易日和
要检查的交易日列表，并通过 `live-release` Environment 提供验收凭据。
macOS job 验证 DeepSeek structured/stream/tool-call 和 AKShare freshness，
并按凭据配置验证 Tushare fallback 和外部推送。缺少 `DEEPSEEK_API_KEY` 时
验收失败。Windows job 在 MSI 打包和验收后执行发布预检，上传
`pia-release-preflight` 报告。当前 MVP 预检同时要求 `TUSHARE_TOKEN`。
macOS job 的 Actions 摘要列出实际报告为跳过的检查，包括依赖工作站
Playwright 脚本的 GUI smoke。工作站仍可用 `./scripts/acceptance.sh` 运行该检查。
`.github/workflows/provider-freshness.yml` 会在工作日定期运行最近五个
Provider 开市日的 freshness gate，也支持手动选择 AKShare 或 Tushare。
5. 发布候选版本。
6. 观察一轮完整收盘周期。
7. 通过试点清单后逐步放量。

试点操作入口：

- [试点用户手册](PILOT_USER_GUIDE.md)
- [试点复盘模板](PILOT_RETROSPECTIVE_TEMPLATE.md)

发布候选包应生成制品清单和 SHA-256：

```bash
./scripts/release-manifest.sh
```

输出默认写入 `.pia/release/manifest.json`。配置
`PIA_RELEASE_SIGNING_KEY` 后，脚本会额外使用 OpenSSL 生成
`.pia/release/manifest.sig`；未配置签名密钥时不会伪造签名状态。

## 8. 事故处理

### 规则绕过

- 立即禁用建议生成；
- 保留只读查询和审计；
- 锁定相关版本和任务；
- 复现并增加回归测试；
- 由产品负责人决定恢复。

### 数据错误

- 标记受影响快照；
- 阻断相关决策；
- 通知用户；
- 修复数据后重新回放；
- 不覆盖旧审计记录。

### Worker 故障

- 检查心跳和队列；
- 重启单个 Worker；
- 失败任务按幂等键恢复；
- 观察是否重复发送通知。
