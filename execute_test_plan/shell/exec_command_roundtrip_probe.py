from __future__ import annotations

from shell_tools_common import BASE_URL
from shell_tools_common import EXEC_COMMAND_TOOL
from shell_tools_common import MODEL
from shell_tools_common import OUTPUT_DIR
from shell_tools_common import SAFE_COMMAND_TEXT
from shell_tools_common import run_shell_tool_roundtrip


TOOL_NAME = "exec_command"
RESPONSE1_JSON_PATH = OUTPUT_DIR / "exec_command_roundtrip_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "exec_command_roundtrip_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "exec_command_roundtrip_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "exec_command_roundtrip_results.md"

PHASE1_PROMPT = (
    "Call the exec_command function to inspect the local Python runtime. "
    f"The cmd argument must be exactly {SAFE_COMMAND_TEXT!r}. "
    "Do not answer directly."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: function")
    print(f"tool_name: {TOOL_NAME}")
    print("intent: verify Codex exec_command function-call roundtrip")
    print(f"allowed_cmd: {SAFE_COMMAND_TEXT!r}")
    print("\nRoundtrip result:")
    return run_shell_tool_roundtrip(
        tool_name=TOOL_NAME,
        tool_definition=EXEC_COMMAND_TOOL,
        phase1_prompt=PHASE1_PROMPT,
        response1_json_path=RESPONSE1_JSON_PATH,
        response2_json_path=RESPONSE2_JSON_PATH,
        result_json_path=RESULT_JSON_PATH,
        result_md_path=RESULT_MD_PATH,
        title="Exec Command Roundtrip Results",
    )


if __name__ == "__main__":
    raise SystemExit(main())
