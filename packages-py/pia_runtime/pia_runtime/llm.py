from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from contextvars import ContextVar
from copy import copy, deepcopy
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Iterator
from .models import new_id


class LLMError(RuntimeError):
    """Provider-neutral LLM failure with a stable task-facing error code."""

    code = "LLM_PROVIDER_ERROR"
    retryable = False

    def __init__(self, message: str, *, provider_id: str = "unknown") -> None:
        super().__init__(message)
        self.provider_id = provider_id


class CredentialsRequired(LLMError):
    code = "CREDENTIALS_REQUIRED"


class LLMRateLimited(LLMError):
    code = "LLM_RATE_LIMITED"
    retryable = True


class LLMProviderUnavailable(LLMError):
    code = "LLM_PROVIDER_UNAVAILABLE"
    retryable = True


class LLMAuthenticationFailed(LLMError):
    code = "LLM_AUTHENTICATION_FAILED"


class LLMContentSafetyBlocked(LLMError):
    code = "LLM_CONTENT_SAFETY_BLOCKED"


class LLMInvalidResponse(LLMError):
    code = "LLM_INVALID_RESPONSE"


class LLMEngineeringBudget(LLMError):
    code = "TOKEN_BUDGET_EXCEEDED"


@dataclass
class GenerationRequestContext:
    user_id: str = "default"
    task_id: str = "standalone"
    request_id: str = field(default_factory=lambda: new_id("generation"))
    attempts: list[dict] = field(default_factory=list)
    max_http_attempts: int = 6
    exposed: bool = False
    tool_calls: int = 0
    check: Any = None
    ledger: Any = None
    route: Any = None
    current_attempt: dict | None = None
    omitted: list[str] = field(default_factory=list)

    def before_http(self, request):
        remaining = self.check() if self.check else 45
        if len(self.attempts) >= self.max_http_attempts:
            raise LLMEngineeringBudget("LLM_HTTP_ATTEMPT_LIMIT")
        if len(request.data or b"") > 32768:
            raise LLMEngineeringBudget("LLM_INPUT_BYTES_EXCEEDED")
        attempt_id = self.ledger.reserve(self, self.route, len(request.data or b"")) if self.ledger else new_id("llm_attempt")
        row = {"request_id": self.request_id, "attempt_id": attempt_id,
               "route_id": self.route.route_id or self.route.provider_id,
               "provider_id": self.route.provider_id, "model": self.route.model,
               "usage": None, "cost_status": "unknown"}
        self.attempts.append(row)
        self.current_attempt = row
        return min(45, max(0.001, remaining)) if isinstance(remaining, (int, float)) else 45

    def finish_http(self, usage=None, error=None):
        row = self.current_attempt
        if row is None:
            return
        row["usage"] = usage
        row["reason_code"] = getattr(error, "code", type(error).__name__) if error else None
        if self.ledger:
            self.ledger.settle(row["attempt_id"], usage, row["reason_code"])
            row["cost_status"] = self.ledger.db.fetchone(
                "SELECT cost_status FROM llm_attempts WHERE id=?", (row["attempt_id"],),
            )["cost_status"]
        self.current_attempt = None


_request_context: ContextVar[GenerationRequestContext | None] = ContextVar("generation_request", default=None)


@dataclass(slots=True)
class GenerationEvent:
    kind: str
    delta: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """A model endpoint that can satisfy a set of structured task capabilities."""

    provider_id: str
    client: Any
    priority: int = 100
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    route_id: str = ""
    allowed_data_classes: tuple[str, ...] = ("market_public", "portfolio", "confirmed_memory")
    token_upper_bound: str | None = None
    declared_capabilities: tuple[str, ...] | None = None

    @property
    def model(self) -> str:
        return str(getattr(self.client, "model", self.provider_id))

    def capabilities(self) -> set[str]:
        actual = set(self.client.capabilities())
        return actual if self.declared_capabilities is None else actual & set(self.declared_capabilities)


