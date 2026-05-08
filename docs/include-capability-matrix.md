# Include Capability Matrix

This document records the current probe results for the official OpenAI
Responses API `include` values when routed through this gateway to the Codex
backend.

Scope:

- Client surface: official OpenAI Python SDK through `base_url=http://127.0.0.1:8787/v1`.
- Gateway target: ChatGPT OAuth Codex backend path.
- Date of observations: 2026-05-02.
- Probe files: `examples/include/`.

## Summary Matrix

The table below intentionally uses short ASCII values so the columns stay
aligned in source form.

```text
+----+-----------------------------------------+-----------------------------------------------+------------------+------------------------+----------------------------+------------------------------+
| ID | include                                 | probe                                         | dependency       | Codex CLI evidence     | backend observation        | current verdict              |
+----+-----------------------------------------+-----------------------------------------------+------------------+------------------------+----------------------------+------------------------------+
| 01 | reasoning.encrypted_content             | 01_reasoning_encrypted_content                | none             | yes                    | supported                  | supported                    |
| 02 | message.input_image.image_url           | 02_message_input_image_url                    | image input      | partial                | no image_url echo          | echo unsupported             |
| 03 | message.output_text.logprobs            | 03_output_text_logprobs                       | model support    | no                     | rejected                   | unsupported in this path     |
| 04 | web_search_call.results                 | 04_web_search_results                         | web_search tool  | yes                    | supported                  | supported                    |
| 05 | web_search_call.action.sources          | 05_web_search_action_sources                  | web_search tool  | yes                    | supported                  | supported                    |
| 06 | file_search_call.results                | 06_file_search_results                        | vector store     | no                     | skipped                    | not tested                   |
| 07 | code_interpreter_call.outputs           | 07_code_interpreter_outputs                   | code tool        | no                     | unsupported tool type      | not applicable               |
| 08 | computer_call_output.output.image_url   | 08_computer_output_image_url                  | computer tool    | no                     | unsupported tool type      | not applicable               |
+----+-----------------------------------------+-----------------------------------------------+------------------+------------------------+----------------------------+------------------------------+
```

## Detailed Results

### 01 - `reasoning.encrypted_content`

- Probe: `examples/include/01_reasoning_encrypted_content.py`
- Tool dependency: none.
- Codex CLI evidence: yes. Codex CLI adds `reasoning.encrypted_content` to
  `include` when reasoning is present.
- Backend observation: supported. The response includes an `encrypted_content`
  field, observed at paths such as `$.output[0].encrypted_content`.
- Gateway policy: this include is required for the current stateless Codex
  backend flow and should remain automatically included.

### 02 - `message.input_image.image_url`

- Probe: `examples/include/02_message_input_image_url.py`
- Tool dependency: none; this depends on image input, not a tool.
- Codex CLI evidence: partial.
  - Codex CLI has a real `input_image` / `image_url` input path.
  - Codex CLI has not been observed to request
    `include=["message.input_image.image_url"]`.
- Backend observation: a valid image URL request can succeed while the response
  does not echo the input `image_url`.
- Current status: image input should be tested separately from include echo.
  The include option itself is judged by whether the response returns the input
  image URL.
- Current verdict: the current Codex backend path does not implement the
  official `message.input_image.image_url` include echo semantics.

### 03 - `message.output_text.logprobs`

- Probe: `examples/include/03_output_text_logprobs.py`
- Tool dependency: none.
- Codex CLI evidence: no. No Codex CLI usage of `logprobs` has been found.
- Backend observation: rejected in earlier probing with:

```text
logprobs are not supported with reasoning models.
```

- Important nuance: the gateway currently sends reasoning defaults to the
  Codex backend. Therefore the narrow conclusion is:

```text
Current Codex model + current gateway reasoning behavior rejects logprobs.
```

- Current verdict: unsupported in this path. Do not generalize this to all
  OpenAI Responses API models.

### 04 - `web_search_call.results`

