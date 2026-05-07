from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openai import APIStatusError, OpenAI, OpenAIError


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

OUTPUT_DIR = Path(__file__).resolve().parent
RESPONSE1_JSON_PATH = OUTPUT_DIR / "namespace_function_roundtrip_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "namespace_function_roundtrip_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "namespace_function_roundtrip_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "namespace_function_roundtrip_results.md"

NAMESPACE_NAME = "probe_namespace"
TOOL_NAME = "get_probe_value"
EXPECTED_KEY = "gateway_status"
EXPECTED_VALUE = "namespace-function-roundtrip-ok"

NAMESPACE_TOOL = {
    "type": "namespace",
    "name": NAMESPACE_NAME,
    "description": "Probe namespace for testing Responses API namespace tool wiring.",
    "tools": [
        {
            "type": "function",
            "name": TOOL_NAME,
            "description": "Return a deterministic value for the namespace tool probe.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Lookup key. Use gateway_status for this test.",
                    }
                },
                "required": ["key"],
            },
        }
    ],
}

PROMPT1 = (
    f"Call the {NAMESPACE_NAME}.{TOOL_NAME} tool with key {EXPECTED_KEY}. "
    "Do not answer directly."
)
PROMPT2 = (
    "Use the supplied tool output to answer. "
    f"Reply exactly with {EXPECTED_VALUE} and nothing else."
)


def build_client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY, max_retries=0)


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return json.loads(json.dumps(response, default=str))


def error_message(error: BaseException) -> str:
    if isinstance(error, APIStatusError):
        try:
            payload = error.response.json()
        except Exception:
            return error.response.text
        if isinstance(payload, dict):
            upstream = payload.get("error")
            if isinstance(upstream, dict):
                return str(upstream.get("message") or upstream)
        return json.dumps(payload, ensure_ascii=False)
    return str(error)


def find_objects_by_type(value: Any, object_type: str, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        matches: list[tuple[str, dict[str, Any]]] = []
        if value.get("type") == object_type:
            matches.append((path, value))
        for child_key, child_value in value.items():
            matches.extend(find_objects_by_type(child_value, object_type, f"{path}.{child_key}"))
        return matches
    if isinstance(value, list):
        matches = []
        for index, child_value in enumerate(value):
            matches.extend(find_objects_by_type(child_value, object_type, f"{path}[{index}]"))
        return matches
    return []


def output_item_types(payload: dict[str, Any]) -> list[str]:
    output = payload.get("output")
    if not isinstance(output, list):
        return []
    return [str(item.get("type", "<missing>")) for item in output if isinstance(item, dict)]


def output_text(response: Any, payload: dict[str, Any]) -> str:
    sdk_output_text = getattr(response, "output_text", None)
    if isinstance(sdk_output_text, str):
        return sdk_output_text

    texts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "".join(texts)


def parse_arguments(function_call: dict[str, Any]) -> dict[str, Any]:
    raw_arguments = function_call.get("arguments")
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str) and raw_arguments:
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def find_probe_function_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for path, item in find_objects_by_type(payload, "function_call"):
        name = str(item.get("name") or "")
        if name == TOOL_NAME or name.endswith(f".{TOOL_NAME}"):
            return path, item
    return None


def make_function_call_context_item(function_call: dict[str, Any]) -> dict[str, Any]:
    item = {
        "type": "function_call",
        "call_id": function_call["call_id"],
        "name": function_call["name"],
        "arguments": function_call.get("arguments") or "{}",
    }
    if function_call.get("id"):
        item["id"] = function_call["id"]
    if function_call.get("status"):
        item["status"] = function_call["status"]
    return item


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return str(value)


