import io
import json
import ssl
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from llm import complete
from tools import CALCULATOR_DEFINITION


class LLMTests(unittest.TestCase):
    def setUp(self):
        config = json.dumps({"base_url": "https://example.invalid/v1/", "model": "test-model", "api_key": "test-key"})
        config_patch = patch("llm.Path.read_text", return_value=config)
        config_patch.start()
        self.addCleanup(config_patch.stop)
        env_patch = patch.dict("llm.os.environ", {"MOONSHOT_API_KEY": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def response(self):
        result = MagicMock()
        result.__enter__.return_value.read.return_value = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "结果", "reasoning": "provider field"}}],
        }).encode("utf-8")
        return result

    def test_payload_and_response(self):
        messages = [{"role": "user", "content": "计算"}]
        for tools in [None, [CALCULATOR_DEFINITION]]:
            with self.subTest(tools=bool(tools)):
                with patch("llm.urlopen", return_value=self.response()) as request:
                    message = complete(messages, tools=tools)
                sent = request.call_args.args[0]
                payload = json.loads(sent.data)
                self.assertEqual(sent.full_url, "https://example.invalid/v1/chat/completions")
                self.assertEqual(sent.get_header("Authorization"), "Bearer test-key")
                self.assertEqual(payload["messages"], messages)
                self.assertEqual(payload["model"], "test-model")
                self.assertEqual("tools" in payload, bool(tools))
                self.assertEqual(message["content"], "结果")
                self.assertEqual(message["reasoning"], "provider field")

    def test_http_error_is_not_blindly_retried(self):
        error = HTTPError("https://example.invalid", 429, "limit", {"Retry-After": "1"}, io.BytesIO(b'{"error":"limit"}'))
        with patch("llm.urlopen", side_effect=error) as request:
            with self.assertRaises(HTTPError):
                complete([])
        self.assertEqual(request.call_count, 1)

    def test_transient_tls_failure_retries_same_request(self):
        with patch("llm.urlopen", side_effect=[URLError(ssl.SSLEOFError("disconnect")), self.response()]) as request:
            with patch("llm.time.sleep") as sleep:
                self.assertEqual(complete([])["content"], "结果")
        self.assertEqual(request.call_count, 2)
        self.assertIs(request.call_args_list[0].args[0], request.call_args_list[1].args[0])
        sleep.assert_called_once_with(1)

    def test_tls_retry_has_limit(self):
        with patch("llm.urlopen", side_effect=URLError(ssl.SSLEOFError("disconnect"))) as request:
            with patch("llm.time.sleep"):
                with self.assertRaises(URLError):
                    complete([])
        self.assertEqual(request.call_count, 3)
