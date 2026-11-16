import json
import threading
import unittest
import urllib.error
from unittest.mock import patch

from pia_runtime.llm import (DeepSeekClient, GenerationEvent, LLMAuthenticationFailed, LLMEngineeringBudget,
                             LLMInvalidResponse, LLMProviderUnavailable, ModelRoute, ModelRouter)


class Response:
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self):
        return json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode()


class ModelFallbackTest(unittest.TestCase):
    def router(self):
        return ModelRouter([ModelRoute(name, DeepSeekClient("fake", f"https://{name}.invalid", name, retry_attempts=1),
                                       priority=index, allowed_data_classes=("market_public",))
                            for index, name in enumerate(["primary", "secondary"])])

    def test_transient_fallback_filters_private_payload_and_records_attempts(self):
        router = self.router()
        received = []
        def transport(request, **kwargs):
            received.append(json.loads(request.data))
            if len(received) == 1:
                raise urllib.error.URLError("offline")
            return Response()
        with patch("pia_runtime.llm.urllib.request.urlopen", side_effect=transport):
            result = router.generate_structured("system", {
                "market": {}, "portfolio": {"secret": "holdings"}, "confirmed_memories": ["private"], "unrecognized": "private",
                "rules": {"decision": "BLOCKED", "reasons": [{"code": "POSITION_LIMIT", "actual": {"holdings": "private"}}]},
            })
        self.assertEqual(result, {"ok": True})
        self.assertNotIn("portfolio", json.loads(received[1]["messages"][1]["content"]))
        self.assertNotIn("confirmed_memories", json.loads(received[1]["messages"][1]["content"]))
        self.assertNotIn("private", received[1]["messages"][1]["content"])
        self.assertEqual(len(router.request_context.attempts), 2)
        self.assertEqual(router.provider_id, "secondary")

    def test_authentication_and_stream_output_do_not_fallback(self):
        router = self.router()
        with patch.object(DeepSeekClient, "generate_structured", side_effect=LLMAuthenticationFailed("denied")) as call:
            with self.assertRaises(LLMAuthenticationFailed):
                router.generate_structured("system", {})
            self.assertEqual(call.call_count, 1)
        def stream(*args, **kwargs):
            yield GenerationEvent("delta", delta="{")
            raise LLMProviderUnavailable("interrupted")
        with patch.object(DeepSeekClient, "stream_structured", stream):
            events = router.stream_structured("system", {})
            self.assertEqual(next(events).delta, "{")
            with self.assertRaises(LLMProviderUnavailable):
                next(events)
            self.assertEqual(router.provider_id, "primary")

    def test_request_state_does_not_cross_threads(self):
        router = self.router()
        barrier = threading.Barrier(2)
        results = []
        def call(index):
            token = router.begin_request(str(index), str(index))
            try:
                barrier.wait()
                with patch.object(DeepSeekClient, "generate_structured", return_value={"ok": True}):
                    router.generate_structured("system", {})
                results.append(router.request_context.user_id)
            finally:
                router.end_request(token)
        threads = [threading.Thread(target=call, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
        self.assertEqual(sorted(results), ["0", "1"])

    def test_input_limit_prevents_http(self):
        with patch("pia_runtime.llm.urllib.request.urlopen") as transport:
            with self.assertRaises(LLMEngineeringBudget):
                self.router().generate_structured("system", {"rules": "x" * 40000})
            transport.assert_not_called()

    def test_each_http_attempt_refreshes_remaining_timeout(self):
        router = self.router()
        remaining = [45]
        token = router.begin_request("user", "task", lambda: remaining[0])
        timeouts = []
        def transport(request, timeout):
            timeouts.append(timeout)
            remaining[0] = 0.5
            if len(timeouts) == 1:
                raise urllib.error.URLError("offline")
            return Response()
        try:
            with patch("pia_runtime.llm.urllib.request.urlopen", side_effect=transport):
                router.generate_structured("system", {"market": {}})
            self.assertEqual(timeouts, [45, 0.5])
        finally:
            router.end_request(token)

    def test_invalid_json_is_not_retried_on_another_route(self):
        class InvalidResponse(Response):
            def read(self):
                return b"{invalid"
        with patch("pia_runtime.llm.urllib.request.urlopen", return_value=InvalidResponse()) as transport:
            with self.assertRaises(LLMInvalidResponse):
                self.router().generate_structured("system", {})
            self.assertEqual(transport.call_count, 1)
