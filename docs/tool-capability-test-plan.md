# Tool Capability Test Plan

This document defines the test plan for probing tool support when requests are
routed through this gateway to the Codex backend.

Scope:

- Client surface: official OpenAI Python SDK through
  `base_url=http://127.0.0.1:8787/v1`.
- Gateway target: ChatGPT OAuth Codex backend path.
- Date of plan: 2026-05-05.
- Main goal: distinguish backend-hosted tools, Codex client-local tools, and
  official OpenAI tools that may not be supported by the Codex backend path.

## Key Principle

Tool support should not be described as one flat capability.

The Codex backend, the Codex CLI, and the official OpenAI Responses API use
overlapping but not identical tool concepts. A test must therefore record:

1. Where the tool shape came from.
2. Whether the tool is expected to be executed by the backend.
3. Whether the request is accepted by the backend.
4. Whether the response contains an observable tool call or tool result.
5. Whether the gateway should expose or document the capability for normal SDK
   users.

## Discovery Sources

There is currently no confirmed standalone backend endpoint that returns a full
tool catalog such as `GET /codex/tools`.

The current discovery strategy is:

```text
+-------------------------------+--------------------------------------------------------------+
| Source                        | Purpose                                                      |
+-------------------------------+--------------------------------------------------------------+
| GET /codex/models             | Read explicit model capability fields.                       |
| Codex CLI source              | Learn how model fields are converted into tool definitions.   |
| Official OpenAI documentation | Compare official Responses API tool shapes.                  |
| Live gateway probes           | Verify what the Codex backend actually accepts and returns.   |
+-------------------------------+--------------------------------------------------------------+
```

Important `/codex/models` fields:

```text
+------------------------------+---------------------------------------------------------------+
| Field                        | Meaning                                                       |
+------------------------------+---------------------------------------------------------------+
| supports_search_tool         | Model may expose the Codex web_search tool.                   |
| web_search_tool_type         | web_search shape: text or text_and_image.                     |
| apply_patch_tool_type        | Codex local apply_patch shape: freeform or function.          |
| experimental_supported_tools | Allowlist for experimental Codex internal tools.              |
| input_modalities             | Input modalities accepted by the model, such as text/image.   |
+------------------------------+---------------------------------------------------------------+
```

## Tool Taxonomy

The test plan separates tools into three categories.

```text
+---------------------------+--------------------------+----------------------+------------------------------+
| Category                  | Executed by backend?     | Normal SDK target?   | Examples                     |
+---------------------------+--------------------------+----------------------+------------------------------+
| Backend-hosted tools      | yes                      | yes, if supported    | web_search                   |
| Official OpenAI tools     | maybe                    | yes                  | function, file_search, shell |
| Codex client-local tools  | no, client executes them | no, not by gateway   | shell_command, apply_patch   |
+---------------------------+--------------------------+----------------------+------------------------------+
```

The gateway should be careful not to promise Codex client-local tools as
backend-hosted tools unless a local executor is deliberately implemented.

## Summary Test Matrix

This table is the high-level plan for all currently visible tool candidates.

