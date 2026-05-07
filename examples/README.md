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
python examples/06_previous_response_id_probe.py
python examples/07_conversation_probe.py
python examples/08_include_reasoning_encrypted_content_probe.py
python examples/09_include_message_input_image_url_probe.py
python examples/10_include_output_text_logprobs_probe.py
python examples/11_include_web_search_results_probe.py
python examples/12_include_web_search_action_sources_probe.py
python examples/13_include_file_search_results_probe.py
python examples/14_include_code_interpreter_outputs_probe.py
python examples/15_include_computer_output_image_url_probe.py
python examples/16_param_max_output_tokens_probe.py
python examples/17_param_temperature_probe.py
python examples/18_param_top_p_probe.py
python examples/19_param_text_format_probe.py
python examples/20_param_instructions_probe.py
python examples/21_param_tool_choice_auto_probe.py
python examples/22_param_tool_choice_none_probe.py
python examples/23_param_tool_choice_required_probe.py
python examples/24_param_parallel_tool_calls_false_probe.py
python examples/25_param_parallel_tool_calls_true_probe.py
python examples/26_reasoning_summary_metadata_probe.py
python examples/27_param_reasoning_effort_summary_matrix_probe.py
python examples/28_param_text_verbosity_probe.py
python examples/29_param_service_tier_probe.py
python examples/30_param_metadata_probe.py
```

Configuration:

- `CODEX_GATEWAY_BASE_URL`: default `http://127.0.0.1:8787/v1`
- `CODEX_GATEWAY_API_KEY`: default `local-dummy-key`
- `CODEX_GATEWAY_MODEL`: default `gpt-5.2`
- `CODEX_GATEWAY_PROMPT`: optional prompt override for examples 02 and 03
- `CODEX_GATEWAY_STATE_PROBE_TOKEN`: optional fixed token for examples 06 and 07
- `CODEX_GATEWAY_IMAGE_URL`: optional image URL or data URL for example 09 image probing
- `CODEX_GATEWAY_VECTOR_STORE_ID`: optional comma-separated vector store ids for example 13

Gateway model discovery settings:

- `CODEX_GATEWAY_DEFAULT_MODEL`: gateway default when callers omit `model`
- `CODEX_GATEWAY_FALLBACK_MODEL`: fallback when model discovery is unavailable
- `CODEX_MODELS_CLIENT_VERSION`: Codex backend model-list client version
- `CODEX_MODELS_CACHE_TTL_SECONDS`: in-process model-list cache TTL

Response examples print both `requested_model` and `actual_model`. The actual model comes from the gateway/upstream response and may differ when the upstream normalizes or routes the request.

`05_list_models.py` prints both the OpenAI-compatible model list from `/v1/models` and the richer Codex metadata from `/codex/models`.

`06_previous_response_id_probe.py` makes two real response calls. The second call sends `previous_response_id=response1.id`. In the current stateless Codex path, the expected observation is usually `Unsupported parameter: previous_response_id`; the script treats that as a successful probe result, not a recommended client pattern.

`07_conversation_probe.py` follows the official Conversations API flow: first call `client.conversations.create()` to obtain `conversation.id`, then pass that id to two `client.responses.create(...)` calls and observe whether a one-time token can be recovered. In the current gateway this is expected to report that `/v1/conversations` is not implemented. This is an experimental probe, not a recommended client pattern.

`08_include_reasoning_encrypted_content_probe.py` verifies whether `include=["reasoning.encrypted_content"]` returns encrypted reasoning state from the real gateway/backend path.

`09_include_message_input_image_url_probe.py` sends a public dog image as `input_image.image_url` and asks the model to describe it. It also requests `include=["message.input_image.image_url"]`, so the output separates image-understanding evidence from whether the official include echo was returned.

`10_include_output_text_logprobs_probe.py` verifies whether `include=["message.output_text.logprobs"]` returns output token log probabilities, or whether the backend rejects that include for the selected model.

`11_include_web_search_results_probe.py` uses the Codex CLI web search tool shape (`{"type": "web_search", "external_web_access": true}`) and verifies whether `include=["web_search_call.results"]` returns search result objects.

`12_include_web_search_action_sources_probe.py` uses the Codex CLI web search tool shape (`{"type": "web_search", "external_web_access": true}`) and verifies whether `include=["web_search_call.action.sources"]` returns web search action sources.

