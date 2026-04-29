# To Do List

## High Priority

- Add an automated real OpenAI SDK compatibility smoke test.
  - Cover `client.responses.create(...)`.
  - Cover `client.responses.create(..., stream=True)`.
  - Cover `client.models.list()`.
  - Keep it separate from normal unit tests because it needs a real OAuth token and backend access.

- Improve streaming final response semantics.
  - Preserve upstream final response fields.
  - Consider backfilling final `output_text` from accumulated text deltas when upstream final response has an empty value.
  - Keep streamed delta behavior unchanged for SDK compatibility.

- Harden error mapping for OpenAI-compatible routes.
  - Normalize upstream `{"detail": ...}` and `{"error": ...}` consistently.
  - Preserve status codes and useful upstream details.
  - Avoid leaking tokens, local API keys, full prompts, or full outputs.

- Finish model handling cleanup.
  - Keep explicit `model` values as passthrough.
  - Use `CODEX_GATEWAY_DEFAULT_MODEL`, backend model list, and fallback only when `model` is omitted.
  - Keep the in-process model cache TTL configurable.
  - Avoid reintroducing broad model normalization.

## Medium Priority

- Add packaging metadata.
  - Introduce `pyproject.toml`.
  - Provide console entry points for starting the gateway and running OAuth login.
  - Keep `requirements.txt` or replace it with a documented install path.

- Improve token storage security.
  - Document that tokens are currently stored as local JSON.
  - Restrict token file permissions where supported.
  - Consider optional OS credential-store integration later.

- Improve diagnostics.
  - Add structured logs for route, status, upstream status, request id, and model.
  - Avoid logging sensitive request or response bodies by default.
  - Add a debug mode for local troubleshooting.

- Expand examples.
  - Add an omitted-model example to demonstrate default model selection.
  - Add an error-handling example.
  - Add a minimal curl example for `/v1/models` and `/codex/models`.

- Improve documentation.
  - Add an architecture overview.
  - Document proxy semantics and non-goals in README.
  - Document the model discovery endpoint and cache behavior.
  - Add Windows, Linux, and macOS quickstart notes.

## Lower Priority

- Add optional local access control.
  - Allow validating inbound `Authorization: Bearer <local key>`.
  - Keep inbound local keys separate from upstream OAuth tokens.
  - Default should remain easy for local development.

- Add graceful shutdown notes or helper scripts.
  - Document how to find and stop a process occupying the gateway port.
  - Consider a small dev script for starting the gateway on an alternate port.

- Add broader test coverage.
  - Malformed SSE.
  - Upstream non-JSON errors.
  - Model endpoint stale-cache fallback.
  - Concurrent token refresh behavior.
  - Client disconnect during streaming.

- Clean up legacy README artifacts.
  - Replace mojibake tree characters in the project layout block.
  - Keep examples and route list synchronized.

## Non-Goals To Preserve

- Do not add gateway-level retry for response generation requests.
- Do not make the gateway a hidden model router.
- Do not depend on local Codex client cache files.
- Do not implement the full OpenAI API surface unless there is a clear need.
