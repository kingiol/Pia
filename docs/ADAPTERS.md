# Provider and Platform Adapter Architecture

## 1. 当前覆盖情况

原有文档已经涉及：

- 数据源和数据供应商；
- `source`、`observed_at`、`as_of`、`quality` 等数据元信息；
- Broker/Order Adapter 的只读或模拟边界；
- Web、Tauri、iOS、Android 的 Transport；
- Notification Provider；
- 内部 Service/RPC 和外部 MCP。

原有文档没有完整定义：

- Provider Adapter 的统一接口；
- Provider 能力和版本声明；
- 多 Provider 路由、优先级和故障切换；
- Provider DTO 到统一领域模型的归一化；
- Adapter 的健康检查、限流、重试和熔断；
- Broker、LLM、通知、存储和平台 Adapter 的共同规范；
- Adapter Contract Tests 和回放夹具。

本文件补齐这些边界。

## 2. 总体原则

```text
Domain / Agent / Rules
          |
          v
       Ports
          |
          v
Provider Registry / Router
          |
    +-----+------+--------+---------+
    |            |        |         |
 Market       News     Broker     LLM
 Adapter      Adapter  Adapter    Adapter
    |            |        |         |
 Provider SDK / HTTP / MCP / Native SDK
```

原则：

1. Agent、Rules 和 Domain 不直接导入 Provider SDK。
2. Provider-specific DTO 不得穿透 Adapter 边界。
3. 所有外部结果都必须带来源、时间点、质量和快照标识。
4. Adapter 只负责连接和转换，不负责投资判断。
5. 不能安全归一化的数据必须标记为 `partial` 或 `unavailable`。
6. Provider 切换不能改变任务、规则和审计的领域模型。

## 3. Adapter 分类

| Adapter | 典型实现 | 核心用途 | MVP |
|---|---|---|---|
| Market Data | `akshare` 主、`tushare` 备、交易所接口 | 日线、指数、市场广度、交易日历 | P0 |
| Fundamental | Tushare、公告解析、授权数据 | 财报、财务指标、公司资料 | P0 |
| News/Filing | 新闻供应商、交易所公告 | 新闻、公告、财报事件 | P0 |
| Broker/Portfolio | 券商 API、导入文件、模拟账户 | 持仓、现金、订单预览 | 只读/模拟 |
| LLM | `deepseek`、其他云端模型、企业网关、本地模型 | 结构化推理和文本生成 | P0 |
| Embedding | 云端或本地模型 | 语义检索 | P1 |
| Notification | Web Push、Email、APNs、FCM | 通知和设备注册 | P0 |
| Storage | PostgreSQL、SQLite、DuckDB、对象存储 | 事务、快照和分析 | P0 |
| Queue/Scheduler | Redis、数据库队列、系统调度器 | 任务和事件调度 | P0 |
| Platform | Tauri、Web、iOS、Android | 文件、通知、后台和安全存储 | P1 |

