# Tool Capability Matrix

This document summarizes the tool-capability probes run through this gateway
against the Codex backend.

Last refreshed: 2026-05-07

## Scope

The matrix covers tools visible from three sources:

- OpenAI-compatible Responses API requests sent by the official Python SDK.
- Codex backend model metadata exposed by `GET /codex/models`.
- Codex CLI source code under `codex/codex-rs/tools/src`.

The gateway is a transparent proxy. A tool is only considered backend-hosted
when the Codex backend itself executes or materializes the tool result. Tools
such as `shell_command` and `apply_patch` are model-mediated local tools: the
model emits a call, and the client executes it.

## `/codex/models` Tool Metadata

Current API-visible model metadata shows the same high-level tool candidates
for all listed models:

```text
+--------------+--------+----------------+-------------+--------------------+-------------------------------+
| Model        | Search | Search type    | Apply patch | Experimental tools | Derived tools                 |
+--------------+--------+----------------+-------------+--------------------+-------------------------------+
| gpt-5.5      | true   | text_and_image | freeform    | []                 | web_search, apply_patch, image|
| gpt-5.4      | true   | text_and_image | freeform    | []                 | web_search, apply_patch, image|
| gpt-5.4-mini | true   | text_and_image | freeform    | []                 | web_search, apply_patch, image|
| gpt-5.3-codex| true   | text           | freeform    | []                 | web_search, apply_patch, image|
| gpt-5.2      | true   | text           | freeform    | []                 | web_search, apply_patch, image|
+--------------+--------+----------------+-------------+--------------------+-------------------------------+
```

Interpretation:

- `web_search` is explicitly supported by model metadata.
- `apply_patch` is advertised as `freeform`, which is a local client executor
  pattern, not a backend-hosted patch executor.
- `experimental_supported_tools` is currently empty, so `list_dir` and
  `test_sync_tool` are not active for the tested models.
- Image input is available from `input_modalities`, while `image_generation`
  support is established by live probing.

## Wire-Layer Coverage

The Codex source defines these top-level tool wire shapes in `ToolSpec`. All
practical shapes have now been probed.

```text
+------------------+---------------------+----------------------+-----------------------------------------------+
| Tool shape       | Live status         | Backend-hosted?      | Evidence                                      |
+------------------+---------------------+----------------------+-----------------------------------------------+
| function         | supported_roundtrip | model-mediated       | function_call + function_call_output works   |
| namespace        | supported_roundtrip | model-mediated       | official function namespace emits call       |
| tool_search      | supported_roundtrip | model-mediated/local | hit and empty-result flows work              |
| local_shell      | rejected            | no                   | backend says it is no longer supported       |
| image_generation | supported           | yes                  | backend returns image_generation_call        |
| web_search       | supported           | yes                  | backend returns web_search_call              |
| custom/freeform  | supported_roundtrip | model-mediated       | custom_tool_call + output works              |
+------------------+---------------------+----------------------+-----------------------------------------------+
```

OpenAI official top-level `shell` is tested separately because it is not the
same as Codex's function-shaped shell tools. Current Codex backend behavior is
to reject both `environment.type=local` and `environment.type=container_auto`
with `Unsupported tool type: shell`.

OpenAI official MCP and connector tools are also tested separately because they
use the top-level `type=mcp` tool shape. The negative probes do not contact a
real MCP server or real user connector; they only record whether the Codex
backend recognizes the official MCP shape.

## Tool Capability Matrix

