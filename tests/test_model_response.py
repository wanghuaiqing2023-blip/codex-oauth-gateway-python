import unittest

from gateway.model import normalize_model, requested_model
from gateway.response import map_usage_limit_404, parse_final_response


class GatewayMigrationTests(unittest.TestCase):
    def test_requested_model_is_forwarded_without_normalization(self):
        self.assertEqual(requested_model("gpt-5-codex-mini"), "gpt-5-codex-mini")
        self.assertEqual(requested_model("gpt-5-codex"), "gpt-5-codex")
        self.assertEqual(requested_model("vendor/future-model"), "vendor/future-model")
        self.assertIsNone(requested_model(None))

    def test_normalize_model_wrapper_is_passthrough(self):
        self.assertEqual(normalize_model("codex-mini-latest"), "codex-mini-latest")
        self.assertIsNone(normalize_model(None))

    def test_parse_final_response(self):
        sse = "\n".join([
            'data: {"type":"response.output_text.delta","delta":"hi"}',
            'data: {"type":"response.done","response":{"id":"resp_1"}}',
            "",
        ])
        self.assertEqual(
            parse_final_response(sse),
            {
                "id": "resp_1",
                "output_text": "hi",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hi"}],
                    }
                ],
            },
        )

    def test_parse_final_response_preserves_existing_output(self):
        sse = "\n".join([
            'data: {"type":"response.output_text.delta","delta":"hi"}',
            'data: {"type":"response.done","response":{"id":"resp_1","output":[{"type":"message"}]}}',
            "",
        ])
        self.assertEqual(
            parse_final_response(sse),
            {"id": "resp_1", "output": [{"type": "message"}]},
        )

    def test_parse_final_response_uses_output_item_done(self):
        sse = "\n".join([
            'data: {"type":"response.output_item.done","item":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hi\\n"}]}}',
            'data: {"type":"response.completed","response":{"id":"resp_1","output":[]}}',
            "",
        ])
        self.assertEqual(
            parse_final_response(sse),
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hi\n"}],
                    }
                ],
                "output_text": "hi\n",
            },
        )

    def test_parse_final_response_applies_openai_semantics(self):
        sse = "\n".join([
            'data: {"type":"response.done","response":{"id":"resp_1","output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hi"}]}],"usage":{"total_tokens":3}}}',
            "",
        ])
        self.assertEqual(
            parse_final_response(sse, default_model="gpt-5.1-codex", openai_compatible=True),
            {
                "id": "resp_1",
                "object": "response",
                "model": "gpt-5.1-codex",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hi"}],
                    }
                ],
                "output_text": "hi",
                "usage": {"total_tokens": 3},
            },
        )

    def test_map_usage_limit(self):
        status, body = map_usage_limit_404(404, '{"error":{"code":"usage_limit_exceeded"}}')
        self.assertEqual(status, 429)
        self.assertEqual(body, '{"error":{"code":"usage_limit_exceeded"}}')


if __name__ == "__main__":
    unittest.main()
