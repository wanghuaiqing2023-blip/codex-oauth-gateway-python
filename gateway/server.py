import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests

from .auth import get_chatgpt_account_id, get_valid_tokens, load_tokens
from .config import (
    CODEX_MODELS_CLIENT_VERSION,
    CODEX_MODELS_CACHE_TTL_SECONDS,
    CODEX_MODELS_URL,
    CODEX_RESPONSES_URL,
    DEFAULT_INSTRUCTIONS,
    DEFAULT_GATEWAY_PORT,
    DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
    DEFAULT_GATEWAY_MODEL,
    FALLBACK_GATEWAY_MODEL,
    OPENAI_HEADERS,
    OPENAI_HEADER_VALUES,
    TOKEN_FILE,
)
from .errors import GatewayError
from .model import requested_model
from .response import map_usage_limit_404, parse_final_response


RESPONSES_PATHS = {"/responses", "/v1/responses"}
MODELS_PATHS = {"/v1/models", "/codex/models"}
_MODELS_CACHE_LOCK = threading.Lock()
_MODELS_CACHE_PAYLOAD: dict | None = None
_MODELS_CACHE_EXPIRES_AT = 0.0


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _request_path(raw_path: str) -> str:
    return urlparse(raw_path).path


def _is_openai_compatible_path(raw_path: str) -> bool:
    return _request_path(raw_path).startswith("/v1/")


def _is_responses_path(raw_path: str) -> bool:
    return _request_path(raw_path) in RESPONSES_PATHS


def _is_models_path(raw_path: str) -> bool:
    return _request_path(raw_path) in MODELS_PATHS


def _openai_error_payload(message: str, code: str | None = None, details=None) -> dict:
    error = {
        "message": message,
        "type": "gateway_error",
        "code": code,
    }
    if details is not None:
        error["details"] = details
    return {"error": error}


def _gateway_error_payload(error: GatewayError, openai_compatible: bool) -> dict:
    if openai_compatible:
        return _openai_error_payload(str(error), error.code, error.details)
    return {
        "error": str(error),
        "code": error.code,
        "details": error.details,
    }


def _generic_error_payload(message: str, code: str, openai_compatible: bool) -> dict:
    if openai_compatible:
        return _openai_error_payload(message, code)
    return {"error": message, "code": code}


def _upstream_openai_error_payload(status: int, body_text: str) -> dict:
    try:
        parsed = json.loads(body_text)
        upstream_error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(upstream_error, dict):
            error = dict(upstream_error)
            error["message"] = error.get("message") or error.get("code") or f"Upstream returned status {status}."
            error["type"] = error.get("type") or "upstream_error"
            error["code"] = error.get("code")
            return {"error": error}
        detail = parsed.get("detail") if isinstance(parsed, dict) else None
        if isinstance(detail, str):
            return _openai_error_payload(detail, "UPSTREAM_ERROR")
    except Exception:
        pass
    return _openai_error_payload(body_text or f"Upstream returned status {status}.", "UPSTREAM_ERROR")


def _not_found_response(handler: BaseHTTPRequestHandler):
    routes = ["GET /health", "GET /v1/models", "GET /codex/models", "POST /responses", "POST /v1/responses"]
    if _is_openai_compatible_path(handler.path):
        return _json_response(handler, 404, _openai_error_payload("Not found", "NOT_FOUND"))
    return _json_response(handler, 404, {"error": "Not found", "routes": routes})


def _upstream_headers(access_token: str, account_id: str, accept: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        OPENAI_HEADERS["account_id"]: account_id,
        OPENAI_HEADERS["beta"]: OPENAI_HEADER_VALUES["beta"],
        OPENAI_HEADERS["originator"]: OPENAI_HEADER_VALUES["originator"],
        "accept": accept,
    }


def _get_upstream_auth() -> tuple[str, str]:
    tokens = get_valid_tokens()
    account_id = get_chatgpt_account_id(tokens.access)
    if not account_id:
        raise GatewayError(401, "INVALID_ACCESS_TOKEN", "Could not extract ChatGPT account id from access token.")
    return tokens.access, account_id


