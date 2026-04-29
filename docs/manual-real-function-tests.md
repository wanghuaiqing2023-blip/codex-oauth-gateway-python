# Manual Real-Function Test Cases

This checklist validates end-to-end behavior with real OAuth credentials and real upstream responses.

## Prerequisites
- Dependencies installed: `pip install -r requirements.txt`
- Gateway started from repo root.
- Network access to `auth.openai.com` and `chatgpt.com`.
- Valid ChatGPT account access.

Useful startup commands:
```bash
python auth_cli.py
python main.py
```

Default token path:
```text
~/.codex-oauth-gateway-python/openai.json
```

---

## Group 1: OAuth Login

### 1.1 Automatic browser callback
- Purpose: verify OAuth flow + token save.
- Steps:
  1. Remove old token file.
  2. Run `python auth_cli.py` and complete browser login.
- Expected:
  - Tokens saved to `~/.codex-oauth-gateway-python/openai.json`.
  - JSON includes `type/access/refresh/expires`.

### 1.2 Manual callback fallback
- Purpose: verify manual callback works when port `1455` is unavailable.
- Steps:
  1. Occupy port `1455`.
  2. Run `python auth_cli.py`.
  3. Paste callback URL or `code=...&state=...`.
- Expected: token save succeeds.

### 1.3 Note on state-mismatch coverage
- This scenario is covered by unit tests (deterministic) instead of manual checklist.
- Rationale: manual reproduction is timing-sensitive in real OAuth callback flow.

---

## Group 2: Token Lifecycle

### 2.1 Health check with valid token
- Request command (single line):
```bash
curl -sS http://127.0.0.1:8787/health
```
- Expected: `ok=true`, `authenticated=true`, non-null `expires`.

### 2.2 Missing token behavior
- Request command (single line):
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex","stream":false,"input":[{"role":"user","content":"ping"}]}'
```
- Expected: error code `MISSING_TOKENS`; process stays alive.

### 2.3 Expired token refresh
- After setting `expires` to past, request with one line:
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex","stream":false,"input":[{"role":"user","content":"reply with refresh-ok"}]}'
```
- Expected: token refresh, request succeeds.

### 2.4 Invalid refresh token
- After forcing expired token + invalid `refresh`, request with one line:
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex","stream":false,"input":[{"role":"user","content":"ping"}]}'
```
- Expected: error code `TOKEN_REFRESH_FAILED`.

---

## Group 3: Real Non-Streaming Responses

### 3.1 Minimal non-stream request
- Request command (single line):
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex","stream":false,"input":[{"role":"user","content":"Reply with exactly: gateway-ok"}]}'
```
- Expected: HTTP 200 JSON; output contains `gateway-ok`.

### 3.2 Custom instructions override
- Request command (single line):
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex","stream":false,"instructions":"Always reply with exactly: custom-instructions-ok","input":[{"role":"user","content":"Say hello."}]}'
```
- Expected: output follows custom instruction.

---

## Group 4: Real Streaming Responses

### 4.1 Basic streaming request
- Request command (single line):
```bash
curl -N http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex","stream":true,"input":[{"role":"user","content":"Count from 1 to 5, one number per line."}]}'
```
- Expected: incremental `data:` SSE events and final completion event.

### 4.2 Client interrupt
- Start 4.1 then press `Ctrl+C`.
- Verify with one-line command:
```bash
curl -sS http://127.0.0.1:8787/health
```
- Expected: gateway still healthy.

---

## Group 5: Request Transformation

### 5.1 Default model when model omitted
- Request command (single line):
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"stream":false,"input":[{"role":"user","content":"Reply with exactly: default-model-ok"}]}'
```
- Expected: succeeds with gateway default model.

### 5.2 Automated coverage note
- The following behaviors are intentionally covered by automated tests, not this manual checklist:
  - model alias normalization
  - include merge and de-dup logic
  - `usage_limit_exceeded` mapping (404 -> 429)

---

## Group 6: Error and Boundary Behavior

### 6.1 Invalid JSON
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{not-json'
```
Expected: `400`, code `INVALID_JSON`.

### 6.2 Missing input
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex"}'
```
Expected: `400`, code `MISSING_INPUT`.

### 6.3 Large body (>20MB)
- Generate and send in one line:
```bash
python -c 'import json; print(json.dumps({"input":"x"*(21*1024*1024)}))' | curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' --data-binary @-
```
Expected: `413`, code `REQUEST_BODY_TOO_LARGE`.

### 6.4 Backend unavailable
- Then send one-line request:
```bash
curl -sS http://127.0.0.1:8787/responses -H 'content-type: application/json' -d '{"model":"gpt-5.1-codex","stream":false,"input":[{"role":"user","content":"network-check"}]}'
```
Expected: `UPSTREAM_REQUEST_FAILED` or `UPSTREAM_TIMEOUT`.

---

## Recommended first pass
1. OAuth login success.
2. `/health` authenticated.
3. Non-streaming `/responses` success.
4. Streaming `/responses` success.
5. Expired token auto-refresh success.