Local 桌面可以在「设置 → Tushare」保存 Token。真实行情同步中的 A 股股票日线优先使用免费 `daily`，其余能力由 AKShare 提供。免费档为未复权日线，账户需有 120 积分权限。[Tushare 积分与频次](https://tushare.pro/document/1?doc_id=290)

## 4. Provider Contract

每个 Adapter 必须声明：

```text
provider_id
provider_version
adapter_version
capabilities
markets
data_granularity
rate_limits
requires_credentials
supports_point_in_time
supports_replay
health_status
```

示例：

```json
{
  "provider_id": "tushare",
  "provider_version": "api-v1",
  "adapter_version": "0.1.0",
  "capabilities": [
    "trading_calendar",
    "daily_bars",
    "fundamentals"
  ],
  "markets": ["CN_STOCK"],
  "data_granularity": ["daily"],
  "supports_point_in_time": true,
  "supports_replay": true,
  "health_status": "healthy"
}
```

MVP 的主行情 Adapter 使用 `akshare` Python package，默认不配置 API key；`requires_credentials=false`。这不代表完全离线，网络可用性、上游接口变化和数据质量仍必须经过 Health Check 与 Quality Gate。备用 `tushare` Adapter 单独管理 Token 和配额。

## 5. Market Data Port

领域层只依赖 Port：

```python
class MarketDataProvider(Protocol):
    provider_id: str

    def capabilities(self) -> set[str]: ...

    def health(self) -> HealthStatus: ...

    def get_trading_calendar(
        self, start: date, end: date
    ) -> list[TradingDay]: ...

    def get_daily_bars(
        self, symbols: list[str], as_of: date
    ) -> list[DailyBar]: ...

    def get_market_breadth(
        self, as_of: date
    ) -> MarketBreadth: ...
```

Provider Adapter 内部负责：

- API Key 和签名；
- HTTP/RPC 调用；
- 分页；
- 限流；
- 重试；
- Provider 错误映射；
- Provider DTO 转换；
- 原始响应落盘；
- 请求审计。

## 6. News/Filing Port

```python
class ResearchSourceProvider(Protocol):
    def search_news(self, query: NewsQuery) -> list[NewsItem]: ...

    def search_filings(
        self, symbols: list[str], since: datetime
    ) -> list[Filing]: ...

    def get_source_health(self) -> HealthStatus: ...
```

要求：

- 记录来源 URL、发布时间、抓取时间和授权状态；
- 保存摘要和内容哈希，不默认复制受限全文；
- 将新闻和公告统一为 `Evidence`；
- 不能确认发布时间或来源时，不得进入高置信度结论。

## 7. Broker/Portfolio Adapter

Broker Adapter 分为能力层：

```text
READ_PORTFOLIO
READ_BALANCE
READ_ORDERS
PREVIEW_ORDER
PAPER_SUBMIT
LIVE_SUBMIT
```

MVP 只开放：

```text
READ_PORTFOLIO
READ_BALANCE
READ_ORDERS
PAPER_SUBMIT
```

接口示例：

```python
class BrokerAdapter(Protocol):
    def capabilities(self) -> set[BrokerCapability]: ...

    def get_portfolio(self) -> PortfolioSnapshot: ...

    def get_balances(self) -> BalanceSnapshot: ...

    def preview_order(self, order: OrderRequest) -> OrderPreview: ...

    def submit_order(self, order: OrderRequest) -> OrderReceipt:
        raise NotImplementedError
```

`LIVE_SUBMIT` 必须同时满足：

- 用户显式开启；
- Adapter 声明能力；
- Rules Engine 通过；
- Risk Review 通过；
- 人工审批通过；
- 二次确认和审计记录完整。

没有这些条件时，接口应返回 `CAPABILITY_DISABLED`，而不是静默降级成模拟成交。

## 8. LLM Provider Adapter

LLM Adapter 统一：

- 结构化输出；
- 流式输出；
- Token 和成本统计；
- 超时；
- 重试；
- 模型版本；
- 内容安全错误；
- Tool Calling 能力声明。

`ModelRouter` 是 Agent 的唯一 LLM 入口。它按任务所需能力、首选
provider 和优先级选择可用模型，并暴露统一的 provider/model/usage
信息；Agent 不直接绑定具体 SDK。DeepSeek adapter 会把 HTTP 状态、限流、
认证失败、内容安全拦截、临时不可用和无效结构化响应映射为稳定错误码，
由 Runtime 决定任务进入 `RETRYABLE` 还是 `FAILED`。

MVP 的 DeepSeek 配置：

```text
provider_id: deepseek
base_url: https://api.deepseek.com
endpoint: POST /chat/completions
model: deepseek-flash
protocol: OpenAI-compatible
streaming: enabled
structured_output: enabled
tool_calls: enabled
```

`Responses API` 暂不作为 MVP 默认路径；未来可以在同一个 `LLMProvider` Port 下增加实现。

```python
class LLMProvider(Protocol):
    def capabilities(self) -> set[str]: ...

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult: ...

    def stream_structured(
        self, request: StructuredGenerationRequest
    ) -> AsyncIterator[GenerationEvent]: ...
```

Agent 不应直接写死某个模型名称，模型选择由 `ModelRouter` 根据任务、成本、延迟和结构化输出能力决定。

## 9. Notification Adapter

```python
class NotificationProvider(Protocol):
    def register_device(self, device: DeviceRegistration) -> None: ...

    def send(self, message: NotificationMessage) -> DeliveryReceipt: ...

    def health(self) -> HealthStatus: ...
```

当前已提供本机 native provider、cloud webhook gateway、按用户设备路由的
device gateway adapter，以及按平台分路的 push gateway adapter。渠道包括：

- Web Push；
- Email；
- APNs；
- FCM；
- 桌面系统通知。

通知 Adapter 只负责投递，不负责决定是否应该通知。通知策略由 Event Engine 和用户偏好决定。

Cloud runtime 可通过 `PIA_NOTIFICATION_WEBHOOK_URL` 和
`PIA_NOTIFICATION_WEBHOOK_TOKEN` 配置一个通用 gateway；也可通过
`PIA_DEVICE_PUSH_GATEWAY_URL` 和 `PIA_DEVICE_PUSH_GATEWAY_TOKEN` 配置按设备
路由的 Web Push/APNs/FCM gateway。设备 gateway 会读取当前用户已注册且有
`push_token` 的设备，并发送 `notification_id`、`user_id`、`title`、`body`
和设备列表。每次投递都会把 provider、状态、详情和时间写入
`notification_deliveries`，并可通过
`GET /api/notifications/{notification_id}/deliveries` 查询；前端不会暴露 provider
credentials。需要平台独立路由时，可分别配置
`PIA_WEB_PUSH_GATEWAY_URL`、`PIA_APNS_GATEWAY_URL` 和
`PIA_FCM_GATEWAY_URL` 及对应 token；每个请求只包含该平台的设备 token，
平台 gateway 负责连接具体的 Web Push、APNs 或 FCM 服务。

## 10. Storage 和 Queue Adapter

Storage 使用 Repository Port：

```text
ResearchTaskRepository
EvidenceRepository
DecisionRepository
ApprovalRepository
SnapshotRepository
```

Queue/Scheduler 使用：

```text
TaskQueue
EventScheduler
DistributedLock
CooldownStore
```

业务代码不直接依赖 Redis、PostgreSQL 或 SQLite API。这样本地 Tauri 模式可以使用 SQLite/DuckDB，云端模式使用 PostgreSQL，而任务和审计模型保持一致。

## 11. Provider Registry 和路由

Provider Registry 维护：

```text
provider_id
capabilities
priority
markets
freshness_sla
quota
health
credential_ref
enabled
```

路由顺序：

1. 匹配业务能力；
2. 匹配市场和粒度；
3. 排除健康状态异常的 Provider；
4. 按用户或环境配置排序；
5. 检查时效和授权；
6. 执行请求；
7. 失败时根据策略切换或阻断；
8. 将实际 Provider 写入结果元数据。

不允许为了“有数据”而静默混合不同时间点、不同口径或不同授权范围的数据。

## 12. Normalization 和 Provenance

```text
Provider Response
      |
      v
RawEnvelope
      |
      v
Normalizer
      |
      v
Canonical Domain Model
      |
      v
Quality Check
      |
      v
Snapshot + Evidence
```

每条标准化数据保留：

- `provider_id`
- `provider_version`
- `adapter_version`
- `raw_payload_hash`
- `observed_at`
- `as_of`
- `quality`
- `normalization_warnings`
- `snapshot_id`

## 13. 故障处理

### Retryable

- 超时；
- 429 限流；
- 临时网络错误；
- Provider 维护窗口。

### Non-retryable

- 凭据失效；
- 参数不合法；
- 数据不支持目标市场；
- 授权范围不足。

### Blocked

- 时间点不可信；
- 数据质量不合格；
- Provider 返回字段口径变化；
- 没有任何可用 Provider。

发生 `Blocked` 时，Rules Engine 必须阻断受影响的研究或建议。

## 14. 目录约定

```text
packages-py/
  pia-adapters/
    base/
      capabilities.py
      health.py
      errors.py
      registry.py
      routing.py
    market_data/
      tushare.py
      akshare.py
      exchange_official.py
    research/
      news_provider.py
      filing_provider.py
    broker/
      import_file.py
      paper.py
      live_broker.py
    llm/
      deepseek.py
      openai_provider.py
      local_provider.py
    notifications/
      web_push.py
      email.py
      apns.py
      fcm.py
    storage/
      postgres.py
      sqlite.py
      duckdb.py
```

## 15. Contract Tests

每个 Adapter 必须通过同一组契约测试：

- 能力声明正确；
- 健康检查可用；
- Provider 错误能映射为统一错误；
- 原始响应能生成稳定领域模型；
- 缺失字段会产生质量状态；
- 时间点和来源不会丢失；
- 重试不会重复写入；
- 失败不会伪造成功数据；
- 回放夹具可以重建标准化结果。

Provider 接入的完成定义不是“API 调通”，而是“通过 Contract Tests、质量检查和回放测试”。

当 Provider credential 尚未配置时，Adapter 必须返回可识别的 `CREDENTIALS_REQUIRED` 或 `CAPABILITY_DISABLED`，并保留任务失败原因。MVP 的 LLM 集成测试和 E2E 必须调用真实 DeepSeek API，不允许切换到 Mock LLM；数据、Rules 和 Event 层仍可使用固定 fixtures。
