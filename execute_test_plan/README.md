# Execute Test Plan

This directory contains runnable probes and generated results for the tool
capability test plan.

Files are grouped by tested tool family:

- `web_search/`: hosted web search probes.
- `image_generation/`: hosted image generation probes.
- `function/`: OpenAI function and namespace tool probes.
- `custom/`: OpenAI custom/freeform tool probes.
- `tool_search/`: Codex deferred tool-search probes.
- `openai_mcp/`: OpenAI official MCP and connector negative probes.
- `openai_shell/`: OpenAI official top-level shell tool probes.
- `shell/`: function-shaped shell tool probes.
- `local_shell/`: legacy Codex local shell protocol probes.
- `apply_patch/`: apply-patch protocol and roundtrip probes.
- `tool_parameters/`: tool-related control parameter probes.

Run from the project root or from this directory:

```powershell
python .\execute_test_plan\run_tool_capability_plan.py
```

To print a focused `/codex/models` capability table:

```powershell
python .\execute_test_plan\model_capabilities_probe.py
```

To show only API-visible models:

```powershell
python .\execute_test_plan\model_capabilities_probe.py --api-visible-only
```

To run a focused `image_generation` probe and save the generated image:

```powershell
python .\execute_test_plan\image_generation\image_generation_probe.py
```

To run a focused `image_generation` parameter matrix probe:

```powershell
python .\execute_test_plan\image_generation\image_generation_tool_matrix_probe.py
```

To run a focused `image_generation` edit matrix probe:

```powershell
python .\execute_test_plan\image_generation\image_generation_edit_matrix_probe.py
```

To run a focused `apply_patch` protocol probe without applying file changes:

```powershell
python .\execute_test_plan\apply_patch\apply_patch_probe.py
```

To run a function-shape `apply_patch` roundtrip against a safe temp file:

```powershell
python .\execute_test_plan\apply_patch\apply_patch_function_roundtrip_probe.py
```

To test whether the model can generate a precise article-edit patch:

```powershell
python .\execute_test_plan\apply_patch\apply_patch_article_edit_probe.py
```

To run focused OpenAI `custom` tool probes:

```powershell
python .\execute_test_plan\custom\custom_text_tool_probe.py
python .\execute_test_plan\custom\custom_regex_tool_probe.py
```

To run a custom tool roundtrip probe:

```powershell
python .\execute_test_plan\custom\custom_text_tool_roundtrip_probe.py
```

To run a function tool roundtrip probe:

```powershell
python .\execute_test_plan\function\function_tool_roundtrip_probe.py
```

To run a namespace-wrapped function roundtrip probe:

```powershell
python .\execute_test_plan\function\namespace_function_roundtrip_probe.py
```

To run focused Codex `local_shell` protocol probes:

```powershell
python .\execute_test_plan\local_shell\local_shell_call_probe.py
python .\execute_test_plan\local_shell\local_shell_roundtrip_probe.py
```

To run focused OpenAI official top-level `shell` probes:

```powershell
python .\execute_test_plan\openai_shell\openai_shell_local_probe.py
python .\execute_test_plan\openai_shell\openai_shell_hosted_probe.py
```

To run focused OpenAI official `mcp` negative probes:

```powershell
python .\execute_test_plan\openai_mcp\openai_mcp_remote_negative_probe.py
python .\execute_test_plan\openai_mcp\openai_mcp_connector_negative_probe.py
```

To run focused Codex shell function-tool roundtrip probes:

```powershell
python .\execute_test_plan\shell\shell_command_roundtrip_probe.py
python .\execute_test_plan\shell\shell_roundtrip_probe.py
python .\execute_test_plan\shell\exec_command_roundtrip_probe.py
```

To run focused `tool_search` probes:

```powershell
python .\execute_test_plan\tool_search\tool_search_call_probe.py
python .\execute_test_plan\tool_search\tool_search_hit_roundtrip_probe.py
python .\execute_test_plan\tool_search\tool_search_empty_result_probe.py
```

To run focused `max_tool_calls` probes:

```powershell
python .\execute_test_plan\tool_parameters\max_tool_calls_zero_probe.py
python .\execute_test_plan\tool_parameters\max_tool_calls_one_probe.py
python .\execute_test_plan\tool_parameters\max_tool_calls_two_probe.py
```

To run focused `truncation` probes:

```powershell
python .\execute_test_plan\tool_parameters\truncation_omitted_probe.py
python .\execute_test_plan\tool_parameters\truncation_disabled_probe.py
python .\execute_test_plan\tool_parameters\truncation_auto_probe.py
```

To run a focused `web_search` parameter matrix probe:

```powershell
python .\execute_test_plan\web_search\web_search_tool_matrix_probe.py
```

The runner uses:

- `CODEX_GATEWAY_BASE_URL`, default `http://127.0.0.1:8787/v1`
- `CODEX_GATEWAY_API_KEY`, default `local-dummy-key`
- `CODEX_GATEWAY_MODEL`, default `gpt-5.2`
- `CODEX_GATEWAY_VECTOR_STORE_ID`, optional comma-separated vector store ids
  for the `file_search` probe

Generated files:

- `tool_capability_results.json`
- `tool_capability_results.md`
- `web_search/web_search_tool_matrix_results.json`
- `web_search/web_search_tool_matrix_results.md`
- `image_generation/image_generation_tool_matrix_results.json`
- `image_generation/image_generation_tool_matrix_results.md`
- `image_generation/image_generation_edit_matrix_results.json`
- `image_generation/image_generation_edit_matrix_results.md`
- `apply_patch/apply_patch_function_roundtrip_results.json`
- `apply_patch/apply_patch_function_roundtrip_results.md`
- `apply_patch/apply_patch_article_edit_results.json`
- `apply_patch/apply_patch_article_edit_results.md`
- `function/namespace_function_roundtrip_results.json`
- `function/namespace_function_roundtrip_results.md`
- `tool_search/tool_search_call_probe_results.json`
- `tool_search/tool_search_call_probe_results.md`
- `tool_search/tool_search_hit_roundtrip_results.json`
- `tool_search/tool_search_hit_roundtrip_results.md`
- `tool_search/tool_search_empty_result_results.json`
- `tool_search/tool_search_empty_result_results.md`
- `local_shell/local_shell_call_probe_results.json`
- `local_shell/local_shell_call_probe_results.md`
- `local_shell/local_shell_roundtrip_results.json`
- `local_shell/local_shell_roundtrip_results.md`
- `openai_mcp/openai_mcp_remote_negative_results.json`
- `openai_mcp/openai_mcp_remote_negative_results.md`
- `openai_mcp/openai_mcp_remote_negative_response.json`
- `openai_mcp/openai_mcp_connector_negative_results.json`
- `openai_mcp/openai_mcp_connector_negative_results.md`
- `openai_mcp/openai_mcp_connector_negative_response.json`
- `openai_shell/openai_shell_local_results.json`
- `openai_shell/openai_shell_local_results.md`
- `openai_shell/openai_shell_local_response1.json`
- `openai_shell/openai_shell_hosted_results.json`
- `openai_shell/openai_shell_hosted_results.md`
- `openai_shell/openai_shell_hosted_response.json`
- `shell/shell_command_roundtrip_results.json`
- `shell/shell_command_roundtrip_results.md`
- `shell/shell_roundtrip_results.json`
- `shell/shell_roundtrip_results.md`
- `shell/exec_command_roundtrip_results.json`
- `shell/exec_command_roundtrip_results.md`
- `tool_parameters/max_tool_calls_zero_results.json`
- `tool_parameters/max_tool_calls_zero_results.md`
- `tool_parameters/max_tool_calls_one_results.json`
- `tool_parameters/max_tool_calls_one_results.md`
- `tool_parameters/max_tool_calls_two_results.json`
- `tool_parameters/max_tool_calls_two_results.md`
- `tool_parameters/truncation_omitted_results.json`
- `tool_parameters/truncation_omitted_results.md`
- `tool_parameters/truncation_disabled_results.json`
- `tool_parameters/truncation_disabled_results.md`
- `tool_parameters/truncation_auto_results.json`
- `tool_parameters/truncation_auto_results.md`
