import unittest

from gateway.model import normalize_model
from gateway.response import map_usage_limit_404, parse_final_response


class GatewayMigrationTests(unittest.TestCase):
    def test_normalize_model(self):
        self.assertEqual(normalize_model("gpt-5-codex-mini"), "gpt-5.1-codex-mini")
        self.assertEqual(normalize_model("gpt-5-codex"), "gpt-5.1-codex")
        self.assertEqual(normalize_model("gpt-5.2"), "gpt-5.2")

    def test_parse_final_response(self):
        sse = "\n".join([
            'data: {"type":"response.output_text.delta","delta":"hi"}',
            'data: {"type":"response.done","response":{"id":"resp_1"}}',
            "",
        ])
        self.assertEqual(parse_final_response(sse), {"id": "resp_1"})

    def test_map_usage_limit(self):
        status, body = map_usage_limit_404(404, '{"error":{"code":"usage_limit_exceeded"}}')
        self.assertEqual(status, 429)
        self.assertEqual(body, '{"error":{"code":"usage_limit_exceeded"}}')


if __name__ == "__main__":
    unittest.main()
