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
        server._clear_models_cache_for_tests()
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

    def test_v1_validation_error_uses_openai_error_shape(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(
            "POST",
            "/v1/responses",
            body=b'{"model":"gpt-5.1-codex"}',
            headers={"content-type": "application/json", "authorization": "Bearer local-test-key"},
        )
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(
            payload,
            {
                "error": {
                    "message": "Request body must include an input field.",
                    "type": "gateway_error",
                    "code": "MISSING_INPUT",
                }
            },
        )
        conn.close()

    @patch("gateway.server.requests.get")
    def test_v1_models_returns_openai_compatible_list(self, mock_get):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            text = ""

            @staticmethod
            def json():
                return {
                    "models": [
                        {
                            "slug": "gpt-5.5",
                            "display_name": "GPT-5.5",
                            "visibility": "list",
                            "supported_in_api": True,
                            "context_window": 272000,
                        },
                        {
                            "slug": "gpt-5.3-codex-spark",
                            "visibility": "list",
                            "supported_in_api": False,
                            "context_window": 128000,
                        },
                        {
                            "slug": "codex-auto-review",
                            "visibility": "hide",
                            "supported_in_api": True,
                            "context_window": 272000,
                        },
                    ]
                }

        mock_get.return_value = FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "openai.json"
            access_token = _jwt_with_account("acct_test")
            token_file.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": access_token,
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
                conn.request("GET", "/v1/models", headers={"authorization": "Bearer local-test-key"})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(
                    payload,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": "gpt-5.5",
                                "object": "model",
                                "owned_by": "openai-codex",
                            }
                        ],
                    },
                )

                called_headers = mock_get.call_args.kwargs["headers"]
                self.assertEqual(called_headers["Authorization"], f"Bearer {access_token}")
                self.assertNotEqual(called_headers["Authorization"], "Bearer local-test-key")
                self.assertEqual(mock_get.call_args.kwargs["params"], {"client_version": server.CODEX_MODELS_CLIENT_VERSION})
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file

    @patch("gateway.server.requests.get")
    def test_codex_models_returns_full_backend_metadata(self, mock_get):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            text = ""

            @staticmethod
            def json():
                return {
                    "models": [
                        {
                            "slug": "gpt-5.5",
                            "display_name": "GPT-5.5",
                            "visibility": "list",
                            "supported_in_api": True,
                            "context_window": 272000,
                        },
                        {
                            "slug": "codex-auto-review",
                            "display_name": "Codex Auto Review",
                            "visibility": "hide",
                            "supported_in_api": True,
                            "context_window": 272000,
                        },
                    ]
                }

        mock_get.return_value = FakeResponse()

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
                conn.request("GET", "/codex/models")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(payload["models"]), 2)
                self.assertEqual(payload["models"][1]["slug"], "codex-auto-review")
                self.assertEqual(payload["models"][1]["visibility"], "hide")
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file

    @patch("gateway.server.requests.get")
    def test_v1_models_uses_in_process_cache(self, mock_get):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            text = ""

            @staticmethod
            def json():
                return {
                    "models": [
                        {
                            "slug": "gpt-5.5",
                            "visibility": "list",
                            "supported_in_api": True,
                        },
                    ]
                }

        mock_get.return_value = FakeResponse()

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
                for _ in range(2):
                    conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
                    conn.request("GET", "/v1/models")
                    response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    response.read()
                    conn.close()
                self.assertEqual(mock_get.call_count, 1)
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

    @patch("gateway.server.requests.post")
    def test_v1_non_stream_path_returns_openai_compatible_response(self, mock_post):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/event-stream"}
            text = "\n".join([
                'data: {"type":"response.completed","response":{"id":"resp_1","output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"gateway-ok"}]}],"usage":{"input_tokens":1,"output_tokens":2,"total_tokens":3}}}',
                "",
            ])

            @staticmethod
            def iter_content(chunk_size=1024):
                yield b""

        mock_post.return_value = FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "openai.json"
            access_token = _jwt_with_account("acct_test")
            token_file.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": access_token,
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
                        "model": "gpt-5-codex",
                        "stream": False,
                        "input": "hello",
                    }
                ).encode("utf-8")
                conn.request(
                    "POST",
                    "/v1/responses",
                    body=body,
                    headers={"content-type": "application/json", "authorization": "Bearer local-test-key"},
                )
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload["id"], "resp_1")
                self.assertEqual(payload["object"], "response")
                self.assertEqual(payload["status"], "completed")
                self.assertEqual(payload["model"], "gpt-5-codex")
                self.assertEqual(payload["output_text"], "gateway-ok")
                self.assertEqual(payload["usage"], {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})

                called_headers = mock_post.call_args.kwargs["headers"]
                self.assertEqual(called_headers["Authorization"], f"Bearer {access_token}")
                self.assertNotEqual(called_headers["Authorization"], "Bearer local-test-key")
                called_json = mock_post.call_args.kwargs["json"]
                self.assertTrue(called_json["stream"])
                self.assertEqual(called_json["input"], [{"role": "user", "content": "hello"}])
                self.assertEqual(called_json["model"], "gpt-5-codex")
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file

    @patch("gateway.server.requests.get")
    @patch("gateway.server.requests.post")
    def test_v1_non_stream_omitted_model_uses_first_backend_model(self, mock_post, mock_get):
        class FakeModelsResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            text = ""

            @staticmethod
            def json():
                return {
                    "models": [
                        {
                            "slug": "gpt-5.5",
                            "visibility": "list",
                            "supported_in_api": True,
                        },
                        {
                            "slug": "gpt-5.4-mini",
                            "visibility": "list",
                            "supported_in_api": True,
                        },
                    ]
                }

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/event-stream"}
            text = 'data: {"type":"response.completed","response":{"id":"resp_1","output":[]}}\n'

            @staticmethod
            def iter_content(chunk_size=1024):
                yield b""

        mock_get.return_value = FakeModelsResponse()
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
            original_default_model = server.DEFAULT_GATEWAY_MODEL
            auth.TOKEN_FILE = token_file
            server.TOKEN_FILE = token_file
            server.DEFAULT_GATEWAY_MODEL = None
            try:
                conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
                body = json.dumps(
                    {
                        "stream": False,
                        "input": "hello",
                    }
                ).encode("utf-8")
                conn.request(
                    "POST",
                    "/v1/responses",
                    body=body,
                    headers={"content-type": "application/json"},
                )
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload["model"], "gpt-5.5")
                self.assertEqual(mock_post.call_args.kwargs["json"]["model"], "gpt-5.5")
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file
                server.DEFAULT_GATEWAY_MODEL = original_default_model

    @patch("gateway.server.requests.post")
    def test_v1_stream_path_passthrough(self, mock_post):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/event-stream; charset=utf-8"}
            text = ""

            @staticmethod
            def iter_content(chunk_size=1024):
                yield b'data: {"type":"response.output_text.delta","delta":"hi"}\n\n'
                yield b'data: {"type":"response.completed","response":{"id":"resp_1","object":"response","status":"completed","output":[]}}\n\n'

        mock_post.return_value = FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "openai.json"
            access_token = _jwt_with_account("acct_test")
            token_file.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": access_token,
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
                        "stream": True,
                        "input": "hello",
                    }
                ).encode("utf-8")
                conn.request(
                    "POST",
                    "/v1/responses",
                    body=body,
                    headers={"content-type": "application/json", "authorization": "Bearer local-test-key"},
                )
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("content-type"), "text/event-stream; charset=utf-8")
                body_text = response.read().decode("utf-8")
                self.assertIn('"type":"response.output_text.delta"', body_text)
                self.assertIn('"type":"response.completed"', body_text)

                called_headers = mock_post.call_args.kwargs["headers"]
                self.assertEqual(called_headers["Authorization"], f"Bearer {access_token}")
                self.assertNotEqual(called_headers["Authorization"], "Bearer local-test-key")
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file

    @patch("gateway.server.requests.post")
    def test_v1_non_stream_upstream_error_uses_openai_error_shape(self, mock_post):
        class FakeResponse:
            status_code = 404
            headers = {"content-type": "application/json"}
            text = '{"detail":"Input must be a list"}'

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
                        "input": "hello",
                    }
                ).encode("utf-8")
                conn.request(
                    "POST",
                    "/v1/responses",
                    body=body,
                    headers={"content-type": "application/json", "authorization": "Bearer local-test-key"},
                )
                response = conn.getresponse()
                self.assertEqual(response.status, 404)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(
                    payload,
                    {
                        "error": {
                            "message": "Input must be a list",
                            "type": "gateway_error",
                            "code": "UPSTREAM_ERROR",
                        }
                    },
                )
                conn.close()
            finally:
                auth.TOKEN_FILE = original_auth_token_file
                server.TOKEN_FILE = original_server_token_file


if __name__ == "__main__":
    unittest.main()