def _fetch_codex_models():
    access_token, account_id = _get_upstream_auth()
    return requests.get(
        CODEX_MODELS_URL,
        headers=_upstream_headers(access_token, account_id, "application/json"),
        params={"client_version": CODEX_MODELS_CLIENT_VERSION},
        timeout=DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
    )


def _clear_models_cache_for_tests() -> None:
    global _MODELS_CACHE_EXPIRES_AT, _MODELS_CACHE_PAYLOAD
    with _MODELS_CACHE_LOCK:
        _MODELS_CACHE_PAYLOAD = None
        _MODELS_CACHE_EXPIRES_AT = 0.0


def _cached_codex_models(*, allow_expired: bool = False) -> dict | None:
    now = time.time()
    with _MODELS_CACHE_LOCK:
        if _MODELS_CACHE_PAYLOAD is None:
            return None
        if allow_expired or _MODELS_CACHE_EXPIRES_AT > now:
            return _MODELS_CACHE_PAYLOAD
    return None


def _store_codex_models(payload: dict) -> None:
    global _MODELS_CACHE_EXPIRES_AT, _MODELS_CACHE_PAYLOAD
    with _MODELS_CACHE_LOCK:
        _MODELS_CACHE_PAYLOAD = payload
        _MODELS_CACHE_EXPIRES_AT = time.time() + CODEX_MODELS_CACHE_TTL_SECONDS


def _codex_models_payload() -> tuple[dict | None, object | None]:
    cached = _cached_codex_models()
    if cached is not None:
        return cached, None

    upstream = _fetch_codex_models()
    if upstream.status_code >= 400:
        stale = _cached_codex_models(allow_expired=True)
        if stale is not None:
            return stale, None
        return None, upstream

    try:
        payload = upstream.json()
    except Exception as error:
        stale = _cached_codex_models(allow_expired=True)
        if stale is not None:
            return stale, None
        raise GatewayError(502, "UPSTREAM_INVALID_JSON", "Models endpoint returned invalid JSON.") from error

    if not isinstance(payload, dict):
        raise GatewayError(502, "UPSTREAM_INVALID_JSON", "Models endpoint must return a JSON object.")

    _store_codex_models(payload)
    return payload, None


def _iter_api_visible_models(codex_payload: dict):
    models = codex_payload.get("models")
    if not isinstance(models, list):
        return

    for model in models:
        if not isinstance(model, dict):
            continue
        if model.get("visibility") != "list" or model.get("supported_in_api") is not True:
            continue
        slug = model.get("slug")
        if isinstance(slug, str) and slug:
            yield model


def _first_api_visible_model(codex_payload: dict) -> str | None:
    for model in _iter_api_visible_models(codex_payload):
        return model["slug"]
    return None


def _default_model() -> str:
    if DEFAULT_GATEWAY_MODEL:
        return DEFAULT_GATEWAY_MODEL

    try:
        payload, upstream_error = _codex_models_payload()
    except Exception:
        return FALLBACK_GATEWAY_MODEL

    if payload is not None and upstream_error is None:
        model = _first_api_visible_model(payload)
        if model:
            return model

    return FALLBACK_GATEWAY_MODEL


def _request_model(model: object) -> str:
    return requested_model(model) or _default_model()


def _openai_models_payload(codex_payload: dict) -> dict:
    data = []
    for model in _iter_api_visible_models(codex_payload):
        data.append(
            {
                "id": model["slug"],
                "object": "model",
                "owned_by": "openai-codex",
            }
        )
    return {"object": "list", "data": data}


