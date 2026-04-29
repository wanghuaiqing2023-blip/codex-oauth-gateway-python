# Manual Real-Function Test Cases

This document collects manual test cases for validating the gateway against real OAuth and backend behavior. It is intended as a living checklist while the gateway is still evolving.

## Scope

These tests focus on externally visible behavior:

- OAuth login and callback capture
- token persistence and refresh
- gateway health checks
- non-streaming real responses
- streaming real responses
- request transformation behavior
- error handling and edge cases

They are not a replacement for unit tests. They are meant to answer: "Can this gateway actually work end to end with a real account and real backend?"

## Prerequisites

- Python environment is ready.
- Dependencies are installed with `pip install -r requirements.txt`.
- The gateway is run from `codex-oauth-gateway-python`.
- The machine can reach `auth.openai.com` and `chatgpt.com`.
- The user has a ChatGPT account that can access the target Codex backend models.
- No unrelated service is using port `1455` during OAuth callback testing.
- No unrelated service is using port `8787` during gateway testing, unless `CODEX_GATEWAY_PORT` is set.

Useful commands:

```powershell
python -m unittest discover -s tests
python auth_cli.py
python main.py
```

Token default path:

```text
~/.codex-oauth-gateway-python/openai.json
```

Override path:

```powershell
$env:CODEX_GATEWAY_TOKEN_FILE = "C:\path\to\openai.json"
```

## Test Group 1: OAuth Login

### 1.1 Automatic Browser Callback

Purpose: verify that the CLI can start an OAuth flow, open the browser, capture the callback, and save tokens.

Steps:

1. Delete or move any existing token file from `~/.codex-oauth-gateway-python/openai.json`.
2. Run:

```powershell
python auth_cli.py
```

3. Complete login in the browser.
4. Return to the terminal after the callback page appears.

Expected result:

- Browser opens automatically or the terminal prints a login URL.
- Terminal prints that OAuth tokens were saved successfully.
- `~/.codex-oauth-gateway-python/openai.json` exists.
- The saved JSON contains `type`, `access`, `refresh`, and `expires`.

Notes to observe:

- Whether the browser opens reliably on Windows and Linux.
- Whether the callback message is understandable.
- Whether token save failures produce a useful error.

### 1.2 Manual Callback Fallback

Purpose: verify that login still works if the local callback server cannot be used.

Steps:

1. Occupy port `1455` with another process, or otherwise make the callback listener fail.
2. Run:

```powershell
python auth_cli.py
```

3. Complete login and manually paste the callback URL or `code=...&state=...` into the terminal.

Expected result:

- CLI falls back to manual input.
- Valid callback input is accepted.
- Tokens are saved successfully.

### 1.3 State Mismatch Rejection

Purpose: verify that the CLI rejects a callback with the wrong OAuth state.

Steps:

1. Run:

```powershell
python auth_cli.py
```

2. At the manual input prompt, paste a callback value with a valid-looking code but incorrect state.

Expected result:

- CLI rejects the input.
- It prints a state mismatch message.
- No new token file should be written from the invalid callback.

Discussion point:

- The callback listener receives `expected_state`; the strictness of state validation should be checked carefully in both automatic and manual paths.

## Test Group 2: Token Lifecycle

### 2.1 Health Check With Valid Token

Purpose: verify that the gateway can detect an authenticated state.

Steps:

1. Complete OAuth login.
2. Start the gateway:

```powershell
python main.py
```

3. In another terminal:

```powershell
curl.exe -s http://127.0.0.1:8787/health
```

Expected result:

- Response has `"ok": true`.
- Response has `"authenticated": true`.
- Response includes the token file path.
- Response includes a non-null `expires` value.

### 2.2 Missing Token

Purpose: verify behavior when no token file exists.

Steps:

1. Move or delete the token file.
2. Start the gateway.
3. Call:

```powershell
curl.exe -s http://127.0.0.1:8787/health
```

4. Send a minimal response request.

Expected result:

- `/health` reports `"authenticated": false`.
- `POST /responses` returns an error with code `MISSING_TOKENS`.
- The gateway process does not crash.

### 2.3 Expired Token Refresh

Purpose: verify that an expired access token is refreshed automatically.

Steps:

1. Complete OAuth login.
2. Open the token file.
3. Change `expires` to a timestamp in the past, such as `0`.
4. Start the gateway.
5. Send a minimal non-streaming request.

Expected result:

- Gateway refreshes the access token before calling the backend.
- Token file is updated.
- Request succeeds if the refresh token is valid.

### 2.4 Invalid Refresh Token

Purpose: verify a clean error when token refresh fails.

Steps:

1. Complete OAuth login.
2. Change the token file's `expires` to `0`.
3. Replace `refresh` with an invalid value.
4. Send a minimal request.

Expected result:

- Gateway returns an error with code `TOKEN_REFRESH_FAILED`.
- The error is not a Python traceback.
- The gateway remains running.

## Test Group 3: Real Non-Streaming Response

### 3.1 Minimal Non-Streaming Request

Purpose: verify that the gateway can send a real request and convert final SSE output to JSON.

Steps:

1. Complete OAuth login.
2. Start the gateway.
3. Send:

```powershell
$body = @{
  model = "gpt-5.1-codex"
  stream = $false
  input = @(
    @{
      role = "user"
      content = "Reply with exactly: gateway-ok"
    }
  )
} | ConvertTo-Json -Depth 10

curl.exe -s http://127.0.0.1:8787/responses `
  -H "content-type: application/json" `
  -d $body
```

