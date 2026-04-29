# codex-oauth-gateway-python

A Python OAuth gateway for routing local or internal requests to OpenAI Codex Responses.

## Overview
- Provides a lightweight HTTP gateway with OAuth token management.
- Normalizes request payloads before forwarding upstream.
- Supports both streaming passthrough and non-stream JSON responses.

## Current capabilities
- Routes
  - `GET /health`: service health and auth status.
  - `GET /v1/models`: OpenAI SDK-compatible model list.
  - `GET /codex/models`: full Codex backend model metadata.
  - `POST /responses`: forward requests to upstream Responses API.
  - `POST /v1/responses`: OpenAI SDK-compatible Responses API facade.
- OAuth
  - Authorization code exchange.
  - Refresh token flow with automatic renewal near expiry.
  - Local token file persistence.
- Request handling
  - Model normalization for common aliases.
  - Default fields for `instructions`, `reasoning`, and `text`.
  - Upstream requests are sent as SSE; response format follows client request mode.
- Response handling
  - SSE final-event parsing and `output_text` backfill.
  - Maps `usage_limit_exceeded` 404 responses to 429.
- Error handling
  - Structured errors with `status`, `code`, and optional `details`.

## Quickstart
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1) Authenticate and save tokens
```bash
python auth_cli.py
```

### 2) Start the gateway
```bash
python main.py
```

Default address: `http://127.0.0.1:8787`

### 3) Health check
```bash
curl -s http://127.0.0.1:8787/health
```

### 4) Use with the official OpenAI SDK
Install the SDK in your client environment:
```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8787/v1",
    api_key="local-dummy-key",
)

response = client.responses.create(
    model="gpt-5.1-codex",
    input="hello",
)

print(response.output_text)
```

Streaming:
```python
stream = client.responses.create(
    model="gpt-5.1-codex",
    input="hello",
    stream=True,
)

for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="")
```

The local `api_key` is accepted for SDK compatibility. Upstream requests still use the OAuth token saved by `auth_cli.py`.

### 5) Run tests
```bash
PYTHONPATH=. python -m unittest discover -s tests
```

## Examples
Runnable client examples live in `examples/`.

```bash
python examples/01_health_check.py
python examples/02_response_create.py
python examples/03_stream_response.py
python examples/04_messages_input.py
python examples/05_list_models.py
```

See `examples/README.md` for configuration options.

## Configuration
- `CODEX_GATEWAY_PORT`: gateway port (default: `8787`)
- `CODEX_UPSTREAM_TIMEOUT_SECONDS`: upstream timeout in seconds (default: `60`)
- `CODEX_GATEWAY_TOKEN_FILE`: token file path (default: `~/.codex-oauth-gateway-python/openai.json`)
- `CODEX_GATEWAY_DEFAULT_MODEL`: optional default model when a request omits `model`
- `CODEX_GATEWAY_FALLBACK_MODEL`: built-in fallback when model discovery is unavailable (default: `gpt-5.2`)
- `CODEX_MODELS_CLIENT_VERSION`: Codex backend model-list client version (default: `0.126.0`)
- `CODEX_MODELS_CACHE_TTL_SECONDS`: in-process model-list cache TTL (default: `21600`, or 6 hours)

If a request includes `model`, the gateway forwards it unchanged. If `model` is omitted, the gateway chooses `CODEX_GATEWAY_DEFAULT_MODEL`, then the first API-supported model from the Codex backend model list, then `CODEX_GATEWAY_FALLBACK_MODEL`.

## Upstream endpoints
- Responses: `https://chatgpt.com/backend-api/codex/responses`
- OAuth token: `https://auth.openai.com/oauth/token`
- OAuth authorize: `https://auth.openai.com/oauth/authorize`

## Project layout
```text
.
├── gateway/
│   ├── auth.py
│   ├── config.py
│   ├── errors.py
│   ├── model.py
│   ├── response.py
│   └── server.py
├── tests/
├── auth_cli.py
├── main.py
└── README.md
```

## Roadmap
- OpenAI SDK compatibility for `client.responses.create(...)` and streaming responses.
- Proxy fidelity: accurate request forwarding, error passthrough, and response semantics.
- Observability: structured logs, metrics, tracing.
- Security hardening: token encryption and sensitive-data masking.
- Broader test coverage for malformed SSE, concurrency, and network faults.

See `docs/design-principles.md` for the project compatibility and proxy design principles.