def _proxy_json_upstream_response(handler: BaseHTTPRequestHandler, upstream, *, openai_compatible: bool):
    try:
        payload = upstream.json()
    except Exception:
        message = upstream.text or f"Upstream returned status {upstream.status_code}."
        if openai_compatible:
            payload = _openai_error_payload(message, "UPSTREAM_ERROR")
        else:
            payload = {"error": message, "code": "UPSTREAM_ERROR"}

    if openai_compatible and upstream.status_code >= 400:
        payload = _upstream_openai_error_payload(upstream.status_code, upstream.text)

    return _json_response(handler, upstream.status_code, payload if isinstance(payload, dict) else {"data": payload})


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

    input_value = body["input"]
    if isinstance(input_value, str):
        input_value = [{"role": "user", "content": input_value}]

    include = list(dict.fromkeys((body.get("include") or []) + ["reasoning.encrypted_content"]))
    return {
        **body,
        "input": input_value,
        "model": _request_model(body.get("model")),
        "store": False,
        "stream": True,
        "instructions": body.get("instructions") or DEFAULT_INSTRUCTIONS,
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
        openai_compatible = _is_openai_compatible_path(self.path)
        path = _request_path(self.path)
        if path == "/health":
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
        if _is_models_path(self.path):
            try:
                codex_payload, upstream = _codex_models_payload()
                if upstream is not None:
                    return _proxy_json_upstream_response(self, upstream, openai_compatible=openai_compatible)
                if codex_payload is None:
                    raise GatewayError(502, "UPSTREAM_INVALID_JSON", "Models endpoint returned no JSON payload.")
                if openai_compatible:
                    return _json_response(self, 200, _openai_models_payload(codex_payload))
                return _json_response(self, 200, codex_payload)
            except GatewayError as error:
                return _json_response(self, error.status, _gateway_error_payload(error, openai_compatible))
            except requests.Timeout:
                return _json_response(
                    self,
                    504,
                    _generic_error_payload("Upstream timeout.", "UPSTREAM_TIMEOUT", openai_compatible),
                )
            except requests.RequestException as error:
                return _json_response(
                    self,
                    502,
                    _generic_error_payload(str(error), "UPSTREAM_REQUEST_FAILED", openai_compatible),
                )
            except Exception as error:  # noqa: BLE001
                return _json_response(
                    self,
                    500,
                    _generic_error_payload(str(error), "INTERNAL_SERVER_ERROR", openai_compatible),
                )
        return _not_found_response(self)

    def do_POST(self):
        openai_compatible = _is_openai_compatible_path(self.path)
        if not _is_responses_path(self.path):
            return _not_found_response(self)

        try:
            input_body = _read_json_body(self)
            requested_stream = input_body.get("stream") is True
            body = _transform_body(input_body)
            access_token, account_id = _get_upstream_auth()
            headers = {
                **_upstream_headers(access_token, account_id, "text/event-stream"),
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

            if requested_stream:
                self.send_response(upstream.status_code)
                self.send_header("x-gateway-upstream-retry-attempts", "0")
                self.send_header("content-type", upstream.headers.get("content-type", "text/event-stream; charset=utf-8"))
                self.end_headers()
                for chunk in upstream.iter_content(chunk_size=1024):
                    if chunk:
                        self.wfile.write(chunk)
                return

            full_text = upstream.text
            status, full_text = map_usage_limit_404(upstream.status_code, full_text)
            final = parse_final_response(
                full_text,
                default_model=body.get("model"),
                openai_compatible=openai_compatible,
            )
            if final is None:
                if openai_compatible and status >= 400:
                    return _json_response(self, status, _upstream_openai_error_payload(status, full_text))
                self.send_response(status)
                self.send_header("x-gateway-upstream-retry-attempts", "0")
                self.send_header("content-type", "text/event-stream; charset=utf-8")
                self.end_headers()
                self.wfile.write(full_text.encode("utf-8"))
                return

            payload = json.dumps(final, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("x-gateway-upstream-retry-attempts", "0")
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except GatewayError as error:
            return _json_response(self, error.status, _gateway_error_payload(error, openai_compatible))
        except requests.Timeout:
            return _json_response(
                self,
                504,
                _generic_error_payload("Upstream timeout.", "UPSTREAM_TIMEOUT", openai_compatible),
            )
        except requests.RequestException as error:
            return _json_response(
                self,
                502,
                _generic_error_payload(str(error), "UPSTREAM_REQUEST_FAILED", openai_compatible),
            )
        except Exception as error:  # noqa: BLE001
            return _json_response(
                self,
                500,
                _generic_error_payload(str(error), "INTERNAL_SERVER_ERROR", openai_compatible),
            )


def start_server(port: int = DEFAULT_GATEWAY_PORT):
    server = ThreadingHTTPServer(("127.0.0.1", port), GatewayHandler)
    print(f"codex-oauth-gateway-python listening on http://127.0.0.1:{port}")
    server.serve_forever()
