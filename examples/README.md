# Client Examples

These examples show how to use this gateway from normal client code.

Prerequisites:

1. Run OAuth once:

```powershell
python auth_cli.py
```

2. Start the gateway in another terminal:

```powershell
python main.py
```

3. Install client dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run examples from the repository root:

```powershell
python examples/01_health_check.py
python examples/02_response_create.py
python examples/03_stream_response.py
python examples/04_messages_input.py
python examples/05_list_models.py
```

Configuration:

- `CODEX_GATEWAY_BASE_URL`: default `http://127.0.0.1:8787/v1`
- `CODEX_GATEWAY_API_KEY`: default `local-dummy-key`
- `CODEX_GATEWAY_MODEL`: default `gpt-5.2`
- `CODEX_GATEWAY_PROMPT`: optional prompt override for examples 02 and 03

Gateway model discovery settings:

- `CODEX_GATEWAY_DEFAULT_MODEL`: gateway default when callers omit `model`
- `CODEX_GATEWAY_FALLBACK_MODEL`: fallback when model discovery is unavailable
- `CODEX_MODELS_CLIENT_VERSION`: Codex backend model-list client version
- `CODEX_MODELS_CACHE_TTL_SECONDS`: in-process model-list cache TTL

Response examples print both `requested_model` and `actual_model`. The actual model comes from the gateway/upstream response and may differ when the upstream normalizes or routes the request.

`05_list_models.py` prints both the OpenAI-compatible model list from `/v1/models` and the richer Codex metadata from `/codex/models`.

Example:

```powershell
$env:CODEX_GATEWAY_MODEL = "gpt-5.2"
$env:CODEX_GATEWAY_PROMPT = "Reply exactly: hello-from-gateway"
python examples/02_response_create.py
```
