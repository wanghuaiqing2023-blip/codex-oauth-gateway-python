# Client Examples

These examples show how to use this gateway from normal OpenAI Python SDK client code.

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

Configuration:

- `CODEX_GATEWAY_BASE_URL`: default `http://127.0.0.1:8787/v1`
- `CODEX_GATEWAY_API_KEY`: default `local-dummy-key`
- `CODEX_GATEWAY_MODEL`: default `gpt-5.2`
- `CODEX_GATEWAY_PROMPT`: optional prompt override for basic response examples
- `CODEX_GATEWAY_STATE_PROBE_TOKEN`: optional fixed token for state probes
- `CODEX_GATEWAY_IMAGE_URL`: optional image URL or data URL for image input probing
- `CODEX_GATEWAY_VECTOR_STORE_ID`: optional comma-separated vector store ids for file search probing

Gateway model discovery settings:

- `CODEX_GATEWAY_DEFAULT_MODEL`: gateway default when callers omit `model`
- `CODEX_GATEWAY_FALLBACK_MODEL`: fallback when model discovery is unavailable
- `CODEX_MODELS_CLIENT_VERSION`: Codex backend model-list client version
- `CODEX_MODELS_CACHE_TTL_SECONDS`: in-process model-list cache TTL

## Basic

```powershell
python examples/basic/01_health_check.py
python examples/basic/02_response_create.py
python examples/basic/03_stream_response.py
python examples/basic/04_messages_input.py
```

Response examples print both `requested_model` and `actual_model`. The actual model comes from the gateway/upstream response and may differ when the upstream normalizes or routes the request.

## Models

```powershell
python examples/models/01_list_models.py
python examples/models/02_capabilities.py
```

`01_list_models.py` prints both the OpenAI-compatible model list from `/v1/models` and the richer Codex metadata from `/codex/models`.

## State

```powershell
python examples/previous_response_id/01_probe.py
python examples/conversation/01_probe.py
```

These are experimental probes. In the current stateless Codex path, `previous_response_id` is usually rejected by the backend, and `/v1/conversations` is not implemented by this gateway.

## Include

```powershell
python examples/include/01_reasoning_encrypted_content.py
python examples/include/02_message_input_image_url.py
python examples/include/03_output_text_logprobs.py
python examples/include/04_web_search_results.py
python examples/include/05_web_search_action_sources.py
python examples/include/06_file_search_results.py
python examples/include/07_code_interpreter_outputs.py
python examples/include/08_computer_output_image_url.py
```

The include probes verify official include paths such as `reasoning.encrypted_content`, `message.output_text.logprobs`, `web_search_call.results`, and hosted-tool artifact fields. Some include values depend on a matching tool call; a successful response without the requested field is recorded separately from backend rejection.

## Parameters

Each parameter has its own directory so users can find probes by the exact OpenAI Responses API field name.

