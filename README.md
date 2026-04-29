# codex-oauth-gateway-python

A Python OAuth gateway for routing local or internal requests to OpenAI Codex Responses.

## Overview
- Provides a lightweight HTTP gateway with OAuth token management.
- Normalizes request payloads before forwarding upstream.
- Supports both streaming passthrough and non-stream JSON responses.

## Current capabilities
- Routes
  - `GET /health`: service health and auth status.
  - `POST /responses`: forward requests to upstream Responses API.
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

### 4) Run tests
```bash
PYTHONPATH=. python -m unittest discover -s tests
```

## Configuration
- `CODEX_GATEWAY_PORT`: gateway port (default: `8787`)
- `CODEX_UPSTREAM_TIMEOUT_SECONDS`: upstream timeout in seconds (default: `60`)
- `CODEX_GATEWAY_TOKEN_FILE`: token file path (default: `~/.codex-oauth-gateway-python/openai.json`)

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
- Reliability improvements: retry/backoff/circuit-breaking/rate limiting.
- Observability: structured logs, metrics, tracing.
- Security hardening: token encryption and sensitive-data masking.
- Broader test coverage for malformed SSE, concurrency, and network faults.
