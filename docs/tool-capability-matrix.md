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

Primary aggregate:

- `execute_test_plan/tool_capability_results.md`
- `execute_test_plan/tool_capability_results.json`

Focused probes:

- `execute_test_plan/web_search/web_search_tool_matrix_results.md`
- `execute_test_plan/image_generation/image_generation_tool_matrix_results.md`
- `execute_test_plan/image_generation/image_generation_edit_matrix_results.md`
- `execute_test_plan/function/function_tool_roundtrip_response1.json`
- `execute_test_plan/function/function_tool_roundtrip_response2.json`
- `execute_test_plan/function/namespace_function_roundtrip_results.md`
- `execute_test_plan/custom/custom_text_tool_roundtrip_response1.json`
- `execute_test_plan/custom/custom_text_tool_roundtrip_response2.json`
- `execute_test_plan/tool_search/tool_search_call_probe_results.md`
- `execute_test_plan/tool_search/tool_search_hit_roundtrip_results.md`
- `execute_test_plan/tool_search/tool_search_empty_result_results.md`
- `execute_test_plan/openai_mcp/openai_mcp_remote_negative_results.md`
- `execute_test_plan/openai_mcp/openai_mcp_remote_negative_response.json`
- `execute_test_plan/openai_mcp/openai_mcp_connector_negative_results.md`
- `execute_test_plan/openai_mcp/openai_mcp_connector_negative_response.json`
- `execute_test_plan/openai_shell/openai_shell_local_results.md`
- `execute_test_plan/openai_shell/openai_shell_local_response1.json`
- `execute_test_plan/openai_shell/openai_shell_hosted_results.md`
- `execute_test_plan/openai_shell/openai_shell_hosted_response.json`
- `execute_test_plan/shell/shell_command_roundtrip_results.md`
- `execute_test_plan/shell/shell_roundtrip_results.md`
- `execute_test_plan/shell/exec_command_roundtrip_results.md`
- `execute_test_plan/apply_patch/apply_patch_function_roundtrip_results.md`
- `execute_test_plan/apply_patch/apply_patch_article_edit_results.md`
- `execute_test_plan/local_shell/local_shell_call_probe_results.md`
- `execute_test_plan/local_shell/local_shell_roundtrip_results.md`

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