```text
+----+-------------------------+-----------------------+------------------+----------------------+-----------------------------+
| ID | Tool                    | Source                | Backend-hosted?  | Probe status         | Main test intent            |
+----+-------------------------+-----------------------+------------------+----------------------+-----------------------------+
| 31 | capability discovery    | /codex/models         | n/a              | supported            | Build per-model tool map.   |
| 32 | web_search variants     | Codex CLI + models    | yes              | supported            | Verify accepted shapes.     |
| 33 | function calling        | OpenAI official API   | model-mediated   | supported            | Verify function call flow.  |
| 34 | function call output    | OpenAI official API   | model-mediated   | supported            | Verify tool result return.  |
| 35 | image_generation        | Codex ToolSpec        | yes              | supported            | Verify image tool support.  |
| 42 | OpenAI MCP remote       | OpenAI official API   | maybe            | rejected             | Verify type=mcp remote edge.|
| 43 | OpenAI MCP connector    | OpenAI official API   | maybe            | rejected             | Verify connector edge.      |
| 40 | OpenAI shell local      | OpenAI official API   | model-mediated   | rejected             | Verify shell_call roundtrip. |
| 41 | OpenAI shell hosted     | OpenAI official API   | maybe            | rejected             | Verify container_auto edge. |
| 36 | shell_command           | Codex CLI local       | no               | supported            | Verify current shell flow.  |
| 37 | shell                   | Codex CLI local       | no               | supported            | Verify array shell flow.    |
| 38 | exec_command            | Codex CLI local       | no               | supported            | Verify unified exec flow.   |
| 13 | file_search             | OpenAI official API   | yes              | skipped              | Verify vector store search. |
| 14 | code_interpreter        | OpenAI official API   | yes              | rejected             | Record unsupported boundary.|
| 15 | computer_use_preview    | OpenAI official API   | yes              | rejected             | Record unsupported boundary.|
| 39 | apply_patch function    | Codex CLI local       | no               | supported            | Verify JSON patch flow.     |
| -- | apply_patch freeform    | Codex CLI local       | no               | supported            | Verify custom patch flow.   |
| -- | namespace function      | OpenAI official API   | model-mediated   | supported            | Verify function grouping.   |
| -- | local_shell             | Codex CLI local       | no               | rejected             | Record removed boundary.    |
| -- | view_image              | Codex CLI local       | no               | source-only          | Do not expose as hosted.    |
| -- | list_dir                | Codex experimental    | no/uncertain     | conditional          | Test only if declared.      |
| -- | test_sync_tool          | Codex experimental    | no/uncertain     | conditional          | Test only if declared.      |
+----+-------------------------+-----------------------+------------------+----------------------+-----------------------------+
```

## Phase 1 - Capability Discovery

Suggested probe:

```text
examples/models/02_capabilities.py
```

Purpose:

- Read `GET /codex/models`.
- Print each visible API model and the tool-related metadata.
- Derive a theoretical tool candidate list per model.
- Record the requested model and any actual model observed in a simple response
  call.

Expected output columns:

```text
+-----------------+----------------------+----------------------+-----------------------+-----------------------------+
| model           | supports_search_tool | web_search_tool_type | apply_patch_tool_type | experimental_supported_tools |
+-----------------+----------------------+----------------------+-----------------------+-----------------------------+
```

Test intent:

- Avoid guessing tool support from a single hard-coded model.
- Capture whether model metadata changes over time.
- Separate model-declared capability from live request behavior.

## Phase 2 - Codex `web_search`

Suggested probe:

```text
examples/tool/web_search/01_matrix.py
```

The Codex CLI source shows that `supports_search_tool` maps to the
`web_search` tool. `web_search_tool_type` further controls whether the tool is
text-only or text-and-image.

Test cases:

```text
+------+----------------------------------------------+----------------------------------------------+
| Case | Tool shape                                   | Test intent                                  |
+------+----------------------------------------------+----------------------------------------------+
| 32A  | {"type":"web_search","external_web_access":true}  | Verify live search is accepted.          |
| 32B  | {"type":"web_search","external_web_access":false} | Verify cached/non-live shape is accepted.|
| 32C  | web_search + search_context_size             | Verify search context size support.          |
| 32D  | web_search + user_location                   | Verify location parameter support.           |
| 32E  | web_search + filters                         | Verify filter parameter support.             |
| 32F  | web_search + search_content_types text/image | Verify text_and_image shape if declared.     |
+------+----------------------------------------------+----------------------------------------------+
```

Observation targets:

- Request accepted or rejected.
- `response.output` contains `web_search_call`.
- `include=["web_search_call.results"]` returns result objects.
- `include=["web_search_call.action.sources"]` returns source URLs.

Current evidence:

```text
+---------+------------------------------------+------------------+
| Include | Existing probe                     | Observation      |
+---------+------------------------------------+------------------+
| results | 11_include_web_search_results_probe | supported        |
| sources | 12_include_web_search_action_sources_probe | supported |
+---------+------------------------------------+------------------+
```

