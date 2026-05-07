from __future__ import annotations

import json

from openai import OpenAIError

from local_shell_common import BASE_URL
from local_shell_common import LOCAL_SHELL_TOOL
from local_shell_common import MODEL
from local_shell_common import OUTPUT_DIR
from local_shell_common import SAFE_COMMAND
from local_shell_common import action_command
from local_shell_common import build_client
from local_shell_common import error_message
from local_shell_common import find_local_shell_call
from local_shell_common import make_timing
from local_shell_common import output_item_types
from local_shell_common import print_table
from local_shell_common import response_to_dict
from local_shell_common import write_result_files


RESPONSE_JSON_PATH = OUTPUT_DIR / "local_shell_call_probe_response.json"
RESULT_JSON_PATH = OUTPUT_DIR / "local_shell_call_probe_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "local_shell_call_probe_results.md"


PROMPT = (
    "Use the local_shell tool to run exactly this command array: "
    f"{json.dumps(SAFE_COMMAND)}. Do not answer directly."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: local_shell")
    print("intent: verify whether Codex backend emits a local_shell_call")
    print("execution: no local command is executed by this probe")
    print(f"requested_command: {json.dumps(SAFE_COMMAND)}")

    client = build_client()
    _, elapsed_ms = make_timing()

    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            tools=[LOCAL_SHELL_TOOL],
            tool_choice="required",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows = [["phase1_tool_call", "rejected", "", "", [], elapsed_ms(), "", error_message(error)]]
        print("\nSummary:")
        print_table(
            [
                "phase",
                "status",
                "actual_model",
                "response_status",
                "output_item_types",
                "elapsed_ms",
                "call_id",
                "observation",
            ],
            rows,
        )
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="Local Shell Call Probe Results",
            summary_rows=rows,
        )
        return 0

    payload = response_to_dict(response)
    RESPONSE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    match = find_local_shell_call(payload)
    actual_model = getattr(response, "model", None) or payload.get("model") or ""
    response_status = getattr(response, "status", None) or payload.get("status") or ""
    item_types = output_item_types(payload)

    if not match:
        rows = [
            [
                "phase1_tool_call",
                "accepted_no_local_shell_call",
                actual_model,
                response_status,
                item_types,
                elapsed_ms(),
                "",
                "request accepted but no local_shell_call found",
            ]
        ]
        details = [["response_json", str(RESPONSE_JSON_PATH)]]
    else:
        path, local_shell_call = match
        call_id = str(local_shell_call.get("call_id") or "")
        command = action_command(local_shell_call)
        rows = [
            [
                "phase1_tool_call",
                "supported_protocol",
                actual_model,
                response_status,
                item_types,
                elapsed_ms(),
                call_id,
                f"{path} found",
            ]
        ]
        details = [
            ["local_shell_call_path", path],
            ["call_id", call_id],
            ["command", command],
            ["command_matches_request", command == SAFE_COMMAND],
            ["response_json", str(RESPONSE_JSON_PATH)],
        ]

    print("\nSummary:")
    print_table(
        [
            "phase",
            "status",
            "actual_model",
            "response_status",
            "output_item_types",
            "elapsed_ms",
            "call_id",
            "observation",
        ],
        rows,
    )
    print("\nDetails:")
    for key, value in details:
        print(f"{key}: {value}")

    write_result_files(
        result_json_path=RESULT_JSON_PATH,
        result_md_path=RESULT_MD_PATH,
        title="Local Shell Call Probe Results",
        summary_rows=rows,
        detail_rows=details,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