- Probe: `examples/include/04_web_search_results.py`
- Tool dependency: `web_search` tool.
- Codex CLI evidence: yes. Codex CLI defines a `web_search` tool shape.
- Tool shape that worked:

```json
{"type": "web_search", "external_web_access": true}
```

- Tool shape that failed earlier:

```json
{"type": "web_search_preview"}
```

- Backend observation: supported. The response included search result objects,
  observed at:

```text
$.output[1].results
```

- Current verdict: supported when using the Codex CLI-compatible `web_search`
  tool shape.

### 05 - `web_search_call.action.sources`

- Probe: `examples/include/05_web_search_action_sources.py`
- Tool dependency: `web_search` tool.
- Codex CLI evidence: yes. Same `web_search` tool shape as probe 11.
- Backend observation: supported. The response included source URL objects,
  observed at:

```text
$.output[1].action.sources
```

- Current verdict: supported when using the Codex CLI-compatible `web_search`
  tool shape.

### 06 - `file_search_call.results`

- Probe: `examples/include/06_file_search_results.py`
- Tool dependency: `file_search` tool plus an existing vector store.
- Codex CLI evidence: no direct matching Codex CLI tool shape has been
  established.
- Backend observation: skipped because `CODEX_GATEWAY_VECTOR_STORE_ID` was not
  set.
- Reason for skipping: this gateway currently does not implement the official
  OpenAI files/vector-stores API surface needed to create the prerequisite
  resources.
- Current verdict: not tested. Keep as an optional probe only for users who
  already have a valid vector store id.

### 07 - `code_interpreter_call.outputs`

- Probe: `examples/include/07_code_interpreter_outputs.py`
- Tool dependency: official Code Interpreter tool.
- Codex CLI evidence: no. Codex CLI public tool definitions do not show a
  `code_interpreter` tool.
- Tool shape tested:

```json
{"type": "code_interpreter", "container": {"type": "auto"}}
```

- Backend observation: structured rejection was observed:

```text
Unsupported tool type: code_interpreter
```

- Current verdict: not applicable to the current Codex backend path. This is
  not a Codex CLI-aligned tool shape, and the observed backend explicitly
  rejects the official `code_interpreter` tool type.

### 08 - `computer_call_output.output.image_url`

- Probe: `examples/include/08_computer_output_image_url.py`
- Tool dependency: official Computer Use tool loop.
- Codex CLI evidence: no. Codex CLI public tool definitions do not show
  `computer_use_preview`, `computer_call`, or `computer_call_output`.
- Official tool shape tested:

```json
{
  "type": "computer_use_preview",
  "display_width": 1024,
  "display_height": 768,
  "environment": "browser"
}
```

- Backend observations:
  - Official shape with `truncation="auto"` caused a transport reset.
  - Tool-type isolation without `truncation` returned:

```text
Unsupported tool type: computer_use_preview
```

- Current verdict: not applicable to the current Codex backend path. The
  official Computer Use tool chain is not accepted by the observed backend.

## Design Implications

```text
+-----------------------------+------------------------------------------------------------+
| Area                        | Implication                                                |
+-----------------------------+------------------------------------------------------------+
| Gateway role                | Keep transparent proxy semantics; avoid inventing support. |
| Codex CLI-backed features   | Prefer Codex CLI tool shapes when adapting to backend.     |
| Official-only tool features | Treat as compatibility probes unless backend accepts them. |
| Web search                  | Supported with Codex web_search, not web_search_preview.   |
| Image input                 | Test vision input separately from include echo semantics.  |
| File/code/computer tools    | Do not promote as supported without stronger evidence.     |
+-----------------------------+------------------------------------------------------------+
```

## References

- OpenAI Responses API include list:
  <https://platform.openai.com/docs/api-reference/responses/create?api-mode=responses>
- OpenAI Python SDK `ResponseIncludable`:
  <https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_includable.py>
- Codex CLI tool definitions:
  <https://raw.githubusercontent.com/openai/codex/main/codex-rs/tools/src/tool_spec.rs>
- OpenAI Computer Use guide:
  <https://platform.openai.com/docs/guides/tools-computer-use>
