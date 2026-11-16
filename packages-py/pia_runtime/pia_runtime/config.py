from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .credentials import configured_secret


def _runtime_root() -> Path:
    configured = os.getenv("PIA_RUNTIME_ROOT")
    if configured:
        return Path(configured)
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "resources"
    return Path(__file__).resolve().parents[3]


ROOT = _runtime_root()


@dataclass(slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    db_path: Path = field(default_factory=lambda: ROOT / ".pia" / "pia.sqlite3")
    analytics_db_path: Path | None = None
    fixture_dir: Path = field(default_factory=lambda: ROOT / "tests" / "fixtures")
    rules_path: Path = field(default_factory=lambda: ROOT / "rules" / "baseline.yaml")
    deterministic_replay: bool = True
    require_llm: bool = False
    llm_streaming: bool = False
    llm_policy_path: Path | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    llm_retry_attempts: int = 2
    llm_retry_backoff_seconds: float = 0.25
    llm_retry_max_backoff_seconds: float = 2.0
    deepseek_input_cost_per_1k: float = 0.0
    deepseek_output_cost_per_1k: float = 0.0
    mode: str = "local"
    postgres_dsn: str | None = None
    cloud_auth_token: str | None = None
    cloud_users: dict[str, str] = field(default_factory=dict)
    tushare_token: str | None = None
    task_timeout_seconds: int = 300
    autostart_tasks: bool = True
    scheduler_enabled: bool = False
    scheduler_timezone: str = "Asia/Shanghai"
    market_close_time: str = "15:05"
    scheduler_poll_seconds: float = 15.0
    native_notifications: bool = False
    structured_logs: bool = False
    notification_webhook_url: str | None = None
    notification_webhook_token: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_smtp_username: str | None = None
    email_smtp_password: str | None = None
    email_sender: str | None = None
    email_recipient: str | None = None
    email_smtp_ssl: bool = False
    email_smtp_starttls: bool = True
    device_push_gateway_url: str | None = None
    device_push_gateway_token: str | None = None
    web_push_gateway_url: str | None = None
    web_push_gateway_token: str | None = None
    apns_gateway_url: str | None = None
    apns_gateway_token: str | None = None
    fcm_gateway_url: str | None = None
    fcm_gateway_token: str | None = None
    data_provider: str = "fixture"
    provider_fallback_enabled: bool = True
    provider_retry_attempts: int = 2
    provider_retry_backoff_seconds: float = 0.25
    provider_retry_max_backoff_seconds: float = 2.0
    provider_circuit_failure_threshold: int = 3
    provider_circuit_reset_seconds: float = 30.0
    scheduler_symbols: list[str] = field(default_factory=list)
    lease_ttl_seconds: int = 60
    lease_heartbeat_seconds: float = 15.0
    worker_poll_seconds: float = 0.5
    task_execution_delay_seconds: float = 0.0
    auto_event_generation: bool = True
    market_breadth_event_threshold: float = 0.15
    price_volume_anomaly_pct: float = 5.0
    portfolio_risk_drawdown_delta: float = 0.05
    portfolio_risk_weight_delta: float = 0.10

    def __post_init__(self) -> None:
        # Normalize the legacy name before execution and storage decisions.
        if self.mode == "server":
            self.mode = "cloud"
        if self.analytics_db_path is None:
            self.analytics_db_path = self.db_path.with_suffix(".duckdb")

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = Path(os.getenv("PIA_DB_PATH", str(ROOT / ".pia" / "pia.sqlite3")))
        fixture_dir = Path(os.getenv("PIA_FIXTURE_DIR", str(ROOT / "tests" / "fixtures")))
        cloud_auth_token = (
            configured_secret("PIA_CLOUD_AUTH_TOKEN")
            or configured_secret("PIA_SERVER_AUTH_TOKEN")
        )
        return cls(
            host=os.getenv("PIA_HOST", "127.0.0.1"),
            port=int(os.getenv("PIA_PORT", "8765")),
            db_path=db_path,
            analytics_db_path=Path(
                os.getenv("PIA_DUCKDB_PATH", str(db_path.with_suffix(".duckdb")))
            ),
            fixture_dir=fixture_dir,
            rules_path=Path(os.getenv("PIA_RULES_PATH", str(ROOT / "rules" / "baseline.yaml"))),
            deterministic_replay=os.getenv("PIA_DETERMINISTIC_REPLAY", "1") == "1",
            require_llm=os.getenv("PIA_REQUIRE_LLM", "0") == "1",
            llm_streaming=os.getenv("PIA_LLM_STREAMING", "0") == "1",
            llm_policy_path=Path(os.environ["PIA_LLM_POLICY_PATH"]) if os.getenv("PIA_LLM_POLICY_PATH") else None,
            deepseek_api_key=configured_secret("DEEPSEEK_API_KEY"),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            llm_retry_attempts=int(os.getenv("PIA_LLM_RETRY_ATTEMPTS", "2")),
            llm_retry_backoff_seconds=float(
                os.getenv("PIA_LLM_RETRY_BACKOFF_SECONDS", "0.25")
            ),
            llm_retry_max_backoff_seconds=float(
                os.getenv("PIA_LLM_RETRY_MAX_BACKOFF_SECONDS", "2.0")
            ),
            deepseek_input_cost_per_1k=float(
                os.getenv("DEEPSEEK_INPUT_COST_PER_1K", "0")
            ),
            deepseek_output_cost_per_1k=float(
                os.getenv("DEEPSEEK_OUTPUT_COST_PER_1K", "0")
            ),
            mode=os.getenv("PIA_MODE", "local"),
            postgres_dsn=os.getenv("PIA_POSTGRES_DSN"),
            cloud_auth_token=cloud_auth_token,
            cloud_users=_parse_cloud_users(
                os.getenv("PIA_CLOUD_USERS", os.getenv("PIA_SERVER_USERS", "")),
                cloud_auth_token,
            ),
            tushare_token=configured_secret("TUSHARE_TOKEN"),
            task_timeout_seconds=int(os.getenv("PIA_TASK_TIMEOUT_SECONDS", "300")),
            autostart_tasks=os.getenv("PIA_AUTOSTART_TASKS", "1") == "1",
            scheduler_enabled=os.getenv("PIA_SCHEDULER_ENABLED", "0") == "1",
            scheduler_timezone=os.getenv("PIA_SCHEDULER_TIMEZONE", "Asia/Shanghai"),
            market_close_time=os.getenv("PIA_MARKET_CLOSE_TIME", "15:05"),
            scheduler_poll_seconds=float(os.getenv("PIA_SCHEDULER_POLL_SECONDS", "15")),
            native_notifications=os.getenv("PIA_NATIVE_NOTIFICATIONS", "0") == "1",
            structured_logs=os.getenv("PIA_STRUCTURED_LOGS", "0") == "1",
            notification_webhook_url=os.getenv("PIA_NOTIFICATION_WEBHOOK_URL"),
            notification_webhook_token=configured_secret("PIA_NOTIFICATION_WEBHOOK_TOKEN"),
            email_smtp_host=os.getenv("PIA_EMAIL_SMTP_HOST"),
            email_smtp_port=int(os.getenv("PIA_EMAIL_SMTP_PORT", "587")),
            email_smtp_username=os.getenv("PIA_EMAIL_SMTP_USERNAME"),
            email_smtp_password=configured_secret("PIA_EMAIL_SMTP_PASSWORD"),
            email_sender=os.getenv("PIA_EMAIL_SENDER"),
            email_recipient=os.getenv("PIA_EMAIL_RECIPIENT"),
            email_smtp_ssl=os.getenv("PIA_EMAIL_SMTP_SSL", "0") == "1",
            email_smtp_starttls=os.getenv("PIA_EMAIL_SMTP_STARTTLS", "1") == "1",
            device_push_gateway_url=os.getenv("PIA_DEVICE_PUSH_GATEWAY_URL"),
            device_push_gateway_token=configured_secret("PIA_DEVICE_PUSH_GATEWAY_TOKEN"),
            web_push_gateway_url=os.getenv("PIA_WEB_PUSH_GATEWAY_URL"),
            web_push_gateway_token=configured_secret("PIA_WEB_PUSH_GATEWAY_TOKEN"),
            apns_gateway_url=os.getenv("PIA_APNS_GATEWAY_URL"),
            apns_gateway_token=configured_secret("PIA_APNS_GATEWAY_TOKEN"),
            fcm_gateway_url=os.getenv("PIA_FCM_GATEWAY_URL"),
            fcm_gateway_token=configured_secret("PIA_FCM_GATEWAY_TOKEN"),
            data_provider=os.getenv("PIA_DATA_PROVIDER", "fixture"),
            provider_fallback_enabled=os.getenv("PIA_PROVIDER_FALLBACK", "1") == "1",
            provider_retry_attempts=int(os.getenv("PIA_PROVIDER_RETRY_ATTEMPTS", "2")),
            provider_retry_backoff_seconds=float(
                os.getenv("PIA_PROVIDER_RETRY_BACKOFF_SECONDS", "0.25")
            ),
            provider_retry_max_backoff_seconds=float(
                os.getenv("PIA_PROVIDER_RETRY_MAX_BACKOFF_SECONDS", "2.0")
            ),
            provider_circuit_failure_threshold=int(
                os.getenv("PIA_PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "3")
            ),
            provider_circuit_reset_seconds=float(
                os.getenv("PIA_PROVIDER_CIRCUIT_RESET_SECONDS", "30")
            ),
            scheduler_symbols=[
                item.strip()
                for item in os.getenv("PIA_SCHEDULER_SYMBOLS", "").split(",")
                if item.strip()
            ],
            lease_ttl_seconds=int(os.getenv("PIA_LEASE_TTL_SECONDS", "60")),
            lease_heartbeat_seconds=float(os.getenv("PIA_LEASE_HEARTBEAT_SECONDS", "15")),
            worker_poll_seconds=float(os.getenv("PIA_WORKER_POLL_SECONDS", "0.5")),
            task_execution_delay_seconds=float(
                os.getenv("PIA_TASK_EXECUTION_DELAY_SECONDS", "0")
            ),
            auto_event_generation=os.getenv("PIA_AUTO_EVENT_GENERATION", "1") == "1",
            market_breadth_event_threshold=float(
                os.getenv("PIA_MARKET_BREADTH_EVENT_THRESHOLD", "0.15")
            ),
            price_volume_anomaly_pct=float(
                os.getenv("PIA_PRICE_VOLUME_ANOMALY_PCT", "5.0")
            ),
            portfolio_risk_drawdown_delta=float(
                os.getenv("PIA_PORTFOLIO_RISK_DRAWDOWN_DELTA", "0.05")
            ),
            portfolio_risk_weight_delta=float(
                os.getenv("PIA_PORTFOLIO_RISK_WEIGHT_DELTA", "0.10")
            ),
        )


def _parse_cloud_users(raw: str, default_token: str | None) -> dict[str, str]:
    users: dict[str, str] = {}
    if default_token:
        users[default_token] = "default"
    for item in raw.split(","):
        if not item.strip() or "=" not in item:
            continue
        token, user_id = item.split("=", 1)
        if token.strip() and user_id.strip():
            users[token.strip()] = user_id.strip()
    return users
