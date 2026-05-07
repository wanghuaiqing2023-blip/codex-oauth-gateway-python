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
RESPONSE1_JSON_PATH = OUTPUT_DIR / "custom_text_tool_roundtrip_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "custom_text_tool_roundtrip_response2.json"

TOOL_NAME = "get_probe_value"
EXPECTED_TOOL_INPUT = "gateway_status"
TOOL_OUTPUT = "gateway-custom-roundtrip-ok"
PROMPT1 = (
    "Call the get_probe_value custom tool. The tool input must be exactly "
    "gateway_status. Do not answer directly."
)
PROMPT2 = (
    "Use the supplied custom tool output to answer. Reply exactly with the "
    "tool output text and nothing else."
)

CUSTOM_TEXT_TOOL = {
    "type": "custom",
    "name": TOOL_NAME,
    "description": "Accepts a raw lookup key. This probe simulates execution in the client.",
    "format": {"type": "text"},
}


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


def find_custom_tool_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for path, item in find_objects_by_type(payload, "custom_tool_call"):
        if item.get("name") == TOOL_NAME:
            return path, item
    return None


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


def make_tool_call_context_item(tool_call: dict[str, Any]) -> dict[str, Any]:
    context_item = {
        "type": "custom_tool_call",
        "call_id": tool_call["call_id"],
        "name": tool_call["name"],
        "input": tool_call.get("input") or "",
    }
    if tool_call.get("id"):
        context_item["id"] = tool_call["id"]
    if tool_call.get("status"):
        context_item["status"] = tool_call["status"]
    return context_item


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: custom")
    print("format: text")
    print(f"tool_name: {TOOL_NAME}")
    print("intent: verify custom_tool_call -> client output -> final model answer")
    print("state_mode: stateless input array; previous_response_id is intentionally not used")
    print(f"expected_tool_input: {EXPECTED_TOOL_INPUT!r}")
    print(f"simulated_tool_output: {TOOL_OUTPUT!r}")

    client = build_client()

    started1 = time.perf_counter()
    try:
        response1 = client.responses.create(
            model=MODEL,
            input=PROMPT1,
            tools=[CUSTOM_TEXT_TOOL],
            tool_choice="required",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        print("\nRoundtrip result:")
        print_table(
            ["phase", "status", "actual_model", "output_item_types", "elapsed_ms", "observation"],
            [["phase1_tool_call", "rejected", "", [], int((time.perf_counter() - started1) * 1000), error_message(error)]],
        )
        return 0

    elapsed1_ms = int((time.perf_counter() - started1) * 1000)
    payload1 = response_to_dict(response1)
    RESPONSE1_JSON_PATH.write_text(json.dumps(payload1, ensure_ascii=False, indent=2), encoding="utf-8")

    match = find_custom_tool_call(payload1)
    if not match:
        print("\nRoundtrip result:")
        print_table(
            ["phase", "status", "actual_model", "output_item_types", "elapsed_ms", "observation"],
            [
                [
                    "phase1_tool_call",
                    "accepted_no_custom_call",
                    getattr(response1, "model", None) or payload1.get("model") or "",
                    output_item_types(payload1),
                    elapsed1_ms,
                    "no matching custom_tool_call found",
                ]
            ],
        )
        print(f"response1_json: {RESPONSE1_JSON_PATH}")
        return 0

    tool_call_path, tool_call = match
    tool_input = str(tool_call.get("input") or "")
    call_id = str(tool_call.get("call_id") or "")
    if not call_id:
        print("\nRoundtrip result:")
        print_table(
            ["phase", "status", "actual_model", "output_item_types", "elapsed_ms", "observation"],
            [
                [
                    "phase1_tool_call",
                    "missing_call_id",
                    getattr(response1, "model", None) or payload1.get("model") or "",
                    output_item_types(payload1),
                    elapsed1_ms,
                    f"{tool_call_path} has no call_id",
                ]
            ],
        )
        print(f"response1_json: {RESPONSE1_JSON_PATH}")
        return 0

    input2 = [
        {
            "role": "user",
            "content": PROMPT2,
        },
        make_tool_call_context_item(tool_call),
        {
            "type": "custom_tool_call_output",
            "call_id": call_id,
            "output": TOOL_OUTPUT,
        },
    ]

    started2 = time.perf_counter()
    try:
        response2 = client.responses.create(
            model=MODEL,
            input=input2,
            tools=[CUSTOM_TEXT_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        print("\nRoundtrip result:")
        print_table(
            [
                "phase",
                "status",
                "actual_model",
                "output_item_types",
                "elapsed_ms",
                "call_id",
                "observation",
            ],
            [
                [
                    "phase1_tool_call",
                    "supported_protocol",
                    getattr(response1, "model", None) or payload1.get("model") or "",
                    output_item_types(payload1),
                    elapsed1_ms,
                    call_id,
                    f"{tool_call_path} found",
                ],
                [
                    "phase2_tool_output",
                    "rejected",
                    "",
                    [],
                    int((time.perf_counter() - started2) * 1000),
                    call_id,
                    error_message(error),
                ],
            ],
        )
        print(f"response1_json: {RESPONSE1_JSON_PATH}")
        return 0

    elapsed2_ms = int((time.perf_counter() - started2) * 1000)
    payload2 = response_to_dict(response2)
    RESPONSE2_JSON_PATH.write_text(json.dumps(payload2, ensure_ascii=False, indent=2), encoding="utf-8")
    final_text = output_text(response2, payload2)

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
        [
            [
                "phase1_tool_call",
                "supported_protocol",
                getattr(response1, "model", None) or payload1.get("model") or "",
                getattr(response1, "status", None) or payload1.get("status") or "",
                output_item_types(payload1),
                elapsed1_ms,
                call_id,
                f"{tool_call_path} found",
            ],
            [
                "phase2_tool_output",
                "supported_roundtrip" if TOOL_OUTPUT in final_text else "accepted_without_expected_text",
                getattr(response2, "model", None) or payload2.get("model") or "",
                getattr(response2, "status", None) or payload2.get("status") or "",
                output_item_types(payload2),
                elapsed2_ms,
                call_id,
                "final text contains tool output" if TOOL_OUTPUT in final_text else "final text did not contain tool output",
            ],
        ],
    )

    print("\nDetails:")
    print(f"tool_call_path: {tool_call_path}")
    print(f"tool_call_input: {tool_input!r}")
    print(f"tool_input_matches: {tool_input == EXPECTED_TOOL_INPUT}")
    print(f"response1_json: {RESPONSE1_JSON_PATH}")
    print(f"response2_json: {RESPONSE2_JSON_PATH}")
    print(f"final_output_text: {final_text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