`13_include_file_search_results_probe.py` verifies whether `include=["file_search_call.results"]` returns file search result objects when `CODEX_GATEWAY_VECTOR_STORE_ID` is set. Without that environment variable, the probe prints `skipped`.

`14_include_code_interpreter_outputs_probe.py` uses the official Code Interpreter tool shape (`{"type": "code_interpreter", "container": {"type": "auto"}}`) and verifies whether `include=["code_interpreter_call.outputs"]` returns execution outputs.

`15_include_computer_output_image_url_probe.py` is a small negative probe for the official Computer Use tool shape (`{"type": "computer_use_preview", ...}`). It first sends the official `truncation="auto"` shape, then retries without `truncation` to isolate whether the backend recognizes the tool type. It does not run a full computer-use loop.

`16_param_max_output_tokens_probe.py` verifies whether `max_output_tokens` is accepted and whether the response exposes length-limit semantics through short output, status, `incomplete_details`, or usage fields.

`17_param_temperature_probe.py` verifies whether `temperature` is accepted by the Codex backend. This is an official Responses API sampling control, but it is not present in the public Codex CLI `ResponsesApiRequest` shape observed during this project.

`18_param_top_p_probe.py` verifies whether `top_p` is accepted by the Codex backend. This is an official Responses API sampling control, but it is not present in the public Codex CLI `ResponsesApiRequest` shape observed during this project.

`19_param_text_format_probe.py` verifies whether official structured output via `text.format` is accepted. This parameter has a close Codex CLI source-code analogue through `TextControls.format`.

`20_param_instructions_probe.py` verifies whether caller-provided `instructions` are accepted and affect the response. This parameter is present in the public Codex CLI `ResponsesApiRequest` shape.

`21_param_tool_choice_auto_probe.py` verifies whether explicit `tool_choice="auto"` is accepted together with the Codex-compatible `web_search` tool shape. This parameter is present in the public Codex CLI `ResponsesApiRequest` shape.

`22_param_tool_choice_none_probe.py` verifies whether `tool_choice="none"` is accepted and suppresses tool calls when a Codex-compatible `web_search` tool is available.

`23_param_tool_choice_required_probe.py` verifies whether `tool_choice="required"` is accepted and forces a tool call when a Codex-compatible `web_search` tool is available.

`24_param_parallel_tool_calls_false_probe.py` verifies whether `parallel_tool_calls=false` is accepted with a forced Codex-compatible `web_search` tool call.

`25_param_parallel_tool_calls_true_probe.py` verifies whether `parallel_tool_calls=true` is accepted with a forced Codex-compatible `web_search` tool call. These probes do not assert real parallel execution; they only verify parameter acceptance and response structure.

`26_reasoning_summary_metadata_probe.py` reads `/codex/models` and prints the reasoning metadata fields used to plan `reasoning.effort` and `reasoning.summary` probes, including `supported_reasoning_levels`, `default_reasoning_level`, `supports_reasoning_summaries`, and `default_reasoning_summary`.

`27_param_reasoning_effort_summary_matrix_probe.py` reads the selected model's supported reasoning efforts from `/codex/models`, then runs each supported effort against `reasoning.summary` values `auto`, `concise`, and `detailed`. It records request acceptance plus visible reasoning summary counts and character lengths, so the probe can distinguish transport support from observable summary behavior.

`28_param_text_verbosity_probe.py` reads `support_verbosity` and `default_verbosity` from `/codex/models`, then verifies whether `text.verbosity` values `low`, `medium`, and `high` are accepted. It keeps `reasoning={"effort":"medium","summary":"auto"}` fixed, records observed upstream actual models plus output character, word, and line counts, then prints each full output so the verbosity effect can be inspected directly.

`29_param_service_tier_probe.py` tests `service_tier` wire values on `/responses`: omitted standard speed, `priority`, official OpenAI values `auto/default/flex`, and the Codex CLI/UI alias `fast`. It does not use `/codex/models` tier metadata as current speed state, because those fields are capability/display metadata rather than a request-state API.

`30_param_metadata_probe.py` verifies whether official Responses API `metadata` is accepted, rejected, or echoed by the Codex backend path. Codex CLI source code exposes private `client_metadata`, not the official `metadata` field, so this probe records the compatibility boundary explicitly.

Example:

```powershell
$env:CODEX_GATEWAY_MODEL = "gpt-5.2"
$env:CODEX_GATEWAY_PROMPT = "Reply exactly: hello-from-gateway"
python examples/02_response_create.py
```