```text
+----------------------------+--------------------------+---------------------+----------------------+----------------------------------------------+
| Tool / capability          | Category                 | Live status         | Main probe           | Gateway stance                               |
+----------------------------+--------------------------+---------------------+----------------------+----------------------------------------------+
| /codex/models discovery    | metadata                 | supported           | tool_capability      | expose for capability inspection             |
| web_search                 | backend-hosted           | supported           | web_search_matrix    | OpenAI SDK users can use Codex shape         |
| web_search results include | backend-hosted artifact  | supported           | include probes       | document include behavior                    |
| image_generation           | backend-hosted           | supported           | image_generation     | supported; document accepted parameters      |
| image input                | model input modality     | supported           | image input probe    | supported for understanding image content    |
| function                   | OpenAI model-mediated    | supported_roundtrip | function_roundtrip   | support as normal SDK function calling       |
| namespace                  | OpenAI function grouping | supported_roundtrip | namespace_roundtrip  | support as a function grouping wrapper       |
| custom text                | OpenAI custom tool       | supported_roundtrip | custom_text          | support model-generated custom input         |
| custom regex grammar       | OpenAI custom grammar    | supported_protocol  | custom_regex         | support grammar-constrained custom input     |
| tool_search                | Codex deferred tool flow | supported_roundtrip | tool_search probes   | support when deferred tools exist            |
| OpenAI MCP remote          | OpenAI MCP tool          | rejected            | openai_mcp_remote    | unsupported in current Codex backend path    |
| OpenAI MCP connector       | OpenAI MCP connector     | rejected            | openai_mcp_connector | unsupported in current Codex backend path    |
| OpenAI shell local         | OpenAI shell tool        | rejected            | openai_shell_local   | unsupported in current Codex backend path    |
| OpenAI shell hosted        | OpenAI hosted shell      | rejected            | openai_shell_hosted  | unsupported in current Codex backend path    |
| shell_command              | Codex local function     | supported_roundtrip | shell_command        | client must execute; not backend-hosted      |
| shell                      | Codex local function     | supported_roundtrip | shell                | client must execute; not backend-hosted      |
| exec_command               | Codex local function     | supported_roundtrip | exec_command         | client must execute; not backend-hosted      |
| apply_patch custom/freeform| Codex local custom       | supported_protocol  | apply_patch_probe    | client must apply; validate strictly         |
| apply_patch function/json  | Codex local function     | supported_roundtrip | apply_patch_function | client must apply; validate strictly         |
| apply_patch article edit   | Codex local function     | supported_roundtrip | article_edit         | model can author semantic patches            |
| file_search                | OpenAI hosted tool       | skipped             | file_search include  | needs real vector_store_id before verdict    |
| code_interpreter           | OpenAI hosted tool       | rejected            | code_interpreter     | unsupported in current Codex backend path    |
| computer_use_preview       | OpenAI hosted tool       | rejected            | computer_use         | unsupported in current Codex backend path    |
| local_shell                | Codex local tool         | rejected            | local_shell          | do not expose; backend removed this shape    |
| view_image                 | Codex local function     | source_only         | source review        | client-local only; not a backend capability  |
| list_dir                   | Codex experimental local | not_active          | /codex/models        | test only if metadata declares it            |
| test_sync_tool             | Codex experimental local | not_active          | /codex/models        | test only if metadata declares it            |
+----------------------------+--------------------------+---------------------+----------------------+----------------------------------------------+
```

## Result Files

The old aggregate runner under `execute_test_plan/` has been removed. Tool
probes now live under `examples/tool/`, grouped by exact tool family:

- `examples/tool/web_search/01_matrix.py`
- `examples/tool/image_generation/01_basic.py`
- `examples/tool/image_generation/02_tool_matrix.py`
- `examples/tool/image_generation/03_edit_matrix.py`
- `examples/tool/function/01_roundtrip.py`
- `examples/tool/function/02_namespace_roundtrip.py`
- `examples/tool/custom/01_text_tool.py`
- `examples/tool/custom/02_regex_grammar.py`
- `examples/tool/custom/03_text_tool_roundtrip.py`
- `examples/tool/tool_search/01_call.py`
- `examples/tool/tool_search/02_hit_roundtrip.py`
- `examples/tool/tool_search/03_empty_result_roundtrip.py`
- `examples/tool/openai_mcp/01_remote_negative.py`
- `examples/tool/openai_mcp/02_connector_negative.py`
- `examples/tool/openai_shell/01_local.py`
- `examples/tool/openai_shell/02_hosted.py`
- `examples/tool/shell_function/01_shell_command_roundtrip.py`
- `examples/tool/shell_function/02_shell_roundtrip.py`
- `examples/tool/shell_function/03_exec_command_roundtrip.py`
- `examples/tool/apply_patch/01_freeform_probe.py`
- `examples/tool/apply_patch/02_function_roundtrip.py`
- `examples/tool/apply_patch/03_article_edit.py`
- `examples/tool/local_shell/01_call.py`
- `examples/tool/local_shell/02_roundtrip.py`

## Completion Notes

The practical tool test surface is now complete for the current account and
model metadata, with two explicit boundaries:

- `file_search` cannot receive a final supported/rejected verdict until a real
  `CODEX_GATEWAY_VECTOR_STORE_ID` is available.
- `list_dir` and `test_sync_tool` are not active because current
  `/codex/models` metadata reports no experimental tools.

For gateway design, the most important distinction remains:

```text
+----------------------+--------------------------------------------------------+
| Tool family          | Required execution owner                               |
+----------------------+--------------------------------------------------------+
| web_search           | Codex backend                                          |
| image_generation     | Codex backend                                          |
| function/custom      | client application                                     |
| OpenAI MCP           | not supported by this backend path                     |
| OpenAI shell         | not supported by this backend path                     |
| shell/apply_patch    | client application with strict local safety checks     |
| code_interpreter     | not supported by this backend path                     |
| computer_use_preview | not supported by this backend path                     |
+----------------------+--------------------------------------------------------+
```