Expected result:

- HTTP status is 200.
- Response content type is JSON.
- Response contains a final response object.
- `output_text` or `output` contains a reply close to `gateway-ok`.

Notes to observe:

- Whether the backend returns empty `output` and relies on delta reconstruction.
- Whether `parse_final_response` reconstructs usable JSON.

### 3.2 Custom Instructions Override

Purpose: verify that caller-provided instructions override default gateway instructions.

Steps:

```powershell
$body = @{
  model = "gpt-5.1-codex"
  stream = $false
  instructions = "Always reply with exactly: custom-instructions-ok"
  input = @(
    @{
      role = "user"
      content = "Say hello."
    }
  )
} | ConvertTo-Json -Depth 10

curl.exe -s http://127.0.0.1:8787/responses `
  -H "content-type: application/json" `
  -d $body
```

Expected result:

- Response follows the caller-provided instructions.
- Gateway does not overwrite the supplied `instructions`.

## Test Group 4: Real Streaming Response

### 4.1 Basic Streaming Request

Purpose: verify that `stream: true` returns server-sent events.

Steps:

```powershell
$body = @{
  model = "gpt-5.1-codex"
  stream = $true
  input = @(
    @{
      role = "user"
      content = "Count from 1 to 5, one number per line."
    }
  )
} | ConvertTo-Json -Depth 10

curl.exe -N http://127.0.0.1:8787/responses `
  -H "content-type: application/json" `
  -d $body
```

Expected result:

- Output arrives as `data: ...` events.
- Content appears incrementally.
- Final event is present.
- Gateway remains usable after the stream completes.

### 4.2 Client Interrupt

Purpose: verify that interrupting a streaming client does not kill the gateway.

Steps:

1. Start a streaming request.
2. Press `Ctrl+C` before the response finishes.
3. Send `GET /health`.

Expected result:

- Client interruption may end that request.
- Gateway process remains alive.
- `/health` still responds.

## Test Group 5: Request Transformation

### 5.1 Default Model

Purpose: verify behavior when no model is provided.

Steps:

```powershell
$body = @{
  stream = $false
  input = @(
    @{
      role = "user"
      content = "Reply with exactly: default-model-ok"
    }
  )
} | ConvertTo-Json -Depth 10

curl.exe -s http://127.0.0.1:8787/responses `
  -H "content-type: application/json" `
  -d $body
```

Expected result:

- Request succeeds.
- Gateway chooses the default normalized model.

### 5.2 Legacy Codex Model Alias

Purpose: verify that legacy model names map to supported model names.

Suggested inputs:

- `gpt-5-codex`
- `gpt-5-codex-mini`
- `codex-mini-latest`

Expected result:

- Requests succeed when the mapped backend model is available.
- Failures should be backend/model-access errors, not local validation crashes.

### 5.3 Include Preservation

Purpose: verify that caller-supplied `include` values are preserved while `reasoning.encrypted_content` is added.

Steps:

1. Send a request with a custom `include` array.
2. Observe response behavior.

Expected result:

- Request succeeds.
- No duplicate include values should be sent.
- Stateless encrypted reasoning behavior should remain enabled.

Discussion point:

- The gateway currently lacks safe request logging, so this is hard to verify directly without instrumentation.

## Test Group 6: Error And Boundary Behavior

### 6.1 Invalid JSON

Purpose: verify invalid body handling.

Steps:

```powershell
curl.exe -s http://127.0.0.1:8787/responses `
  -H "content-type: application/json" `
  -d "{not-json"
```

Expected result:

- HTTP status is 400.
- Error code is `INVALID_JSON`.

### 6.2 Missing Input

Purpose: verify required input validation.

Steps:

```powershell
curl.exe -s http://127.0.0.1:8787/responses `
  -H "content-type: application/json" `
  -d '{"model":"gpt-5.1-codex"}'
```

Expected result:

- HTTP status is 400.
- Error code is `MISSING_INPUT`.

### 6.3 Large Body

Purpose: verify request size protection.

Steps:

1. Send a body larger than 20 MB.
2. Observe response.

Expected result:

- HTTP status is 413.
- Error code is `REQUEST_BODY_TOO_LARGE`.

### 6.4 Backend Unavailable

Purpose: verify upstream request error handling.

Steps:

1. Temporarily block access to the backend or set the machine offline.
2. Send a request.

Expected result:

- Gateway returns `UPSTREAM_REQUEST_FAILED` or `UPSTREAM_TIMEOUT`.
- Gateway process remains running.

### 6.5 Usage Limit

Purpose: verify usage limit mapping.

Steps:

1. Trigger or simulate a backend `usage_limit_exceeded` response.
2. Observe gateway status code.

Expected result:

- Gateway maps backend 404 usage-limit responses to HTTP 429.

Discussion point:

- This may be difficult to trigger safely with a real account and may need a mock upstream test harness later.

## First Manual Test Pass Recommendation

For the first real test pass, prioritize:

1. OAuth login saves a token.
2. `/health` reports authenticated.
3. Non-streaming `/responses` returns JSON.
4. Streaming `/responses` returns SSE.
5. Expired token refreshes successfully.

If these pass, the main gateway path is usable. The remaining cases can be used to harden reliability, security, and compatibility.
