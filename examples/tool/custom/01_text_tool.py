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
RESPONSE_JSON_PATH = OUTPUT_DIR / "custom_text_tool_response.json"

TOOL_NAME = "code_exec"
EXPECTED_INPUT = "print('custom-text-probe-ok')"
PROMPT = (
    "Call the code_exec custom tool. The tool input must be exactly this text, "
    "with no markdown and no extra characters: "
    f"{EXPECTED_INPUT}"
)

CUSTOM_TEXT_TOOL = {
    "type": "custom",
    "name": TOOL_NAME,
    "description": "Accepts a raw Python code string. This probe does not execute it.",
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


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: custom")
    print("format: text")
    print(f"tool_name: {TOOL_NAME}")
    print("scope: protocol probe only; this script does not execute the returned text")
    print(f"expected_input: {EXPECTED_INPUT!r}")

    client = build_client()
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            tools=[CUSTOM_TEXT_TOOL],
            tool_choice="required",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        print("\nProbe result:")
        print_table(
            ["status", "actual_model", "output_item_types", "elapsed_ms", "observation"],
            [["rejected", "", [], int((time.perf_counter() - started) * 1000), error_message(error)]],
        )
        return 0

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    RESPONSE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    match = find_custom_tool_call(payload)
    if match:
        path, call = match
        observed_input = str(call.get("input") or "")
        status = "supported_protocol"
        observation = f"{path} found"
    else:
        observed_input = ""
        status = "accepted_no_custom_call"
        observation = "request accepted, but no matching custom_tool_call was found"

    print("\nProbe result:")
    print_table(
        [
            "status",
            "actual_model",
            "response_status",
            "output_item_types",
            "elapsed_ms",
            "input_matches",
            "observed_input",
        ],
        [
            [
                status,
                getattr(response, "model", None) or payload.get("model") or "",
                getattr(response, "status", None) or payload.get("status") or "",
                output_item_types(payload),
                elapsed_ms,
                observed_input == EXPECTED_INPUT,
                observed_input,
            ]
        ],
    )

    print("\nObservation:")
    print(observation)
    print(f"response_json: {RESPONSE_JSON_PATH}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