```powershell
python examples/max_output_tokens/01_basic.py
python examples/temperature/01_basic.py
python examples/top_p/01_basic.py
python examples/text_format/01_json_schema.py
python examples/instructions/01_basic.py
python examples/parallel_tool_calls/01_false.py
python examples/parallel_tool_calls/02_true.py
python examples/reasoning/01_summary_metadata.py
python examples/reasoning/02_effort_summary_matrix.py
python examples/text_verbosity/01_matrix.py
python examples/metadata/01_basic.py
python examples/service_tier/01_omitted.py
python examples/service_tier/02_priority.py
python examples/service_tier/03_auto.py
python examples/service_tier/04_default.py
python examples/service_tier/05_flex.py
python examples/service_tier/06_scale.py
python examples/service_tier/07_fast_alias.py
python examples/prompt_cache_retention/01_no_key_omitted.py
python examples/prompt_cache_retention/02_no_key_in_memory.py
python examples/prompt_cache_retention/03_no_key_24h.py
python examples/prompt_cache_retention/04_with_key_omitted.py
python examples/prompt_cache_retention/05_with_key_in_memory.py
python examples/prompt_cache_retention/06_with_key_24h.py
python examples/stream_options/01_stream_omitted_options.py
python examples/stream_options/02_stream_include_obfuscation_true.py
python examples/stream_options/03_stream_include_obfuscation_false.py
python examples/stream_options/04_non_stream_include_obfuscation_false.py
python examples/background/01_omitted.py
python examples/background/02_false.py
python examples/background/03_true.py
python examples/background/04_true_with_stream.py
python examples/context_management/01_omitted.py
python examples/context_management/02_empty_list.py
python examples/context_management/03_compaction.py
python examples/context_management/04_compaction_threshold.py
python examples/safety_identifier/01_omitted.py
python examples/safety_identifier/02_basic.py
python examples/user/01_omitted.py
python examples/user/02_basic.py
python examples/top_logprobs/01_omitted.py
python examples/top_logprobs/02_zero.py
python examples/top_logprobs/03_two.py
python examples/top_logprobs/04_two_with_include.py
python examples/truncation/01_omitted.py
python examples/truncation/02_auto.py
python examples/truncation/03_disabled.py
python examples/store/01_omitted.py
python examples/store/02_false.py
python examples/store/03_true.py
python examples/extra_body/01_text_format.py
python examples/max_tool_calls/01_zero.py
python examples/max_tool_calls/02_one.py
python examples/max_tool_calls/03_two.py
```

Current broad observations:

- `instructions`, `text.format`, `text.verbosity`, `reasoning.effort`, `reasoning.summary`, `context_management` compaction, `parallel_tool_calls`, and `service_tier="priority"` have shown positive behavior in probes.
- Explicit `temperature`, `top_p`, `max_output_tokens`, `metadata`, `prompt_cache_retention`, `stream_options`, `background`, `safety_identifier`, `user`, `top_logprobs`, `truncation`, and `max_tool_calls` have been rejected by the current Codex backend path.
- `store` is special: the gateway accepts official client shapes but forces upstream `store=false`, because the Codex backend requires that value.
- `extra_body` is an SDK escape hatch, not a backend parameter. The probe injects a known supported body field, `text.format`, and checks whether structured output takes effect.

## Tool

Tool probes live under `examples/tool/`, grouped by exact tool family rather than by a runner.

```powershell
python examples/tool/web_search/01_matrix.py
python examples/tool/image_generation/01_basic.py
python examples/tool/image_generation/02_tool_matrix.py
python examples/tool/image_generation/03_edit_matrix.py
python examples/tool/function/01_roundtrip.py
python examples/tool/function/02_namespace_roundtrip.py
python examples/tool/custom/01_text_tool.py
python examples/tool/custom/02_regex_grammar.py
python examples/tool/custom/03_text_tool_roundtrip.py
python examples/tool/tool_search/01_call.py
python examples/tool/tool_search/02_hit_roundtrip.py
python examples/tool/tool_search/03_empty_result_roundtrip.py
python examples/tool/shell_function/01_shell_command_roundtrip.py
python examples/tool/shell_function/02_shell_roundtrip.py
python examples/tool/shell_function/03_exec_command_roundtrip.py
python examples/tool/local_shell/01_call.py
python examples/tool/local_shell/02_roundtrip.py
python examples/tool/openai_shell/01_local.py
python examples/tool/openai_shell/02_hosted.py
python examples/tool/openai_mcp/01_remote_negative.py
python examples/tool/openai_mcp/02_connector_negative.py
python examples/tool/apply_patch/01_freeform_probe.py
python examples/tool/apply_patch/02_function_roundtrip.py
python examples/tool/apply_patch/03_article_edit.py
```

Tool examples distinguish backend-hosted tools from model-mediated local tools:

- `web_search` and `image_generation` are backend-hosted in the current Codex backend path.
- `function`, `custom`, `tool_search`, shell-function shapes, and `apply_patch` are model-mediated. The model emits a call and the client application owns execution.
- Official top-level `shell` and `mcp` tool shapes are negative probes in the current Codex backend path.
- Legacy `local_shell` is retained only as a compatibility boundary probe.
