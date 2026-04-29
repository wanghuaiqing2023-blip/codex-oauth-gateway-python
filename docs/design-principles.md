# Design Principles

This project is a lightweight OAuth gateway for routing local or internal OpenAI Responses-compatible requests to the Codex backend. Its design should stay close to a transparent proxy, while making common OpenAI SDK usage work naturally.

## Gateway Role

- The gateway should remain a forwarding and compatibility layer, not a smart client.
- The gateway owns OAuth token acquisition, refresh, persistence, and upstream authorization.
- Client requests should stay as close as possible to the OpenAI Responses API shape.
- Gateway-specific behavior should be minimized and documented when unavoidable.

## OpenAI SDK Compatibility

- The preferred client should be the official OpenAI SDK, configured with this gateway as `base_url`.
- The first compatibility target is limited to:
  - `client.responses.create(...)`
  - `client.responses.create(..., stream=True)`
- Model discovery should use `GET /v1/models` for SDK compatibility and `GET /codex/models` for full Codex metadata.
- The gateway should expose OpenAI-compatible paths for those calls, such as `POST /v1/responses`, while preserving existing local routes where useful.
- The official SDK may send `Authorization: Bearer <api_key>` to the gateway. The gateway should accept this for compatibility, but should not forward that inbound key as the upstream credential.
- Upstream requests should continue to use the locally managed OAuth access token.
- Inbound authorization may later become an optional local access-control mechanism, but it should remain separate from upstream OAuth authorization.

## Proxy Semantics

- Do not add gateway-level retry behavior for response generation requests.
- Do not add new client-policy behavior, such as extra retry or timeout layers, as part of SDK compatibility work.
- Preserve the request lifecycle as much as possible. Cancellation, streaming completion, and upstream failures should be visible to the caller rather than hidden by gateway recovery logic.
- Prefer clear error passthrough and accurate status reporting over automatic recovery.

## Request Handling

- Use OpenAI Responses API field names and structure wherever possible.
- Accept caller-provided fields such as `model`, `input`, `instructions`, `stream`, `reasoning`, `text`, `include`, and future Responses API fields without forcing callers into gateway-specific names.
- Only transform what is required for the Codex upstream contract, such as OAuth headers, input shape compatibility, stateless settings, and required include values.
- Unknown optional fields should be preserved unless they are known to be incompatible with the upstream endpoint.
- Explicit caller-provided `model` values should be forwarded unchanged. The gateway should not silently rewrite unknown or future model ids.

## Model Discovery And Selection

Model handling should preserve the transparent proxy role. The gateway may expose backend model information and choose a default when the caller omits `model`, but it should not become a hidden model router.

### Discovery

- The gateway should query the Codex backend model endpoint directly:

```text
GET https://chatgpt.com/backend-api/codex/models?client_version=...
```

- Do not depend on local Codex client files such as `~/.codex/models_cache.json`. Users may not have Codex installed, and local client caches may be stale or unrelated to this gateway.
- `GET /v1/models` should expose an OpenAI SDK-compatible model list.
- `GET /codex/models` should expose the full Codex backend model metadata.
- `/v1/models` should include only models that are visible to users and supported by the API, such as models where `visibility == "list"` and `supported_in_api == true`.
- `/codex/models` may include hidden or non-API metadata because it is a diagnostic and discovery endpoint.

### Caching

- Model metadata should be cached in the gateway process, not read from the user's Codex installation.
- The default cache TTL should be measured in hours. The agreed baseline is 6 hours:

```text
CODEX_MODELS_CACHE_TTL_SECONDS = 21600
```

- The TTL should be configurable through an environment variable.
- The purpose of the cache is to avoid repeated model-list calls when choosing a default model or serving model discovery endpoints. It is not a routing policy.
- If refreshing the model list fails and a previous in-process cache exists, the gateway may continue using the stale cache.
- If refreshing fails and no cache exists, explicit model requests should still work. Default model selection should fall back to a conservative built-in model.

