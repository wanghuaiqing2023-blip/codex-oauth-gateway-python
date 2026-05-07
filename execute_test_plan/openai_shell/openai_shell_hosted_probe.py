from __future__ import annotations

import json
import time

from openai import OpenAIError

from openai_shell_common import (
    BASE_URL,
    MODEL,
    OPENAI_SHELL_HOSTED_TOOL,
    OUTPUT_DIR,
    RESULT_HEADERS,
    build_client,
    elapsed_ms,
    error_message,
    error_payload,
    find_shell_call,
    find_shell_call_output,
    output_item_types,
    output_text,
    print_table,
    response_to_dict,
    shell_commands,
    write_result_files,
)


RESPONSE_JSON_PATH = OUTPUT_DIR / "openai_shell_hosted_response.json"
RESULT_JSON_PATH = OUTPUT_DIR / "openai_shell_hosted_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "openai_shell_hosted_results.md"

PROMPT = "Use the hosted shell to execute: python --version. Then report the version in one short sentence."


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: OpenAI official shell")
    print("environment: container_auto")
    print("intent: verify Codex backend boundary for the official hosted shell tool")

    client = build_client()
    rows: list[list[object]] = []
    details: list[list[object]] = []

    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            tools=[OPENAI_SHELL_HOSTED_TOOL],
            tool_choice="auto",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        RESPONSE_JSON_PATH.write_text(
            json.dumps(error_payload(error), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows.append(
            [
                "hosted_shell_request",
                "rejected",
                "",
                "",
                [],
                elapsed_ms(started),
                "",
                error_message(error),
            ]
        )
        details.append(["response_json", str(RESPONSE_JSON_PATH)])
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="OpenAI Shell Hosted Results",
            tool=OPENAI_SHELL_HOSTED_TOOL,
            summary_rows=rows,
            detail_rows=details,
        )
        print("\nProbe result:")
        print_table(RESULT_HEADERS, rows)
        print(f"\nresult_json: {RESULT_JSON_PATH}")
        print(f"result_md: {RESULT_MD_PATH}")
        return 0
    except Exception as error:  # noqa: BLE001
        RESPONSE_JSON_PATH.write_text(
            json.dumps(error_payload(error), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows.append(
            [
                "hosted_shell_request",
                "client_error",
                "",
                "",
                [],
                elapsed_ms(started),
                "",
                f"{type(error).__name__}: {error}",
            ]
        )
        details.append(["response_json", str(RESPONSE_JSON_PATH)])
        write_result_files(
            result_json_path=RESULT_JSON_PATH,
            result_md_path=RESULT_MD_PATH,
            title="OpenAI Shell Hosted Results",
            tool=OPENAI_SHELL_HOSTED_TOOL,
            summary_rows=rows,
            detail_rows=details,
        )
        print("\nProbe result:")
        print_table(RESULT_HEADERS, rows)
        print(f"\nresult_json: {RESULT_JSON_PATH}")
        print(f"result_md: {RESULT_MD_PATH}")
        return 0

    payload = response_to_dict(response)
    RESPONSE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    shell_call_match = find_shell_call(payload)
    shell_output_match = find_shell_call_output(payload)
    call_id = ""
    observation = "expected shell_call not found"
    status = "accepted_no_evidence"

    if shell_call_match:
        path, shell_call = shell_call_match
        call_id = str(shell_call.get("call_id") or shell_call.get("id") or "")
        status = "supported"
        observation = f"{path} found"
        details.extend(
            [
                ["shell_call_path", path],
                ["commands", shell_commands(shell_call)],
            ]
        )
    if shell_output_match:
        path, _shell_output = shell_output_match
        status = "supported_with_output"
        observation = f"{observation}; {path} found"
        details.append(["shell_call_output_path", path])

    final_text = output_text(response, payload)
    details.extend(
        [
            ["response_json", str(RESPONSE_JSON_PATH)],
            ["final_output_text", final_text],
        ]
    )

    rows.append(
        [
            "hosted_shell_request",
            status,
            str(getattr(response, "model", "") or ""),
            str(payload.get("status") or ""),
            output_item_types(payload),
            elapsed_ms(started),
            call_id,
            observation,
        ]
    )

    write_result_files(
        result_json_path=RESULT_JSON_PATH,
        result_md_path=RESULT_MD_PATH,
        title="OpenAI Shell Hosted Results",
        tool=OPENAI_SHELL_HOSTED_TOOL,
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
