from __future__ import annotations

import json

from shell_tools_common import BASE_URL
from shell_tools_common import MODEL
from shell_tools_common import OUTPUT_DIR
from shell_tools_common import SAFE_COMMAND_ARRAY
from shell_tools_common import SHELL_TOOL
from shell_tools_common import run_shell_tool_roundtrip


TOOL_NAME = "shell"
RESPONSE1_JSON_PATH = OUTPUT_DIR / "shell_roundtrip_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "shell_roundtrip_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "shell_roundtrip_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "shell_roundtrip_results.md"

PHASE1_PROMPT = (
    "Call the shell function to inspect the local Python runtime. "
    f"The command argument must be exactly this JSON array: {json.dumps(SAFE_COMMAND_ARRAY)}. "
    "Do not answer directly."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: function")
    print(f"tool_name: {TOOL_NAME}")
    print("intent: verify Codex shell function-call roundtrip")
    print(f"allowed_command_array: {json.dumps(SAFE_COMMAND_ARRAY)}")
    print("\nRoundtrip result:")
    return run_shell_tool_roundtrip(
        tool_name=TOOL_NAME,
        tool_definition=SHELL_TOOL,
        phase1_prompt=PHASE1_PROMPT,
        response1_json_path=RESPONSE1_JSON_PATH,
        response2_json_path=RESPONSE2_JSON_PATH,
        result_json_path=RESULT_JSON_PATH,
        result_md_path=RESULT_MD_PATH,
        title="Shell Roundtrip Results",
    )


if __name__ == "__main__":
    raise SystemExit(main())