def print_table(headers: list[str], rows: list[list[Any]]) -> None:
    values = [[format_value(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        if len(row) != len(headers):
            raise ValueError(f"row has {len(row)} columns, expected {len(headers)}")
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()

    print(format_row(headers))
    print(format_row(["-" * width for width in widths]))
    for row in values:
        print(format_row(row))


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        return format_value(value).replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return "\n".join(lines)


def write_result_files(rows: list[list[Any]], details: list[list[Any]]) -> None:
    headers = [
        "phase",
        "status",
        "actual_model",
        "response_status",
        "output_item_types",
        "elapsed_ms",
        "call_id",
        "observation",
    ]
    RESULT_JSON_PATH.write_text(
        json.dumps(
            {
                "base_url": BASE_URL,
                "requested_model": MODEL,
                "namespace": NAMESPACE_NAME,
                "tool_name": TOOL_NAME,
                "summary": [dict(zip(headers, row)) for row in rows],
                "details": details,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    RESULT_MD_PATH.write_text(
        "\n\n".join(
            [
                "# Namespace Function Roundtrip Results",
                f"- gateway base_url: `{BASE_URL}`",
                f"- requested_model: `{MODEL}`",
                f"- namespace: `{NAMESPACE_NAME}`",
                f"- function: `{TOOL_NAME}`",
                "",
                "## Summary",
                markdown_table(headers, rows),
                "## Details",
                markdown_table(["key", "value"], details),
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: namespace")
    print(f"namespace: {NAMESPACE_NAME}")
    print(f"function: {TOOL_NAME}")
    print("intent: verify namespace -> function_call -> function_call_output roundtrip")

    client = build_client()
    rows: list[list[Any]] = []
    details: list[list[Any]] = []

    started1 = time.perf_counter()
    try:
        response1 = client.responses.create(
            model=MODEL,
            input=PROMPT1,
            tools=[NAMESPACE_TOOL],
            tool_choice="required",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows.append(["phase1_tool_call", "rejected", "", "", [], int((time.perf_counter() - started1) * 1000), "", error_message(error)])
        write_result_files(rows, details)
        print_table(
            ["phase", "status", "actual_model", "response_status", "output_item_types", "elapsed_ms", "call_id", "observation"],
            rows,
        )
        return 0

    elapsed1_ms = int((time.perf_counter() - started1) * 1000)
    payload1 = response_to_dict(response1)
    RESPONSE1_JSON_PATH.write_text(json.dumps(payload1, ensure_ascii=False, indent=2), encoding="utf-8")
    match = find_probe_function_call(payload1)

    if not match:
        rows.append(
            [
                "phase1_tool_call",
                "accepted_no_namespace_function_call",
                getattr(response1, "model", None) or payload1.get("model") or "",
                getattr(response1, "status", None) or payload1.get("status") or "",
                output_item_types(payload1),
                elapsed1_ms,
                "",
                "request accepted but no matching function_call found",
            ]
        )
        details.append(["response1_json", str(RESPONSE1_JSON_PATH)])
        write_result_files(rows, details)
        print_table(
            ["phase", "status", "actual_model", "response_status", "output_item_types", "elapsed_ms", "call_id", "observation"],
            rows,
        )
        return 0

    function_call_path, function_call = match
    call_id = str(function_call.get("call_id") or "")
    arguments = parse_arguments(function_call)
    rows.append(
        [
            "phase1_tool_call",
            "supported_protocol",
            getattr(response1, "model", None) or payload1.get("model") or "",
            getattr(response1, "status", None) or payload1.get("status") or "",
            output_item_types(payload1),
            elapsed1_ms,
            call_id,
            f"{function_call_path} found; name={function_call.get('name')}",
        ]
    )

    phase2_input = [
        {"role": "user", "content": PROMPT2},
        make_function_call_context_item(function_call),
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps({"probe_status": EXPECTED_VALUE}, ensure_ascii=False),
        },
    ]

    started2 = time.perf_counter()
    try:
        response2 = client.responses.create(
            model=MODEL,
            input=phase2_input,
            tools=[NAMESPACE_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows.append(["phase2_tool_output", "rejected", "", "", [], int((time.perf_counter() - started2) * 1000), call_id, error_message(error)])
        details.extend(
            [
                ["function_call_path", function_call_path],
                ["function_arguments", arguments],
                ["response1_json", str(RESPONSE1_JSON_PATH)],
            ]
        )
        write_result_files(rows, details)
        print_table(
            ["phase", "status", "actual_model", "response_status", "output_item_types", "elapsed_ms", "call_id", "observation"],
            rows,
        )
        return 0

    elapsed2_ms = int((time.perf_counter() - started2) * 1000)
    payload2 = response_to_dict(response2)
    RESPONSE2_JSON_PATH.write_text(json.dumps(payload2, ensure_ascii=False, indent=2), encoding="utf-8")
    final_text = output_text(response2, payload2)
    rows.append(
        [
            "phase2_tool_output",
            "supported_roundtrip" if EXPECTED_VALUE in final_text else "accepted_without_expected_text",
            getattr(response2, "model", None) or payload2.get("model") or "",
            getattr(response2, "status", None) or payload2.get("status") or "",
            output_item_types(payload2),
            elapsed2_ms,
            call_id,
            "final text contains namespace function output" if EXPECTED_VALUE in final_text else "final text did not contain expected value",
        ]
    )
    details.extend(
        [
            ["function_call_path", function_call_path],
            ["function_name", function_call.get("name")],
            ["function_arguments", arguments],
            ["argument_key_matches", arguments.get("key") == EXPECTED_KEY],
            ["response1_json", str(RESPONSE1_JSON_PATH)],
            ["response2_json", str(RESPONSE2_JSON_PATH)],
            ["final_output_text", final_text],
        ]
    )
    write_result_files(rows, details)

    print("\nRoundtrip result:")
    print_table(
        ["phase", "status", "actual_model", "response_status", "output_item_types", "elapsed_ms", "call_id", "observation"],
        rows,
    )
    print("\nDetails:")
    for key, value in details:
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
