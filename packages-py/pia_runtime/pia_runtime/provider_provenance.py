from __future__ import annotations

import json
import inspect
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .adapters import ProviderResultDegraded
from .decision_context import canonical_json, sanitize_context
from .data_quality import REQUIRED_MARKET_FIELDS, validate_temporal_metadata
from .models import new_id, now_iso


class CapabilityUnavailable(RuntimeError):
    code = "CAPABILITY_UNAVAILABLE"
    retryable = True


def routed_call(
    runtime: Any, capability: str, method_name: str, args: tuple,
    kwargs: dict[str, Any], *, fixture_name: str | None = None,
) -> tuple[Any, Any]:
    from .runtime import _provider_result_quality

    scope = getattr(runtime._provider_context, "user_id", "default")
    task_id = getattr(runtime._provider_context, "task_id", None)
    call_id = new_id("provider_call")
    attempts: list[dict[str, Any]] = []
    requested_symbol = str(args[0] if args else kwargs.get("symbol", "")) if capability == "daily_bars" else ""
    preferred = runtime._market_provider_preference(capability, requested_symbol)
    chain = [runtime.fixture_provider] if runtime.settings.data_provider == "fixture" else runtime._provider_chain(capability, requested_symbol)
    if not runtime.settings.provider_fallback_enabled:
        chain = chain[:1]
    subject = str(args[0]) if args and "." in str(args[0]) else ""
    as_of = str(kwargs.get("as_of") or next(
        (arg for arg in reversed(args) if isinstance(arg, str) and len(arg) == 10 and arg[4:5] == "-"),
        datetime.now(timezone.utc).date().isoformat(),
    ))
    degraded_result = None
    degraded_provider = None

    def invoke(provider, method_name, args, kwargs):
        from .adapters import AkshareMarketProvider, TushareMarketProvider
        from .isolated_call import isolated_call, provider_leaf

        budget = getattr(runtime._provider_context, "budget", None)
        if budget:
            runtime._check_pause(budget.task)
            runtime._check_timeout(budget.task)
            budget.check()
        if type(provider) in {AkshareMarketProvider, TushareMarketProvider}:
            return isolated_call(
                provider_leaf, (provider.provider_id, getattr(provider, "token", None), method_name, args, kwargs),
                {"daily_only": getattr(provider, "daily_only", False)},
                timeout=budget.timeout() if budget else 45,
                check=(lambda: runtime._check_timeout(budget.task)) if budget else None,
            )
        return getattr(provider, method_name)(*args, **kwargs)

    def quality_check(name: str, result: Any) -> tuple[bool, str | None]:
        valid, reason = _provider_result_quality(name, result)
        if valid and isinstance(result, dict) and name == "market_snapshot":
            missing = REQUIRED_MARKET_FIELDS - result.keys()
            if missing:
                return False, "REQUIRED_FIELDS_MISSING"
            temporal = validate_temporal_metadata(
                {key: value for key, value in result.items() if key != "expires_at"},
                latest_allowed_as_of=as_of,
            )
            if not temporal["valid"]:
                return False, temporal["errors"][0]["code"]
        return valid, reason

    def record(attempt: dict[str, Any]) -> None:
        attempt = {
            **attempt, "ordinal": len(attempts) + 1,
            "fallback_from": attempts[-1]["provider_id"] if attempts else None,
        }
        attempts.append(attempt)
        runtime.db.execute(
            """INSERT INTO provider_attempts(id, user_id, task_id, call_id, ordinal, payload_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (attempt["attempt_id"], scope, task_id, call_id, attempt["ordinal"], canonical_json(attempt)),
        )
        if task_id:
            runtime.db.append_event(task_id, "PROVIDER_ATTEMPT", attempt)
        runtime.observability.record_provider_call(
            capability, attempt["provider_id"], method_name, attempt["duration_ms"],
            success=attempt["outcome"] == "success",
        )
        runtime.db.audit(task_id, "PROVIDER_ATTEMPT", attempt, user_id=scope)

    for provider in chain:
        call_kwargs = dict(kwargs)
        if fixture_name is not None and method_name == "get_market_snapshot":
            call_kwargs["fixture_name"] = fixture_name
        method = getattr(provider, method_name, None)
        if method is not None and "as_of" in call_kwargs:
            parameters = inspect.signature(method).parameters
            if "as_of" not in parameters and not any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            ):
                call_kwargs.pop("as_of")
        try:
            result = runtime.providers.call(
                provider, method_name, *args, capability=capability, call_id=call_id,
                credential_scope=scope, on_attempt=record, quality_check=quality_check, invoke=invoke,
                **call_kwargs,
            )
            health = provider.health()
            for row in [result] if isinstance(result, dict) else result if isinstance(result, list) else []:
                if isinstance(row, dict):
                    row.update(provider_id=provider.provider_id)
                    row.setdefault("provider_version", health.provider_version)
                    row.setdefault("adapter_version", health.adapter_version)
            result = attach_provenance(result, provider.provider_id, attempts)
            for row in [result] if isinstance(result, dict) else result if isinstance(result, list) else []:
                if isinstance(row, dict):
                    row["provenance"]["fallback_used"] |= provider.provider_id != preferred
            rows = [result] if isinstance(result, dict) else result if isinstance(result, list) else []
            cacheable = bool(rows) and all(
                isinstance(row, dict) and row.get("quality") == "verified" and row.get("observed_at")
                and row.get("as_of") and str(row["as_of"]) <= as_of
                and validate_temporal_metadata(
                    {key: value for key, value in row.items() if key != "expires_at"},
                    latest_allowed_as_of=as_of,
                )["valid"] for row in rows
            )
            if provider.provider_id != "fixture" and cacheable:
                original_as_of = max(str(row["as_of"]) for row in rows)
                runtime.db.execute(
                    """INSERT INTO provider_last_good
                       (id, user_id, capability, subject, as_of, payload_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (new_id("last_good"), scope, capability, subject, original_as_of,
                     canonical_json(sanitize_context({"provider_id": provider.provider_id, "result": result})), now_iso()),
                )
            return provider, result
        except ProviderResultDegraded as error:
            degraded_result, degraded_provider = error.result, provider
        except Exception as error:
            if getattr(error, "code", "") in {"TASK_CANCELLED", "TASK_TIMEOUT", "STAGE_TIMEOUT", "TASK_EXPIRED"}:
                raise
            if provider.provider_id == "fixture":
                raise
            runtime.db.audit(task_id, "PROVIDER_CALL_FAILED", {
                "capability": capability, "provider_id": provider.provider_id,
                "reason_code": getattr(error, "code", type(error).__name__),
            }, user_id=scope)

    cached = runtime.db.fetchone(
        """SELECT payload_json, as_of FROM provider_last_good
           WHERE user_id=? AND capability=? AND subject=? AND as_of<=?
           ORDER BY as_of DESC, created_at DESC, id DESC LIMIT 1""",
        (scope, capability, subject, as_of),
    ) if runtime.settings.data_provider != "fixture" else None
    if cached:
        cached_payload = json.loads(cached["payload_json"])
        provider = next((item for item in runtime.providers.providers
                         if item.provider_id == cached_payload["provider_id"]), None)
        if provider:
            result = attach_provenance(cached_payload["result"], provider.provider_id, attempts)
            evaluation = datetime.fromisoformat(f"{as_of}T16:00:00+08:00")
            expiry_text = result.get("expires_at") if isinstance(result, dict) else None
            expiry = datetime.fromisoformat(expiry_text or f"{cached['as_of']}T23:59:59+08:00")
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            age = max(0, (evaluation - expiry).total_seconds())
            result = mark_last_good(result, age)
            return provider, result
    if degraded_provider is not None:
        return degraded_provider, attach_provenance(degraded_result, degraded_provider.provider_id, attempts)
    raise CapabilityUnavailable(f"CAPABILITY_UNAVAILABLE: {capability}")


def attach_provenance(result: Any, provider_id: str, attempts: list[dict]) -> Any:
    result = deepcopy(result)
    provenance = {
        "selected_provider_id": provider_id, "source_type": "provider",
        "fallback_used": len({item["provider_id"] for item in attempts}) > 1,
        "stale_age_seconds": 0, "coverage": None, "attempts": deepcopy(attempts),
    }
    if isinstance(result, dict):
        result.setdefault("provider_id", provider_id)
        provenance["coverage"] = result.get("field_completeness")
        provenance["snapshot_ids"] = [result["snapshot_id"]] if result.get("snapshot_id") else []
        result["provenance"] = provenance
    elif isinstance(result, list):
        result = [attach_provenance(item, provider_id, attempts) if isinstance(item, dict) else item for item in result]
    return result


def mark_last_good(result: Any, stale_age: float) -> Any:
    if isinstance(result, list):
        return [mark_last_good(item, stale_age) for item in result]
    if isinstance(result, dict):
        result["provenance"].update(
            source_type="last_good_snapshot", fallback_used=True, stale_age_seconds=stale_age,
        )
        if stale_age:
            result["quality"] = "stale"
    return result
