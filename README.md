# codex-oauth-gateway-python

A local Python OAuth gateway that lets the official OpenAI Python SDK talk to
the ChatGPT Codex backend through OpenAI-compatible Responses API routes.

## Overview

- Manages ChatGPT OAuth login, token refresh, and local token persistence.
- Exposes OpenAI SDK-compatible routes such as `/v1/responses` and `/v1/models`.
- Forwards explicit caller models unchanged; omitted models use environment or
  backend model discovery defaults.
- Applies only Codex-required request adaptations, such as upstream
  `store=false` and `include=["reasoning.encrypted_content"]`.
- Supports non-streaming SDK calls and streaming SDK calls.
- Exposes `/codex/models` for full backend model metadata and capability probes.

The gateway is intended to stay close to a transparent proxy. It should not
become a smart routing layer or a custom client SDK.

## Current Routes

```text
+-------------------+-----------------------------------------------------+
| Route             | Purpose                                             |
+-------------------+-----------------------------------------------------+
| GET /health       | Health check and OAuth token status.                |
| GET /v1/models    | OpenAI SDK-compatible model list.                   |
| GET /codex/models | Full Codex backend model metadata.                  |
| POST /responses   | Local Responses route.                              |
| POST /v1/responses| OpenAI SDK-compatible Responses API route.          |
+-------------------+-----------------------------------------------------+
```

## Quickstart

Create an environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Authenticate once:

```bash
python auth_cli.py
```

Start the gateway:

```bash
python main.py
```

Default address:

```text
http://127.0.0.1:8787
```

Health check:

```bash
curl -s http://127.0.0.1:8787/health
```

Run tests:

```bash
PYTHONPATH=. python -m unittest discover -s tests
```

On Windows PowerShell:

```powershell
python -m unittest discover -s tests
```

## OpenAI SDK Usage

Install the SDK in your client environment:

```bash
pip install openai
```

Non-streaming:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8787/v1",
    api_key="local-dummy-key",
)

response = client.responses.create(
    model="gpt-5.2",
    input="hello",
)

print(response.output_text)
```

Streaming:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8787/v1",
    api_key="local-dummy-key",
)

stream = client.responses.create(
    model="gpt-5.2",
    input="hello",
    stream=True,
)

for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="")
```

The local `api_key` is accepted for SDK compatibility. Upstream requests use
the OAuth access token saved by `auth_cli.py`; the inbound SDK key is not sent
to the Codex backend.

## Examples

Runnable examples live in `examples/`. The directory is organized so that each
OpenAI Responses API parameter has its own directory, and tool probes live
under `examples/tool/`.

Start with:

```bash
python examples/basic/01_health_check.py
python examples/basic/02_response_create.py
python examples/basic/03_stream_response.py
python examples/basic/04_messages_input.py
python examples/models/01_list_models.py
```

Parameter examples:

```text
examples/background/
examples/context_management/
examples/conversation/
examples/extra_body/
examples/include/
examples/instructions/
examples/max_output_tokens/
examples/max_tool_calls/
examples/metadata/
examples/parallel_tool_calls/
examples/previous_response_id/
examples/prompt_cache_retention/
examples/reasoning/
examples/safety_identifier/
examples/service_tier/
examples/store/
examples/stream_options/
examples/temperature/
examples/text_format/
examples/text_verbosity/
examples/tool_choice/
examples/top_logprobs/
examples/top_p/
examples/truncation/
examples/user/
```

Tool examples:

```text
examples/tool/apply_patch/
examples/tool/custom/
examples/tool/function/
examples/tool/image_generation/
examples/tool/local_shell/
examples/tool/openai_mcp/
examples/tool/openai_shell/
examples/tool/shell_function/
examples/tool/tool_search/
examples/tool/web_search/
```

See `examples/README.md` for detailed commands and current probe conclusions.

## Configuration

```text
+----------------------------------+----------------------------------------------------+
| Variable                         | Meaning                                            |
+----------------------------------+----------------------------------------------------+
| CODEX_GATEWAY_PORT               | Gateway port, default 8787.                        |
| CODEX_GATEWAY_TOKEN_FILE         | Token file path.                                   |
| CODEX_GATEWAY_DEFAULT_MODEL      | Default model when the caller omits model.         |
| CODEX_GATEWAY_FALLBACK_MODEL     | Fallback if model discovery is unavailable.        |
| CODEX_MODELS_CLIENT_VERSION      | Client version for Codex model discovery.          |
| CODEX_MODELS_CACHE_TTL_SECONDS   | In-process model metadata cache TTL.               |
| CODEX_UPSTREAM_TIMEOUT_SECONDS   | Low-level upstream HTTP timeout, default 60.       |
+----------------------------------+----------------------------------------------------+
```

Default token path:

```text
~/.codex-oauth-gateway-python/openai.json
```

Default model selection when a request omits `model`:

1. `CODEX_GATEWAY_DEFAULT_MODEL`
2. First API-supported model from `/codex/models`
3. `CODEX_GATEWAY_FALLBACK_MODEL`, default `gpt-5.2`

If a request includes `model`, the gateway forwards it unchanged.

## Current Compatibility Notes

- `client.responses.create(...)` and `client.responses.create(..., stream=True)`
  are the primary supported SDK flows.
- `/v1/models` is SDK-compatible. `/codex/models` returns richer backend
  metadata for diagnostics and examples.
- `store` is a Codex backend compatibility policy: upstream requests are forced
  to `store=false`.
- `reasoning.encrypted_content` is automatically included because the current
  stateless Codex response flow requires it.
- `previous_response_id` is rejected by the current stateless Codex backend
  path and should not be used as a multi-turn state mechanism here.
- The gateway does not implement the official Conversations API, so
  `conversation` is not a supported state mechanism.
- If `prompt_cache_key` is omitted, the gateway omits Codex session/cache
  fields rather than sending empty placeholders.
- Tool support is intentionally documented through probes. Backend-hosted tools
  and client-executed tools are different categories.

## Project Layout

```text
.
+-- auth_cli.py
+-- main.py
+-- gateway/
|   +-- auth.py
|   +-- config.py
|   +-- errors.py
|   +-- model.py
|   +-- response.py
|   +-- server.py
+-- examples/
|   +-- basic/
|   +-- include/
|   +-- tool/
|   +-- ...
+-- docs/
+-- tests/
+-- requirements.txt
+-- README.md
```

## Documentation

- `docs/design-principles.md`: proxy and compatibility design principles.
- `docs/include-capability-matrix.md`: current `include` probe results.
- `docs/parameter-capability-matrix.md`: selected parameter probe results.
- `docs/tool-capability-matrix.md`: tool capability probe results.
- `docs/manual-real-function-tests.md`: manual end-to-end verification checklist.
