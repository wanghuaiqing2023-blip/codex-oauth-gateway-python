import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from .auth import get_chatgpt_account_id, get_valid_tokens, load_tokens
from .config import (
    CODEX_RESPONSES_URL,
    DEFAULT_GATEWAY_PORT,
    DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
    OPENAI_HEADERS,
    OPENAI_HEADER_VALUES,
    TOKEN_FILE,
)
from .errors import GatewayError
from .model import normalize_model
from .response import map_usage_limit_404, parse_final_response


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("content-length", "0"))
    if content_length > 20 * 1024 * 1024:
        raise GatewayError(413, "REQUEST_BODY_TOO_LARGE", "Request body too large.")
    raw = handler.rfile.read(content_length) if content_length > 0 else b"{}"
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise GatewayError(400, "INVALID_JSON", "Request body must be valid JSON.")


def _transform_body(body: dict) -> dict:
    if "input" not in body:
        raise GatewayError(400, "MISSING_INPUT", "Request body must include an input field.")

    include = list(dict.fromkeys((body.get("include") or []) + ["reasoning.encrypted_content"]))
    return {
        **body,
        "model": normalize_model(body.get("model")),
        "store": False,
        "stream": True,
        "reasoning": {
            "effort": (body.get("reasoning") or {}).get("effort", "medium"),
            "summary": (body.get("reasoning") or {}).get("summary", "auto"),
        },
        "text": {
            "verbosity": (body.get("text") or {}).get("verbosity", "medium"),
        },
        "include": include,
    }


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "codex-oauth-gateway-python/0.1"

    def do_GET(self):
        if self.path == "/health":
            tokens = load_tokens()
            return _json_response(
                self,
                200,
                {
                    "ok": True,
                    "authenticated": tokens is not None,
                    "tokenFile": str(TOKEN_FILE),
                    "expires": tokens.expires if tokens else None,
                },
            )
        return _json_response(self, 404, {"error": "Not found", "routes": ["GET /health", "POST /responses"]})

    def do_POST(self):
        if self.path != "/responses":
            return _json_response(self, 404, {"error": "Not found", "routes": ["GET /health", "POST /responses"]})

        try:
            input_body = _read_json_body(self)
            requested_stream = input_body.get("stream") is True
            body = _transform_body(input_body)
            tokens = get_valid_tokens()
            account_id = get_chatgpt_account_id(tokens.access)
            if not account_id:
                raise GatewayError(401, "INVALID_ACCESS_TOKEN", "Could not extract ChatGPT account id from access token.")

            headers = {
                "Authorization": f"Bearer {tokens.access}",
                OPENAI_HEADERS["account_id"]: account_id,
                OPENAI_HEADERS["beta"]: OPENAI_HEADER_VALUES["beta"],
                OPENAI_HEADERS["originator"]: OPENAI_HEADER_VALUES["originator"],
                "accept": "text/event-stream",
                "content-type": "application/json",
            }
            if body.get("prompt_cache_key"):
                headers[OPENAI_HEADERS["conversation_id"]] = body["prompt_cache_key"]
                headers[OPENAI_HEADERS["session_id"]] = body["prompt_cache_key"]

            upstream = requests.post(
                CODEX_RESPONSES_URL,
                headers=headers,
                json=body,
                timeout=DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
                stream=True,
            )

            self.send_response(upstream.status_code)
            self.send_header("x-gateway-upstream-retry-attempts", "0")

            if requested_stream:
                self.send_header("content-type", upstream.headers.get("content-type", "text/event-stream; charset=utf-8"))
                self.end_headers()
                for chunk in upstream.iter_content(chunk_size=1024):
                    if chunk:
                        self.wfile.write(chunk)
                return

            full_text = upstream.text
            status, full_text = map_usage_limit_404(upstream.status_code, full_text)
            final = parse_final_response(full_text)
            if final is None:
                self.send_response(status)
                self.send_header("content-type", "text/event-stream; charset=utf-8")
                self.end_headers()
                self.wfile.write(full_text.encode("utf-8"))
                return

            payload = json.dumps(final, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except GatewayError as error:
            return _json_response(
                self,
                error.status,
                {
                    "error": str(error),
                    "code": error.code,
                    "details": error.details,
                },
            )
        except requests.Timeout:
            return _json_response(self, 504, {"error": "Upstream timeout.", "code": "UPSTREAM_TIMEOUT"})
        except requests.RequestException as error:
            return _json_response(self, 502, {"error": str(error), "code": "UPSTREAM_REQUEST_FAILED"})
        except Exception as error:  # noqa: BLE001
            return _json_response(self, 500, {"error": str(error), "code": "INTERNAL_SERVER_ERROR"})


def start_server(port: int = DEFAULT_GATEWAY_PORT):
    server = ThreadingHTTPServer(("127.0.0.1", port), GatewayHandler)
    print(f"codex-oauth-gateway-python listening on http://127.0.0.1:{port}")
    server.serve_forever()