### Client Version

- The Codex backend requires a `client_version` query parameter for model discovery.
- The gateway should keep a stable built-in default client version that is known to work.
- The client version should be configurable, for example with:

```text
CODEX_MODELS_CLIENT_VERSION
```

- The gateway should not try to infer this value from a local Codex CLI/Desktop installation.
- If the backend rejects the configured version, users or maintainers can update the environment variable or the built-in default.

### Default Model

- If the caller provides `model`, forward it unchanged.
- If the caller omits `model`, choose a default in this order:
  1. `CODEX_GATEWAY_DEFAULT_MODEL`
  2. The first backend model from the cached/fetched model list where `visibility == "list"` and `supported_in_api == true`
  3. A conservative built-in fallback model
- The built-in fallback exists only to keep omitted-model requests usable when model discovery is unavailable.

### Normalization

- The previous broad model normalization behavior should be removed or reduced to a very narrow compatibility shim.
- Do not map arbitrary `gpt-5*`, `codex*`, or unknown model ids to a fixed fallback.
- Do not silently turn unsupported models into different supported models.
- Historical aliases should be avoided unless there is a clear compatibility need and the mapping is documented.
- Model changes observed in `response.model` should be treated as upstream routing or upgrade behavior, not gateway normalization.

## Response Semantics

The goal is not merely to return JSON that the SDK can parse. The returned `response` object should preserve official OpenAI Responses API semantics as much as possible.

- Values obtained from upstream should be returned unchanged whenever possible.
- Values that can be reliably derived may be backfilled.
- Values that cannot be known accurately should not be fabricated.
- Gateway metadata should not be mixed into the Response object. Use headers such as `x-gateway-*` if gateway-specific diagnostics are needed.

Important Response fields:

- `id`: preserve the upstream response id.
- `object`: preserve upstream value; if absent and the object is clearly a Response, `response` may be filled.
- `created_at`: preserve upstream value; do not invent a timestamp unless there is an explicit documented policy.
- `status`: preserve upstream status such as `completed`, `incomplete`, or `failed`.
- `model`: prefer the upstream model; if absent, use the normalized model actually sent upstream.
- `output`: preserve the complete upstream output list, including messages, reasoning items, and tool calls.
- `output_text`: preserve upstream value; if absent, backfill only when it can be accurately reconstructed from output items or SSE text deltas.
- `usage`: preserve upstream usage; do not estimate token counts.
- `error` and `incomplete_details`: preserve upstream failure details.

## Streaming Semantics

- Streaming responses should use SSE events compatible with the official SDK.
- Event types and payload fields should preserve upstream semantics, especially text delta and final response events.
- Text deltas should remain accessible through official SDK event fields such as `event.type` and `event.delta`.
- The final event should contain a complete Response object when upstream provides one.
- If a client disconnects, the gateway should end the corresponding upstream stream cleanly where possible.

## Error Shape

- OpenAI-compatible routes should prefer OpenAI-style error payloads:

```json
{
  "error": {
    "message": "Human-readable error message.",
    "type": "gateway_error",
    "code": "ERROR_CODE"
  }
}
```

- Existing local routes may keep their current error shape for backward compatibility.
- Sensitive values such as OAuth tokens, inbound API keys, prompts, and full model outputs should not be logged in errors.

## Non-Goals

- This project does not aim to implement the full OpenAI API surface.
- Initial SDK compatibility does not need to cover embeddings, files, vector stores, batches, assistants, or administration APIs.
- A custom project-specific client SDK should not be the primary integration path if the official OpenAI SDK can be used directly.
- Retry, circuit-breaking, and gateway-managed rate limiting are not part of the response-generation proxy design.

## Validation

Compatibility work should be validated with real official SDK calls against a local test server:

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

And streaming:

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

The acceptance bar is semantic compatibility, not just successful parsing.