class ModelRouter:
    """Select a capable model while preserving one provider contract."""

    def __init__(
        self,
        routes: list[ModelRoute],
        *,
        preferred_provider_id: str | None = None,
        ledger=None, max_routes=2, max_http_attempts=6,
    ) -> None:
        self.routes = list(routes)
        self.preferred_provider_id = preferred_provider_id
        self._state: ContextVar[dict | None] = ContextVar(f"router_{id(self)}", default=None)
        self.ledger, self.max_routes, self.max_http_attempts = ledger, max_routes, max_http_attempts

    def begin_request(self, user_id, task_id, check=None):
        context = GenerationRequestContext(user_id=user_id, task_id=task_id, check=check,
                                           ledger=self.ledger, max_http_attempts=self.max_http_attempts)
        token = _request_context.set(context)
        self._state.set({"context": context})
        return token

    def end_request(self, token):
        _request_context.reset(token)

    @property
    def request_context(self):
        return (self._state.get() or {}).get("context")

    @property
    def active_route(self) -> ModelRoute:
        return (self._state.get() or {}).get("route") or self._select({"structured_output"})

    @property
    def provider_id(self) -> str:
        return self.active_route.provider_id

    @property
    def model(self) -> str:
        return self.active_route.model

    @property
    def last_usage(self) -> dict[str, Any] | None:
        state = self._state.get() or {}
        if "usage" in state:
            return state["usage"]
        return None

    @last_usage.setter
    def last_usage(self, value: dict[str, Any] | None) -> None:
        state = dict(self._state.get() or {})
        state["usage"] = value
        self._state.set(state)

    @property
    def usage_history(self) -> list[dict[str, Any]]:
        return list((self._state.get() or {}).get("history", []))

    @usage_history.setter
    def usage_history(self, value: list[dict[str, Any]]) -> None:
        state = dict(self._state.get() or {})
        state["history"] = list(value)
        self._state.set(state)

    def capabilities(self) -> set[str]:
        result: set[str] = set()
        for route in self.routes:
            result.update(route.capabilities())
        return result

    def health(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for route in sorted(self.routes, key=lambda item: (item.priority, item.provider_id)):
            health = getattr(route.client, "health", None)
            payload = health() if callable(health) else {}
            rows.append({
                "provider_id": route.provider_id,
                "model": route.model,
                "priority": route.priority,
                "capabilities": sorted(route.capabilities()),
                "status": payload.get("status", "configured"),
                "credentials_configured": payload.get(
                    "credentials_configured",
                    bool(
                        getattr(route.client, "api_key", None)
                        and not str(getattr(route.client, "api_key", "")).startswith("__")
                    ),
                ),
            })
        return rows

    def generate_structured(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._generate("generate_structured", {"structured_output"}, args, kwargs)

    def stream_structured(self, *args: Any, **kwargs: Any) -> Iterator[GenerationEvent]:
        yield from self._stream("stream_structured", {"structured_output", "streaming"}, args, kwargs)

    def generate_with_tools(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._generate("generate_with_tools", {"structured_output", "tool_calls"}, args, kwargs)

    def stream_with_tools(self, *args: Any, **kwargs: Any) -> Iterator[GenerationEvent]:
        yield from self._stream("stream_with_tools", {"structured_output", "tool_calls", "streaming"}, args, kwargs)

    def _candidates(self, required):
        candidates = [route for route in self.routes if required <= route.capabilities()
                      and "market_public" in route.allowed_data_classes]
        eligible = [route for route in candidates if not self.ledger or self.ledger.route_allowed(route)]
        if candidates and not eligible:
            from .llm_budget import BudgetExceeded
            raise BudgetExceeded("COST_BOUND_UNAVAILABLE")
        return sorted(eligible,
                      key=lambda route: (route.provider_id != self.preferred_provider_id if self.preferred_provider_id else False,
                                         route.priority, route.route_id or route.provider_id))[:self.max_routes]

    def _prepare(self, route, args, context):
        client = copy(route.client)
        if isinstance(client, DeepSeekClient):
            client.last_usage, client.usage_history = None, []
            if context.check:
                # Runtime supplies the remaining monotonic stage budget.
                timeout = context.check()
                if isinstance(timeout, (int, float)):
                    client.timeout = min(45, max(0.001, timeout))
        routed = list(args)
        if len(routed) > 1 and isinstance(routed[1], dict):
            allowed = {"market", "rules", "evidence_ids", "pack_id"}
            if "portfolio" in route.allowed_data_classes:
                allowed.add("portfolio")
            if "confirmed_memory" in route.allowed_data_classes:
                allowed.add("confirmed_memories")
            payload = {key: deepcopy(value) for key, value in routed[1].items()
                       if key in allowed}
            if "portfolio" not in route.allowed_data_classes and isinstance(payload.get("rules"), dict):
                rule_result = payload["rules"]
                payload["rules"] = {
                    "decision": rule_result.get("decision"), "rule_snapshot_id": rule_result.get("rule_snapshot_id"),
                    "reason_codes": [item.get("code") for item in rule_result.get("reasons", [])],
                    "warning_codes": [item.get("code") for item in rule_result.get("warnings", [])],
                }
            for key in ["confirmed_memories", "market.daily_bars", "market.instruments", "market.sectors"]:
                if len(json.dumps(payload, ensure_ascii=False).encode()) + len(str(args[0]).encode()) < 28000:
                    break
                if "." in key:
                    parent, field_name = key.split(".")
                    if isinstance(payload.get(parent), dict) and field_name in payload[parent]:
                        payload[parent].pop(field_name)
                        context.omitted.append(key)
                elif key in payload:
                    payload.pop(key)
                    context.omitted.append(key)
            routed[1] = payload
        if len(routed) > 2 and isinstance(routed[2], list) and "portfolio" not in route.allowed_data_classes:
            routed[2] = [tool for tool in routed[2] if tool.get("function", {}).get("name") != "get_portfolio_snapshot"]
        if len(routed) > 3 and callable(routed[3]):
            executor = routed[3]
            def guarded_tool(name, arguments):
                if name == "get_portfolio_snapshot" and "portfolio" not in route.allowed_data_classes:
                    raise LLMError("LLM_DATA_CLASS_NOT_AUTHORIZED", provider_id=route.provider_id)
                if context.check:
                    context.check()
                context.tool_calls += 1
                if context.tool_calls > 8:
                    raise LLMEngineeringBudget("LLM_TOOL_CALL_LIMIT")
                context.exposed = True
                return executor(name, arguments)
            routed[3] = guarded_tool
        context.route = route
        state = dict(self._state.get() or {})
        state.update(route=route, context=context)
        self._state.set(state)
        return client, tuple(routed)

    def _capture(self, client, context):
        histories = [attempt["usage"] for attempt in context.attempts if attempt.get("usage")]
        if histories:
            self.last_usage = {key: sum(_usage.get(key, 0) for _usage in histories)
                               for key in {"prompt_tokens", "completion_tokens", "total_tokens"}}
            self.usage_history = histories
        else:
            self.last_usage = getattr(client, "last_usage", None)
            self.usage_history = list(getattr(client, "usage_history", []))

    def _generate(self, method, required, args, kwargs):
        own = _request_context.get() is None
        token = self.begin_request("default", "standalone") if own else None
        context = _request_context.get()
        try:
            candidates = self._candidates(required)
            if not candidates:
                raise LLMProviderUnavailable("LLM_CAPABILITY_UNAVAILABLE")
            for index, route in enumerate(candidates):
                client, routed = self._prepare(route, args, context)
                try:
                    result = getattr(client, method)(*routed, **kwargs)
                    if not isinstance(result, dict):
                        raise LLMInvalidResponse("LLM response must be a JSON object", provider_id=route.provider_id)
                    return result
                except (LLMRateLimited, LLMProviderUnavailable):
                    if context.exposed or index + 1 == len(candidates):
                        raise
                finally:
                    self._capture(client, context)
        finally:
            if token:
                self.end_request(token)

    def _stream(self, method, required, args, kwargs):
        own = _request_context.get() is None
        token = self.begin_request("default", "standalone") if own else None
        context = _request_context.get()
        try:
            candidates = self._candidates(required)
            if not candidates:
                raise LLMProviderUnavailable("LLM_CAPABILITY_UNAVAILABLE")
            for index, route in enumerate(candidates):
                client, routed = self._prepare(route, args, context)
                try:
                    for event in getattr(client, method)(*routed, **kwargs):
                        if event.kind == "delta" and (event.delta or event.tool_calls):
                            context.exposed = True
                        yield event
                    return
                except (LLMRateLimited, LLMProviderUnavailable):
                    if context.exposed or index + 1 == len(candidates):
                        raise
                finally:
                    self._capture(client, context)
        finally:
            if token:
                self.end_request(token)

    def _select(self, required: set[str]) -> ModelRoute:
        candidates = [
            route for route in self.routes
            if required.issubset(route.capabilities())
        ]
        candidates.sort(
            key=lambda route: (
                route.provider_id != self.preferred_provider_id
                if self.preferred_provider_id
                else False,
                route.priority,
                route.provider_id,
            )
        )
        if not candidates:
            raise LLMProviderUnavailable(
                f"No configured LLM provider supports: {', '.join(sorted(required))}",
                provider_id=self.preferred_provider_id or "router",
            )
        return candidates[0]


@dataclass(slots=True)
class DeepSeekClient:
    api_key: str | None
    base_url: str
    model: str
    timeout: int = 45
    retry_attempts: int = 2
    retry_backoff_seconds: float = 0.25
    retry_max_backoff_seconds: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    on_retry: Callable[..., None] | None = None
    last_usage: dict[str, Any] | None = field(default=None, init=False)
    usage_history: list[dict[str, Any]] = field(default_factory=list, init=False)

    def capabilities(self) -> set[str]:
        return {"structured_output", "streaming", "tool_calls", "token_usage"}

    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.generate_json(system_prompt, user_payload, tools=tools)

    def generate_with_tools(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        *,
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        """Run a bounded tool-call loop before returning structured JSON."""
        self._require_credentials()
        self._begin_usage()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        tool_count = 0
        for round_index in range(min(3, max(1, max_rounds))):
            payload = self._request_json(
                self._request(self._request_body(messages=messages, tools=tools))
            )
            self._record_usage(payload.get("usage"))
            message = ((payload.get("choices") or [{}])[0]).get("message") or {}
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return self._decode_response(payload)
            tool_count += len(tool_calls)
            if tool_count > 8 or round_index >= 2:
                raise LLMEngineeringBudget("LLM_TOOL_BUDGET_EXCEEDED")
            messages.append({
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            })
            for index, call in enumerate(tool_calls):
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError as error:
                    raise RuntimeError(f"DeepSeek tool arguments are invalid: {name}") from error
                result = tool_executor(name, arguments)
                context = _request_context.get()
                if context:
                    context.exposed = True
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"tool_{index}",
                    "content": json.dumps(result, ensure_ascii=False),
                })
        raise RuntimeError("DeepSeek tool-call loop exceeded its limit")

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._require_credentials()
        self._begin_usage()
        payload = self._request_json(
            self._request(
                self._request_body(
                    system_prompt,
                    user_payload,
                    tools=tools,
                )
            )
        )
        self._record_usage(payload.get("usage"))
        return self._decode_response(payload)

    def stream_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[GenerationEvent]:
        """Yield OpenAI-compatible SSE deltas and a final structured result."""
        self._require_credentials()
        self._begin_usage()
        yield from self._stream_messages(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            tools,
        )

    def stream_with_tools(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        *,
        max_rounds: int = 3,
    ) -> Iterator[GenerationEvent]:
        """Stream model deltas while supporting bounded tool-call rounds."""
        self._require_credentials()
        self._begin_usage()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        tool_count = 0
        for round_index in range(min(3, max(1, max_rounds))):
            completed: GenerationEvent | None = None
            for event in self._stream_messages(messages, tools):
                if event.kind == "completed":
                    completed = event
                yield event
            result = (completed.result if completed else None) or {}
            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                return
            tool_count += len(tool_calls)
            if tool_count > 8 or round_index >= 2:
                raise LLMEngineeringBudget("LLM_TOOL_BUDGET_EXCEEDED")
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls,
            })
            for index, call in enumerate(tool_calls):
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError as error:
                    raise RuntimeError(f"DeepSeek tool arguments are invalid: {name}") from error
                tool_result = tool_executor(name, arguments)
                context = _request_context.get()
                if context:
                    context.exposed = True
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"tool_{index}",
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })
        raise RuntimeError("DeepSeek streaming tool-call loop exceeded its limit")

    def _stream_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Iterator[GenerationEvent]:
        content_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        request = self._request(
            self._request_body(messages=messages, tools=tools, stream=True)
        )
        attempts = max(1, int(self.retry_attempts))
        for attempt in range(attempts):
            emitted = False
            content_parts = []
            tool_calls = {}
            try:
                context = _request_context.get()
                round_usage = None
                timeout = min(self.timeout, context.before_http(request)) if context else self.timeout
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    for line in _response_lines(response):
                        if context and context.check:
                            context.check()
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        if raw == "[DONE]":
                            break
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError as error:
                            raise LLMInvalidResponse("DeepSeek stream returned invalid JSON") from error
                        choice = (payload.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        text = str(delta.get("content") or "")
                        new_tool_calls = delta.get("tool_calls") or []
                        if text:
                            content_parts.append(text)
                        for call in new_tool_calls:
                            index = int(call.get("index", len(tool_calls)))
                            current = tool_calls.setdefault(index, {
                                "id": call.get("id") or f"tool_{index}",
                                "type": call.get("type") or "function",
                                "function": {"name": "", "arguments": ""},
                            })
                            function = call.get("function") or {}
                            if function.get("name"):
                                current["function"]["name"] = function["name"]
                            if function.get("arguments"):
                                current["function"]["arguments"] += str(function["arguments"])
                        usage = payload.get("usage")
                        if usage:
                            round_usage = usage
                            self._record_usage(usage)
                        if text or new_tool_calls:
                            emitted = True
                            if context:
                                context.exposed = True
                            yield GenerationEvent(
                                kind="delta",
                                delta=text,
                                tool_calls=new_tool_calls,
                                usage=usage,
                            )
                if context:
                    context.finish_http(round_usage)
            except Exception as error:
                if context:
                    context.finish_http(round_usage, error)
                if (
                    _is_retryable_llm_error(error)
                    and not emitted
                    and not (context and context.exposed)
                    and attempt + 1 < attempts
                ):
                    delay = min(
                        max(self.retry_backoff_seconds, self.retry_max_backoff_seconds),
                        max(0.0, self.retry_backoff_seconds) * (2**attempt),
                    )
                    self._notify_retry(
                        method="stream",
                        attempt=attempt + 1,
                        delay_seconds=delay,
                        error=error,
                    )
                    self.sleep(delay)
                    continue
                raise _map_llm_error(
                    error,
                    provider_id="deepseek",
                    operation="stream",
                ) from error
            break

        result: dict[str, Any] = {}
        if content_parts:
            try:
                result = json.loads("".join(content_parts))
            except json.JSONDecodeError as error:
                raise LLMInvalidResponse("LLM stream did not produce valid JSON") from error
        if not isinstance(result, dict):
            raise LLMInvalidResponse("LLM stream must produce a JSON object")
        if tool_calls:
            result["tool_calls"] = [tool_calls[index] for index in sorted(tool_calls)]
        yield GenerationEvent(kind="completed", result=result, usage=self.last_usage)

    def _require_credentials(self) -> None:
        if not self.api_key or self.api_key.startswith("__"):
            raise CredentialsRequired(
                "DeepSeek API key is not available in the local runtime.",
                provider_id="deepseek",
            )

    def _begin_usage(self) -> None:
        self.last_usage = None
        self.usage_history = []

    def _record_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        normalized = {
            str(key): value
            for key, value in usage.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        if not normalized:
            return
        self.usage_history.append(dict(normalized))
        total: dict[str, Any] = {}
        for entry in self.usage_history:
            for key, value in entry.items():
                total[key] = total.get(key, 0) + value
        if "total_tokens" not in total:
            total["total_tokens"] = (
                total.get("prompt_tokens", 0)
                + total.get("completion_tokens", 0)
            )
        self.last_usage = total

    def _request_body(
        self,
        system_prompt: str | None = None,
        user_payload: dict[str, Any] | None = None,
        *,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages or [
                {"role": "system", "content": system_prompt or ""},
                {"role": "user", "content": json.dumps(user_payload or {}, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_tokens": 1024,
        }
        if tools:
            body["tools"] = tools
        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        if len(json.dumps(body).encode()) > 32768:
            raise LLMEngineeringBudget("LLM_INPUT_BYTES_EXCEEDED")
        return body

    def _request(self, body: dict[str, Any]) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def _request_json(self, request: urllib.request.Request) -> dict[str, Any]:
        attempts = max(1, int(self.retry_attempts))
        for attempt in range(attempts):
            context = _request_context.get()
            try:
                timeout = min(self.timeout, context.before_http(request)) if context else self.timeout
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode())
                if context:
                    context.finish_http(payload.get("usage"))
                    if context.check:
                        context.check()
                return payload
            except Exception as error:
                if context:
                    context.finish_http(error=error)
                if _is_retryable_llm_error(error) and not (context and context.exposed) and attempt + 1 < attempts:
                    delay = min(
                        max(self.retry_backoff_seconds, self.retry_max_backoff_seconds),
                        max(0.0, self.retry_backoff_seconds) * (2**attempt),
                    )
                    self._notify_retry(
                        method="json",
                        attempt=attempt + 1,
                        delay_seconds=delay,
                        error=error,
                    )
                    self.sleep(delay)
                    continue
                raise _map_llm_error(
                    error,
                    provider_id="deepseek",
                    operation="request",
                ) from error

    def _notify_retry(
        self,
        *,
        method: str,
        attempt: int,
        delay_seconds: float,
        error: BaseException,
    ) -> None:
        if self.on_retry is not None:
            self.on_retry(
                method=method,
                attempt=attempt,
                delay_seconds=delay_seconds,
                error=error,
            )

    def _decode_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if content:
            try:
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise LLMInvalidResponse("LLM response must be a JSON object")
                return result
            except json.JSONDecodeError as error:
                raise LLMInvalidResponse(
                    "DeepSeek response did not contain valid JSON",
                    provider_id="deepseek",
                ) from error
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            return {"tool_calls": tool_calls}
        raise LLMInvalidResponse(
            "DeepSeek response did not contain content or tool calls",
            provider_id="deepseek",
        )


def _response_lines(response: Any) -> Iterator[str]:
    """Read SSE lines from real responses and small test doubles."""
    try:
        iterator = iter(response)
    except TypeError:
        iterator = iter(response.read().splitlines())
    for line in iterator:
        if isinstance(line, bytes):
            yield line.decode().strip()
        else:
            yield str(line).strip()


def _is_retryable_llm_error(error: BaseException) -> bool:
    if isinstance(error, LLMError):
        return isinstance(error, (LLMRateLimited, LLMProviderUnavailable))
    if getattr(error, "code", None):
        return False
    if isinstance(error, urllib.error.HTTPError):
        return error.code in {408, 425, 429} or 500 <= error.code < 600
    if isinstance(error, (TimeoutError, ConnectionError, OSError, urllib.error.URLError)):
        return True
    return False


def _map_llm_error(
    error: BaseException,
    *,
    provider_id: str,
    operation: str,
) -> LLMError:
    """Map transport/provider failures to stable, auditable domain errors."""
    if isinstance(error, LLMError):
        return error
    if isinstance(error, (json.JSONDecodeError, UnicodeDecodeError)):
        return LLMInvalidResponse(f"{provider_id} {operation} returned invalid JSON", provider_id=provider_id)
    if getattr(error, "code", "") in {"TASK_TIMEOUT", "TASK_CANCELLED", "STAGE_TIMEOUT", "TASK_EXPIRED", "COST_BUDGET_EXCEEDED"}:
        return error
    if isinstance(error, urllib.error.HTTPError):
        body = ""
        try:
            body = error.read().decode(errors="replace")
        except Exception:
            body = ""
        message = body or str(error)
        lowered = message.lower()
        if error.code == 429:
            return LLMRateLimited(
                f"{provider_id} {operation} was rate limited",
                provider_id=provider_id,
            )
        if error.code in {401, 403}:
            return LLMAuthenticationFailed(
                f"{provider_id} authentication failed",
                provider_id=provider_id,
            )
        if any(
            marker in lowered
            for marker in (
                "content safety",
                "content_filter",
                "safety system",
                "sensitive content",
            )
        ):
            return LLMContentSafetyBlocked(
                f"{provider_id} rejected the request for content safety",
                provider_id=provider_id,
            )
        if error.code in {408, 425} or 500 <= error.code < 600:
            return LLMProviderUnavailable(
                f"{provider_id} is temporarily unavailable",
                provider_id=provider_id,
            )
        return LLMError(
            f"{provider_id} {operation} failed with HTTP {error.code}",
            provider_id=provider_id,
        )
    if _is_retryable_llm_error(error):
        return LLMProviderUnavailable(
            f"{provider_id} {operation} failed temporarily",
            provider_id=provider_id,
        )
    return LLMError(
        f"{provider_id} {operation} failed",
        provider_id=provider_id,
    )
