import base64
import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from gateway import auth, server
from gateway.server import GatewayHandler


def _jwt_with_account(account_id: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"https://api.openai.com/auth": {"chatgpt_account_id": account_id}}).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    return f"a.{payload}.c"


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), GatewayHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.05)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=1)

    def test_health_and_validation_error_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "openai.json"
            token_file.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": _jwt_with_account("acct_test"),
                        "refresh": "refresh_1",
                        "expires": int(time.time() * 1000) + 3600 * 1000,
                    }
                ),
                encoding="utf-8",
            )

            original_auth_token_file = auth.TOKEN_FILE
            original_server_token_file = server.TOKEN_FILE
            auth.TOKEN_FILE = token_file
            server.TOKEN_FILE = token_file
            try:
                conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
                conn.request("GET", "/health")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertTrue(payload["authenticated"])
                conn.close()

                conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
                conn.request("POST", "/responses", body=b'{"model":"gpt-5.1-codex"}', headers={"content-type": "application/json"})
                response = conn.getresponse()
                self.assertEqual(response.status, 400)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload["code"], "MISSING_INPUT")
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file

    @patch("gateway.server.requests.post")
    def test_non_stream_path_returns_json(self, mock_post):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/event-stream"}
            text = 'data: {"type":"response.done","response":{"id":"resp_1"}}\n'

            @staticmethod
            def iter_content(chunk_size=1024):
                yield b""

        mock_post.return_value = FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "openai.json"
            token_file.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": _jwt_with_account("acct_test"),
                        "refresh": "refresh_1",
                        "expires": int(time.time() * 1000) + 3600 * 1000,
                    }
                ),
                encoding="utf-8",
            )

            original_auth_token_file = auth.TOKEN_FILE
            original_server_token_file = server.TOKEN_FILE
            auth.TOKEN_FILE = token_file
            server.TOKEN_FILE = token_file
            try:
                conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
                body = json.dumps(
                    {
                        "model": "gpt-5.1-codex",
                        "stream": False,
                        "include": ["output_text", "reasoning.encrypted_content", "output_text"],
                        "input": [{"role": "user", "content": "hi"}],
                    }
                ).encode("utf-8")
                conn.request("POST", "/responses", body=body, headers={"content-type": "application/json"})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload["id"], "resp_1")
                self.assertTrue(mock_post.called)
                called_json = mock_post.call_args.kwargs["json"]
                self.assertIn("instructions", called_json)
                self.assertTrue(called_json["instructions"])
                self.assertEqual(called_json["include"], ["output_text", "reasoning.encrypted_content"])
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file


if __name__ == "__main__":
    unittest.main()
