from __future__ import annotations

import json
import time

from openai import OpenAIError

from openai_shell_common import (
    BASE_URL,
    FINAL_MARKER,
    MODEL,
    OPENAI_SHELL_LOCAL_TOOL,
    OUTPUT_DIR,
    RESULT_HEADERS,
    SAFE_COMMAND,
    build_client,
    elapsed_ms,
    error_message,
    error_payload,
    find_shell_call,
    format_value,
    make_shell_call_context_item,
    make_shell_call_output_item,
    output_item_types,
    output_text,
    print_table,
    response_to_dict,
    run_whitelisted_command,
    shell_commands,
    validate_safe_shell_call,
    write_result_files,
)


RESPONSE1_JSON_PATH = OUTPUT_DIR / "openai_shell_local_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "openai_shell_local_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "openai_shell_local_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "openai_shell_local_results.md"

PROMPT1 = (
    "Use the local shell tool to request exactly one command: "
    f"{SAFE_COMMAND}. Do not answer directly."
)
PROMPT2 = (
    "Use the supplied shell output to answer. "
    f"Reply exactly with {FINAL_MARKER} and nothing else."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: OpenAI official shell")
    print("environment: local")
    print(f"allowed_command: {SAFE_COMMAND!r}")
    print("intent: verify shell_call + shell_call_output roundtrip for the official local shell tool")

    client = build_client()
    rows: list[list[object]] = []
    details: list[list[object]] = []

    started = time.perf_counter()
    try:
        response1 = client.responses.create(
            model=MODEL,
            input=PROMPT1,
            tools=[OPENAI_SHELL_LOCAL_TOOL],
            tool_choice="required",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        RESPONSE1_JSON_PATH.write_text(
            json.dumps(error_payload(error), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows.append(
            [
                "phase1_shell_call",
                "rejected",
                "",
                "",
                [],
                elapsed_ms(started),
                "",
                error_message(error),
            ]
        )
        details.append(["response1_json", str(RESPONSE1_JSON_PATH)])
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="OpenAI Shell Local Results",
            tool=OPENAI_SHELL_LOCAL_TOOL,
            summary_rows=rows,
            detail_rows=details,
        )
        print("\nProbe result:")
        print_table(RESULT_HEADERS, rows)
        print(f"\nresult_json: {RESULT_JSON_PATH}")
        print(f"result_md: {RESULT_MD_PATH}")
        return 0
    except Exception as error:  # noqa: BLE001
        RESPONSE1_JSON_PATH.write_text(
            json.dumps(error_payload(error), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows.append(
            [
                "phase1_shell_call",
                "client_error",
                "",
                "",
                [],
                elapsed_ms(started),
                "",
                f"{type(error).__name__}: {error}",
            ]
        )
        details.append(["response1_json", str(RESPONSE1_JSON_PATH)])
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="OpenAI Shell Local Results",
            tool=OPENAI_SHELL_LOCAL_TOOL,
            summary_rows=rows,
            detail_rows=details,
        )
        print("\nProbe result:")
        print_table(RESULT_HEADERS, rows)
        print(f"\nresult_json: {RESULT_JSON_PATH}")
        print(f"result_md: {RESULT_MD_PATH}")
        return 0

    payload1 = response_to_dict(response1)
    RESPONSE1_JSON_PATH.write_text(json.dumps(payload1, ensure_ascii=False, indent=2), encoding="utf-8")
    shell_call_match = find_shell_call(payload1)
    if shell_call_match is None:
        rows.append(
            [
                "phase1_shell_call",
                "accepted_no_evidence",
                str(getattr(response1, "model", "") or ""),
                str(payload1.get("status") or ""),
                output_item_types(payload1),
                elapsed_ms(started),
                "",
                "expected shell_call not found",
            ]
        )
        details.append(["response1_json", str(RESPONSE1_JSON_PATH)])
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="OpenAI Shell Local Results",
            tool=OPENAI_SHELL_LOCAL_TOOL,
            summary_rows=rows,
            detail_rows=details,
        )
        print("\nProbe result:")
        print_table(RESULT_HEADERS, rows)
        print(f"\nresult_json: {RESULT_JSON_PATH}")
        print(f"result_md: {RESULT_MD_PATH}")
        return 0

    shell_call_path, shell_call = shell_call_match
    call_id = str(shell_call.get("call_id") or shell_call.get("id") or "")
    rows.append(
        [
            "phase1_shell_call",
            "supported_protocol",
            str(getattr(response1, "model", "") or ""),
            str(payload1.get("status") or ""),
            output_item_types(payload1),
            elapsed_ms(started),
            call_id,
            f"{shell_call_path} found",
        ]
    )

    safe_to_execute, safety_observation = validate_safe_shell_call(shell_call)
    details.extend(
        [
            ["shell_call_path", shell_call_path],
            ["commands", shell_commands(shell_call)],
            ["safe_to_execute", safe_to_execute],
            ["safety_observation", safety_observation],
            ["response1_json", str(RESPONSE1_JSON_PATH)],
        ]
    )

    if not safe_to_execute:
        rows.append(
            [
                "phase2_shell_output",
                "blocked_unsafe_command",
                "",
                "",
                [],
                "",
                call_id,
                safety_observation,
            ]
        )
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="OpenAI Shell Local Results",
            tool=OPENAI_SHELL_LOCAL_TOOL,
            summary_rows=rows,
            detail_rows=details,
        )
        print("\nProbe result:")
        print_table(RESULT_HEADERS, rows)
        print(f"\nresult_json: {RESULT_JSON_PATH}")
        print(f"result_md: {RESULT_MD_PATH}")
        return 0

    command_output = run_whitelisted_command(shell_call)
    shell_output_item = make_shell_call_output_item(shell_call, command_output)
    details.extend(
        [
            ["shell_output_item", shell_output_item],
            ["command_elapsed_ms", command_output.get("elapsed_ms")],
        ]
    )

    input_items = [
        {"role": "user", "content": PROMPT1},
        make_shell_call_context_item(shell_call),
        shell_output_item,
        {"role": "user", "content": PROMPT2},
    ]
    started = time.perf_counter()
    try:
        response2 = client.responses.create(
            model=MODEL,
            input=input_items,
            tools=[OPENAI_SHELL_LOCAL_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        RESPONSE2_JSON_PATH.write_text(
            json.dumps(error_payload(error), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows.append(
            [
                "phase2_shell_output",
                "rejected",
                "",
                "",
                [],
                elapsed_ms(started),
                call_id,
                error_message(error),
            ]
        )
        details.append(["response2_json", str(RESPONSE2_JSON_PATH)])
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="OpenAI Shell Local Results",
            tool=OPENAI_SHELL_LOCAL_TOOL,
            summary_rows=rows,
            detail_rows=details,
        )
        print("\nProbe result:")
        print_table(RESULT_HEADERS, rows)
        print(f"\nresult_json: {RESULT_JSON_PATH}")
        print(f"result_md: {RESULT_MD_PATH}")
        return 0

    payload2 = response_to_dict(response2)
    RESPONSE2_JSON_PATH.write_text(json.dumps(payload2, ensure_ascii=False, indent=2), encoding="utf-8")
    final_text = output_text(response2, payload2)
    status = "supported_roundtrip" if FINAL_MARKER in final_text else "accepted_without_marker"
    observation = "final text contains marker" if FINAL_MARKER in final_text else "final marker not found"
    rows.append(
        [
            "phase2_shell_output",
            status,
            str(getattr(response2, "model", "") or ""),
            str(payload2.get("status") or ""),
            output_item_types(payload2),
            elapsed_ms(started),
            call_id,
            observation,
        ]
    )
    details.extend(
        [
            ["response2_json", str(RESPONSE2_JSON_PATH)],
            ["final_output_text", final_text],
        ]
    )

    write_result_files(
        result_json_path=RESULT_JSON_PATH,
        result_md_path=RESULT_MD_PATH,
        title="OpenAI Shell Local Results",
        tool=OPENAI_SHELL_LOCAL_TOOL,
        summary_rows=rows,
        detail_rows=details,
    )

    print("\nProbe result:")
    print_table(RESULT_HEADERS, rows)
    print("\nDetails:")
    print_table(["key", "value"], details)
    print(f"\nresult_json: {RESULT_JSON_PATH}")
    print(f"result_md: {RESULT_MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