## Phase 3 - Function Calling

Suggested probes:

```text
examples/tool/function/01_roundtrip.py
examples/tool/function/02_namespace_roundtrip.py
```

Function calling is one of the most important official OpenAI tool mechanisms.
It is not the same as a backend-hosted tool. The model emits a function call,
and the client executes the function.

Test cases:

```text
+------+---------------------------------------------+----------------------------------------------+
| Case | Request                                     | Test intent                                  |
+------+---------------------------------------------+----------------------------------------------+
| 33A  | tools=[function], tool_choice=auto          | See whether model may choose a function.     |
| 33B  | tools=[function], tool_choice=required      | See whether backend accepts forced function. |
| 33C  | tools=[function], tool_choice=none          | See whether function calls are suppressed.   |
| 33D  | tool_choice specific function name          | See whether named tool choice is accepted.   |
| 34A  | return function_call_output                 | Verify second turn with tool result.         |
| NS1  | tools=[namespace(function)]                 | Verify official namespace grouping works.    |
+------+---------------------------------------------+----------------------------------------------+
```

Observation targets:

- Request accepted or rejected.
- Response output item type for the function call.
- Function name and JSON arguments.
- Whether a follow-up request with function output is accepted.
- Whether final text uses the supplied tool output.
- Whether a function inside an official namespace can emit a normal
  `function_call` and complete the same roundtrip.

## Phase 4 - Official Hosted Tool Boundary Tests

These tests document compatibility boundaries with official OpenAI Responses
API tools.

### `file_search`

Existing probe:

```text
examples/include/06_file_search_results.py
```

Current status:

- Skipped unless `CODEX_GATEWAY_VECTOR_STORE_ID` is set.
- This is intentional because official `file_search` depends on an existing
  vector store.

Planned test cases:

```text
+------+---------------------------------------------+----------------------------------------------+
| Case | Request                                     | Test intent                                  |
+------+---------------------------------------------+----------------------------------------------+
| 13A  | no vector store id                          | Skip clearly, do not report false failure.   |
| 13B  | valid vector_store_ids                      | Verify whether backend accepts file_search.  |
| 13C  | include=file_search_call.results            | Verify whether search result objects return. |
| 13D  | invalid vector_store_id                     | Verify error shape and passthrough behavior. |
+------+---------------------------------------------+----------------------------------------------+
```

Important interpretation:

- A skipped result does not mean unsupported.
- A backend rejection with a valid vector store would be stronger evidence.
- If accepted, the gateway should document exact vector store requirements.

### `code_interpreter`

Existing probe:

```text
examples/include/07_code_interpreter_outputs.py
```

Current observation:

```text
Unsupported tool type: code_interpreter
```

Current verdict:

- Unsupported in the current Codex backend path.
- Keep as a negative compatibility probe.

### `computer_use_preview`

Existing probe:

```text
examples/include/08_computer_output_image_url.py
```

Current observation:

```text
Unsupported tool type: computer_use_preview
```

Current verdict:

- Unsupported in the current Codex backend path.
- Keep as a negative compatibility probe.

### `image_generation`

Probe:

```text
examples/tool/image_generation/01_basic.py
```

Reason to test:

- Codex `ToolSpec` contains `image_generation`.
- It is not directly controlled by the selected `/codex/models` fields.
- Live probing is needed before documenting support.

Test intent:

- Verify whether the backend accepts an `image_generation` tool shape.
- Observe whether image-generation output items appear.
- Record error message if rejected.

## Phase 5 - OpenAI MCP and Connectors

OpenAI remote MCP servers and connectors use the same official top-level tool
shape:

```json
{"type":"mcp"}
```

Remote MCP uses `server_url`; connectors use `connector_id` and normally also
require user authorization. These are different from local Codex MCP servers
used by Codex itself.

Probes live under:

```text
examples/tool/openai_mcp/
```

Negative test cases:

```text
+----------------------+---------------------------------------------+----------------------------------------------+
| Case                 | Request                                     | Test intent                                  |
+----------------------+---------------------------------------------+----------------------------------------------+
| MCP-REMOTE-NEGATIVE  | type=mcp + unreachable server_url          | Verify remote MCP boundary behavior.         |
| MCP-CONNECTOR-NEG    | type=mcp + fake connector_id/auth          | Verify connector MCP boundary behavior.      |
+----------------------+---------------------------------------------+----------------------------------------------+
```

Current OpenAI MCP live observations:

```text
+----------------------+----------+--------------------------------+
| Tool shape           | Status   | Observation                    |
+----------------------+----------+--------------------------------+
| mcp remote           | rejected | Unsupported tool type: mcp     |
| mcp connector        | rejected | Unsupported tool type: mcp     |
+----------------------+----------+--------------------------------+
```

## Phase 5B - OpenAI Official Shell Tool

The OpenAI official shell tool is distinct from Codex's function-shaped
`shell_command`, `shell`, and `exec_command` tools. Official shell uses a
top-level tool shape:

```json
{"type":"shell","environment":{"type":"local"}}
```

or:

```json
{"type":"shell","environment":{"type":"container_auto"}}
```

Test intent:

- For `environment.type=local`, verify whether Codex backend emits
  `shell_call`, then return `shell_call_output` only for the whitelisted
  `python --version` command.
- For `environment.type=container_auto`, verify whether Codex backend supports,
  rejects, or silently accepts the hosted shell request.
- Record that `skill_reference` belongs to hosted shell/container environments,
  not to a top-level `tools=[{"type":"skill"}]` entry.

Probes live under:

```text
examples/tool/openai_shell/
```

Current official shell live observations:

```text
+----------------------+----------+--------------------------------+
| Tool shape           | Status   | Observation                    |
+----------------------+----------+--------------------------------+
| shell local          | rejected | Unsupported tool type: shell   |
| shell container_auto | rejected | Unsupported tool type: shell   |
+----------------------+----------+--------------------------------+
```

## Phase 6 - Codex Client-Local Tools

These tools are part of Codex CLI's local execution model. They should not be
documented as backend-hosted gateway capabilities unless a gateway-side executor
is intentionally implemented.

```text
+----------------+---------------------------+-----------------------------------------------+
| Tool           | Source                    | Gateway stance                                |
+----------------+---------------------------+-----------------------------------------------+
| shell_command  | Codex CLI local function  | Live supported; client executes locally.      |
| shell          | Codex CLI local function  | Live supported; client executes locally.      |
| exec_command   | Codex CLI local function  | Live supported; client executes locally.      |
| apply_patch    | apply_patch_tool_type     | Live supported; client applies patch locally. |
| local_shell    | Codex ToolSpec            | Live rejected; do not expose as hosted.       |
| view_image     | Codex ToolSpec            | Source-only; requires local file/image access.|
| list_dir       | experimental tools        | Test only if explicitly declared.             |
| test_sync_tool | experimental tools        | Test only if explicitly declared.             |
+----------------+---------------------------+-----------------------------------------------+
```

Test intent:

- Confirm these are not confused with backend-hosted tools.
- Record their protocol shape for future design.
- Avoid accidentally exposing local filesystem or shell capabilities through a
  transparent proxy.

Current `local_shell` live observation:

```text
+-------------+----------+----------------------------------------------+
| Tool        | Status   | Observation                                  |
+-------------+----------+----------------------------------------------+
| local_shell | rejected | The local_shell tool is no longer supported. |
+-------------+----------+----------------------------------------------+
```

Current shell function-tool live observations:

```text
+---------------+---------------------+------------------------------------------+
| Tool          | Status              | Observation                              |
+---------------+---------------------+------------------------------------------+
| shell_command | supported_roundtrip | function_call + function_call_output ok  |
| shell         | supported_roundtrip | function_call + function_call_output ok  |
| exec_command  | supported_roundtrip | function_call + function_call_output ok  |
+---------------+---------------------+------------------------------------------+
```

Current `apply_patch` live observations:

```text
+-----------------------+---------------------+---------------------------------------------+
| Tool shape            | Status              | Observation                                 |
+-----------------------+---------------------+---------------------------------------------+
| custom/freeform       | supported_protocol  | model emits custom_tool_call input patch    |
| function/json         | supported_roundtrip | input patch applied to safe temp file       |
| function/json article | supported_roundtrip | model authored semantic article-edit patch  |
+-----------------------+---------------------+---------------------------------------------+
```

Current wire-layer tool-shape live observations:

```text
+------------------+---------------------+------------------------------------------------+
| Tool shape       | Status              | Observation                                    |
+------------------+---------------------+------------------------------------------------+
| function         | supported_roundtrip | standard function call/output flow works       |
| namespace        | supported_roundtrip | official function namespace emits call         |
| tool_search      | supported_roundtrip | search hit and empty-result flows work         |
| local_shell      | rejected            | backend says local_shell is no longer supported|
| image_generation | supported           | backend returns image_generation_call          |
| web_search       | supported           | backend returns web_search_call                |
| custom/freeform  | supported_roundtrip | custom tool call/output flow works             |
+------------------+---------------------+------------------------------------------------+
```

## Phase 6 - Tool Control Parameters

Tool probes should reuse and cross-reference the existing parameter probes:

```text
+------------------------------+---------------------------------------------------+-------------------------------+
| Parameter                    | Existing probes                                   | Tool-related purpose          |
+------------------------------+---------------------------------------------------+-------------------------------+
| tool_choice=auto             | examples/tool_choice/01_auto.py                   | Model may call tools.         |
| tool_choice=none             | examples/tool_choice/02_none.py                   | Tool calls should be blocked. |
| tool_choice=required         | examples/tool_choice/03_required.py               | Model must call a tool.       |
| tool_choice function object  | examples/tool_choice/04_function_object.py        | Force a named function tool.  |
| tool_choice custom object    | examples/tool_choice/05_custom_object.py          | Force a named custom tool.    |
| tool_choice allowed_tools    | examples/tool_choice/06_allowed_tools_object.py   | Limit allowed tools.          |
| tool_choice image_generation | examples/tool_choice/07_image_generation_object.py| Force image generation.       |
| tool_choice shell object     | examples/tool_choice/08_shell_object.py           | Force official shell tool.    |
| tool_choice mcp object       | examples/tool_choice/09_mcp_object.py             | Force official MCP tool.      |
| tool_choice apply_patch      | examples/tool_choice/10_apply_patch_object.py     | Force apply_patch tool.       |
| parallel_tool_calls          | examples/parallel_tool_calls/                     | Backend accepts parallel flag.|
| include                      | examples/include/                                 | Return extra tool artifacts.  |
+------------------------------+---------------------------------------------------+-------------------------------+
```

## Reporting Format

Every tool probe should print a compact table with these columns:

```text
+------+----------------+----------------+------------+--------------+----------------------+--------------------+
| case | tool           | source         | status     | actual_model | output_item_types    | observation        |
+------+----------------+----------------+------------+--------------+----------------------+--------------------+
```

Recommended status values:

```text
+----------------------+------------------------------------------------------+
| Status               | Meaning                                              |
+----------------------+------------------------------------------------------+
| supported            | Request accepted and expected tool evidence observed. |
| accepted_no_evidence | Request accepted but expected tool evidence absent.   |
| rejected             | Backend or gateway rejected the request.              |
| skipped              | Required external setup was missing.                  |
| source_only          | Tool is local/client-side and not live-probed.         |
+----------------------+------------------------------------------------------+
```

## Final Documentation Target

After the probes are implemented and run, results should be summarized in:

```text
docs/tool-capability-matrix.md
```

That matrix should distinguish:

- Supported backend-hosted tools.
- Accepted but not yet semantically proven tools.
- Official OpenAI tools rejected by the Codex backend path.
- Official OpenAI MCP/connector boundary behavior.
- Codex client-local tools that the gateway should not expose as hosted tools.
