import json
import threading
import urllib.error
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from pia_runtime.llm import (
    CredentialsRequired,
    DeepSeekClient,
    LLMAuthenticationFailed,
    LLMContentSafetyBlocked,
    ModelRoute,
    ModelRouter,
)


class _Response:
    def __init__(self, payload=None, lines=None):
        self.payload = payload
        self.lines = lines or []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

    def close(self):
        return None

    def __iter__(self):
        return iter(self.lines)


class DeepSeekClientTest(unittest.TestCase):
    def test_missing_credentials_are_explicit(self):
        client = DeepSeekClient(None, "https://example.test", "deepseek-flash")
        with self.assertRaises(CredentialsRequired):
            client.generate_json("system", {"ok": True})

    def test_model_router_selects_preferred_capable_route(self):
        first = DeepSeekClient("secret", "https://example.test", "deepseek-flash")
        second = DeepSeekClient("secret", "https://example.test", "other-model")
        router = ModelRouter(
            [
                ModelRoute("other", second, priority=1),
                ModelRoute("deepseek", first, priority=10),
            ],
            preferred_provider_id="deepseek",
        )

        self.assertEqual(router.provider_id, "deepseek")
        self.assertEqual(router.model, "deepseek-flash")
        self.assertTrue({"structured_output", "streaming", "tool_calls"}.issubset(router.capabilities()))

    def test_http_errors_are_mapped_to_stable_codes(self):
        client = DeepSeekClient(
            "secret",
            "https://example.test",
            "deepseek-flash",
            retry_attempts=1,
        )
        unauthorized = urllib.error.HTTPError(
            "https://example.test/chat/completions",
            401,
            "unauthorized",
            {},
            _Response({"error": {"message": "bad key"}}),
        )
        with patch("pia_runtime.llm.urllib.request.urlopen", side_effect=unauthorized):
            with self.assertRaises(LLMAuthenticationFailed):
                client.generate_json("system", {"ok": True})
        unauthorized.close()

        safety = urllib.error.HTTPError(
            "https://example.test/chat/completions",
            400,
            "blocked",
            {},
            _Response({"error": {"message": "content safety policy"}}),
        )
        with patch("pia_runtime.llm.urllib.request.urlopen", side_effect=safety):
            with self.assertRaises(LLMContentSafetyBlocked):
                client.generate_json("system", {"ok": True})
        safety.close()

    def test_structured_request_supports_tools_and_usage(self):
        response = _Response({
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"total_tokens": 12},
        })
        tools = [{
            "type": "function",
            "function": {
                "name": "get_market_snapshot",
                "parameters": {"type": "object"},
            },
        }]
        client = DeepSeekClient("secret", "https://example.test", "deepseek-flash")
        with patch("pia_runtime.llm.urllib.request.urlopen", return_value=response) as mocked:
            result = client.generate_structured("system", {"ok": True}, tools=tools)

        request = mocked.call_args.args[0]
        body = json.loads(request.data.decode())
        self.assertEqual(result, {"ok": True})
        self.assertEqual(body["tools"], tools)
        self.assertEqual(client.last_usage["total_tokens"], 12)

    def test_http_transport_uses_bearer_and_decodes_compatible_response(self):
        received: list[tuple[str, str | None, dict[str, object]]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode())
                received.append((
                    self.path,
                    self.headers.get("Authorization"),
                    payload,
                ))
                body = json.dumps({
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "usage": {"total_tokens": 9},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = DeepSeekClient(
                "local-secret",
                f"http://127.0.0.1:{server.server_port}",
                "deepseek-flash",
            )
            result = client.generate_json("system", {"ok": True})
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertEqual(result, {"ok": True})
        self.assertEqual(client.last_usage["total_tokens"], 9)
        self.assertEqual(received[0][0], "/chat/completions")
        self.assertEqual(received[0][1], "Bearer local-secret")
        self.assertEqual(received[0][2]["model"], "deepseek-flash")

    def test_transient_json_request_retries_with_backoff(self):
        response = _Response({
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"total_tokens": 3},
        })
        delays = []
        client = DeepSeekClient(
            "secret",
            "https://example.test",
            "deepseek-flash",
            retry_attempts=2,
            retry_backoff_seconds=0.2,
            sleep=delays.append,
        )
        with patch(
            "pia_runtime.llm.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("temporary"), response],
        ):
            self.assertEqual(client.generate_json("system", {"ok": True}), {"ok": True})
        self.assertEqual(delays, [0.2])

    def test_stream_retries_before_first_delta(self):
        response = _Response(lines=[
            b'data: {"choices":[{"delta":{"content":"{\\"ok\\": true}"}}]}',
            b"data: [DONE]",
        ])
        delays = []
        client = DeepSeekClient(
            "secret",
            "https://example.test",
            "deepseek-flash",
            retry_attempts=2,
            retry_backoff_seconds=0.1,
            sleep=delays.append,
        )
        with patch(
            "pia_runtime.llm.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("temporary"), response],
        ):
            events = list(client.stream_structured("system", {"ok": True}))
        self.assertEqual(events[-1].result, {"ok": True})
        self.assertEqual(delays, [0.1])

    def test_stream_structured_yields_deltas_and_final_json(self):
        response = _Response(lines=[
            b'data: {"choices":[{"delta":{"content":"{\\"ok\\":"}}]}',
            b'data: {"choices":[{"delta":{"content":" true}"}}]}',
            b'data: {"usage":{"total_tokens":7},"choices":[{"delta":{}}]}',
            b"data: [DONE]",
        ])
        client = DeepSeekClient("secret", "https://example.test", "deepseek-flash")
        with patch("pia_runtime.llm.urllib.request.urlopen", return_value=response) as mocked:
            events = list(client.stream_structured("system", {"ok": True}))

        body = json.loads(mocked.call_args.args[0].data.decode())
        self.assertTrue(body["stream"])
        self.assertEqual([event.delta for event in events if event.kind == "delta"], ['{"ok":', " true}"])
        self.assertEqual(events[-1].result, {"ok": True})
        self.assertEqual(client.last_usage["total_tokens"], 7)

    def test_tool_call_loop_executes_and_returns_final_json(self):
        first = _Response({
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_market_snapshot",
                            "arguments": '{"as_of":"2026-11-06"}',
                        },
                    }],
                },
            }],
            "usage": {"total_tokens": 4},
        })
        second = _Response({
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"total_tokens": 8},
        })
        client = DeepSeekClient("secret", "https://example.test", "deepseek-flash")
        with patch(
            "pia_runtime.llm.urllib.request.urlopen",
            side_effect=[first, second],
        ) as mocked:
            calls = []
            result = client.generate_with_tools(
                "system",
                {"ok": True},
                [{"type": "function", "function": {"name": "get_market_snapshot"}}],
                lambda name, args: calls.append((name, args)) or {"breadth": 0.5},
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, [("get_market_snapshot", {"as_of": "2026-11-06"})])
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(client.last_usage["total_tokens"], 12)
        self.assertEqual(len(client.usage_history), 2)

    def test_streaming_tool_call_loop_executes_and_returns_final_json(self):
        first = _Response(lines=[
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"get_market_snapshot","arguments":"{\\"as_of\\":\\"2026-11-06\\"}"}}]}}]}',
            b"data: [DONE]",
        ])
        second = _Response(lines=[
            b'data: {"choices":[{"delta":{"content":"{\\"ok\\": true}"}}]}',
            b"data: [DONE]",
        ])
        client = DeepSeekClient("secret", "https://example.test", "deepseek-flash")
        with patch(
            "pia_runtime.llm.urllib.request.urlopen",
            side_effect=[first, second],
        ) as mocked:
            calls = []
            events = list(client.stream_with_tools(
                "system",
                {"ok": True},
                [{"type": "function", "function": {"name": "get_market_snapshot"}}],
                lambda name, args: calls.append((name, args)) or {"breadth": 0.5},
            ))

        self.assertEqual(events[-1].result, {"ok": True})
        self.assertEqual(calls, [("get_market_snapshot", {"as_of": "2026-11-06"})])
        self.assertEqual(mocked.call_count, 2)


if __name__ == "__main__":
    unittest.main()
