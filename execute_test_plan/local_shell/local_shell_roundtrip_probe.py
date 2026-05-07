from __future__ import annotations

import json

from openai import OpenAIError

from local_shell_common import BASE_URL
from local_shell_common import LOCAL_SHELL_TOOL
from local_shell_common import MODEL
from local_shell_common import OUTPUT_DIR
from local_shell_common import SAFE_COMMAND
from local_shell_common import SIMULATED_SHELL_OUTPUT
from local_shell_common import action_command
from local_shell_common import build_client
from local_shell_common import error_message
from local_shell_common import find_local_shell_call
from local_shell_common import make_local_shell_call_context_item
from local_shell_common import make_timing
from local_shell_common import output_item_types
from local_shell_common import output_text
from local_shell_common import print_table
from local_shell_common import response_to_dict
from local_shell_common import write_result_files


RESPONSE1_JSON_PATH = OUTPUT_DIR / "local_shell_roundtrip_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "local_shell_roundtrip_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "local_shell_roundtrip_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "local_shell_roundtrip_results.md"

EXPECTED_FINAL_TEXT = "gateway-local-shell-roundtrip-ok"
PROMPT1 = (
    "Use the local_shell tool to run exactly this command array: "
    f"{json.dumps(SAFE_COMMAND)}. Do not answer directly."
)
PROMPT2 = (
    "Use the supplied local shell output to answer. Reply exactly with "
    "gateway-local-shell-roundtrip-ok and nothing else."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: local_shell")
    print("intent: verify local_shell_call -> simulated client output -> final answer")
    print("execution: the command is not executed; this probe supplies a simulated shell result")
    print("output_item_for_result: function_call_output, matching Codex CLI request invariants")
    print(f"requested_command: {json.dumps(SAFE_COMMAND)}")

    client = build_client()
    _, elapsed1_ms = make_timing()

    try:
        response1 = client.responses.create(
            model=MODEL,
            input=PROMPT1,
            tools=[LOCAL_SHELL_TOOL],
            tool_choice="required",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows = [["phase1_tool_call", "rejected", "", "", [], elapsed1_ms(), "", error_message(error)]]
        print("\nRoundtrip result:")
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
            title="Local Shell Roundtrip Results",
            summary_rows=rows,
        )
        return 0

    payload1 = response_to_dict(response1)
    RESPONSE1_JSON_PATH.write_text(json.dumps(payload1, ensure_ascii=False, indent=2), encoding="utf-8")
    match = find_local_shell_call(payload1)
    actual_model1 = getattr(response1, "model", None) or payload1.get("model") or ""
    response_status1 = getattr(response1, "status", None) or payload1.get("status") or ""

    if not match:
        rows = [
            [
                "phase1_tool_call",
                "accepted_no_local_shell_call",
                actual_model1,
                response_status1,
                output_item_types(payload1),
                elapsed1_ms(),
                "",
                "request accepted but no local_shell_call found",
            ]
        ]
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="Local Shell Roundtrip Results",
            summary_rows=rows,
            detail_rows=[["response1_json", str(RESPONSE1_JSON_PATH)]],
        )
        print("\nRoundtrip result:")
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
        return 0

    local_shell_call_path, local_shell_call = match
    call_id = str(local_shell_call.get("call_id") or "")
    if not call_id:
        rows = [
            [
                "phase1_tool_call",
                "missing_call_id",
                actual_model1,
                response_status1,
                output_item_types(payload1),
                elapsed1_ms(),
                "",
                f"{local_shell_call_path} has no call_id",
            ]
        ]
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="Local Shell Roundtrip Results",
            summary_rows=rows,
            detail_rows=[["response1_json", str(RESPONSE1_JSON_PATH)]],
        )
        print("\nRoundtrip result:")
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
        return 0

    input2 = [
        {
            "role": "user",
            "content": PROMPT2,
        },
        make_local_shell_call_context_item(local_shell_call),
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": SIMULATED_SHELL_OUTPUT,
        },
    ]

    _, elapsed2_ms = make_timing()
    try:
        response2 = client.responses.create(
            model=MODEL,
            input=input2,
            tools=[LOCAL_SHELL_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows = [
            [
                "phase1_tool_call",
                "supported_protocol",
                actual_model1,
                response_status1,
                output_item_types(payload1),
                elapsed1_ms(),
                call_id,
                f"{local_shell_call_path} found",
            ],
            ["phase2_tool_output", "rejected", "", "", [], elapsed2_ms(), call_id, error_message(error)],
        ]
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="Local Shell Roundtrip Results",
            summary_rows=rows,
            detail_rows=[["response1_json", str(RESPONSE1_JSON_PATH)]],
        )
        print("\nRoundtrip result:")
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
        return 0

    payload2 = response_to_dict(response2)
    RESPONSE2_JSON_PATH.write_text(json.dumps(payload2, ensure_ascii=False, indent=2), encoding="utf-8")
    final_text = output_text(response2, payload2)
    actual_model2 = getattr(response2, "model", None) or payload2.get("model") or ""
    response_status2 = getattr(response2, "status", None) or payload2.get("status") or ""

    rows = [
        [
            "phase1_tool_call",
            "supported_protocol",
            actual_model1,
            response_status1,
            output_item_types(payload1),
            elapsed1_ms(),
            call_id,
            f"{local_shell_call_path} found",
        ],
        [
            "phase2_tool_output",
            "supported_roundtrip" if EXPECTED_FINAL_TEXT in final_text else "accepted_without_expected_text",
            actual_model2,
            response_status2,
            output_item_types(payload2),
            elapsed2_ms(),
            call_id,
            "final text contains simulated shell output"
            if EXPECTED_FINAL_TEXT in final_text
            else "final text did not contain simulated shell output",
        ],
    ]
    details = [
        ["local_shell_call_path", local_shell_call_path],
        ["call_id", call_id],
        ["command", action_command(local_shell_call)],
        ["command_matches_request", action_command(local_shell_call) == SAFE_COMMAND],
        ["simulated_output", SIMULATED_SHELL_OUTPUT],
        ["response1_json", str(RESPONSE1_JSON_PATH)],
        ["response2_json", str(RESPONSE2_JSON_PATH)],
        ["final_output_text", final_text],
    ]

    print("\nRoundtrip result:")
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
        title="Local Shell Roundtrip Results",
        summary_rows=rows,
        detail_rows=details,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
