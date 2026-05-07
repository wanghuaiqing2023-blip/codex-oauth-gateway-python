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

WEB_SEARCH_TOOL = {"type": "web_search", "external_web_access": True}


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


def summarize_web_search_actions(calls: list[tuple[str, dict[str, Any]]]) -> tuple[list[str], list[str]]:
    action_types: list[str] = []
    action_urls: list[str] = []
    for _path, call in calls:
        action = call.get("action")
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if isinstance(action_type, str) and action_type not in action_types:
            action_types.append(action_type)
        action_url = action.get("url")
        if isinstance(action_url, str) and action_url not in action_urls:
            action_urls.append(action_url)
    return action_types, action_urls


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


def run_max_tool_calls_case(
    *,
    case_id: str,
    intent: str,
    max_tool_calls: int,
    prompt: str,
    response_json_path: Path,
    tool_choice: str | None = "required",
) -> dict[str, Any]:
    client = build_client()
    started = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "input": prompt,
            "tools": [WEB_SEARCH_TOOL],
            "max_tool_calls": max_tool_calls,
            "reasoning": {"effort": "low", "summary": "auto"},
            "text": {"verbosity": "low"},
        }
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        response = client.responses.create(**kwargs)
    except OpenAIError as error:
        return {
            "case": case_id,
            "intent": intent,
            "status": "rejected",
            "requested_model": MODEL,
            "actual_model": "",
            "requested_max_tool_calls": max_tool_calls,
            "response_max_tool_calls": "",
            "tool_choice": tool_choice or "<absent>",
            "response_status": "",
            "output_item_types": [],
            "web_search_call_count": 0,
            "action_types": [],
            "action_urls": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "response_json": "",
            "output_text": "",
            "observation": error_message(error),
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    response_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    calls = find_objects_by_type(payload, "web_search_call")
    action_types, action_urls = summarize_web_search_actions(calls)
    call_count = len(calls)
    status = "supported" if call_count <= max_tool_calls else "exceeded_limit"
    if max_tool_calls == 0 and call_count == 0:
        status = "accepted_without_tool_call"

    return {
        "case": case_id,
        "intent": intent,
        "status": status,
        "requested_model": MODEL,
        "actual_model": getattr(response, "model", None) or payload.get("model") or "",
        "requested_max_tool_calls": max_tool_calls,
        "response_max_tool_calls": payload.get("max_tool_calls"),
        "tool_choice": tool_choice or "<absent>",
        "response_status": getattr(response, "status", None) or payload.get("status") or "",
        "output_item_types": output_item_types(payload),
        "web_search_call_count": call_count,
        "action_types": action_types,
        "action_urls": action_urls,
        "elapsed_ms": elapsed_ms,
        "response_json": str(response_json_path),
        "output_text": output_text(response, payload),
        "observation": f"observed {call_count} web_search_call item(s)",
    }


def write_result_files(title: str, result_json_path: Path, result_md_path: Path, result: dict[str, Any]) -> None:
    result_json_path.write_text(
        json.dumps(
            {
                "base_url": BASE_URL,
                "requested_model": MODEL,
                "tool": WEB_SEARCH_TOOL,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary_rows = [
        [
            result["case"],
            result["status"],
            result["actual_model"],
            result["requested_max_tool_calls"],
            result["response_max_tool_calls"],
            result["tool_choice"],
            result["response_status"],
            result["output_item_types"],
            result["web_search_call_count"],
            result["action_types"],
            result["action_urls"],
            result["elapsed_ms"],
            result["observation"],
        ]
    ]
    result_md_path.write_text(
        "\n\n".join(
            [
                f"# {title}",
                f"- gateway base_url: `{BASE_URL}`",
                f"- requested_model: `{MODEL}`",
                "",
                "## Summary",
                markdown_table(
                    [
                        "case",
                        "status",
                        "actual_model",
                        "requested_max_tool_calls",
                        "response_max_tool_calls",
                        "tool_choice",
                        "response_status",
                        "output_item_types",
                        "web_search_call_count",
                        "action_types",
                        "action_urls",
                        "elapsed_ms",
                        "observation",
                    ],
                    summary_rows,
                ),
                "## Output Text",
                markdown_table(["case", "output_text"], [[result["case"], result["output_text"]]]),
            ]
        ),
        encoding="utf-8",
    )


def print_result(result: dict[str, Any]) -> None:
    print_table(
        [
            "case",
            "status",
            "actual_model",
            "requested_max_tool_calls",
            "response_max_tool_calls",
            "tool_choice",
            "response_status",
            "web_search_call_count",
            "action_types",
            "elapsed_ms",
            "observation",
        ],
        [
            [
                result["case"],
                result["status"],
                result["actual_model"],
                result["requested_max_tool_calls"],
                result["response_max_tool_calls"],
                result["tool_choice"],
                result["response_status"],
                result["web_search_call_count"],
                result["action_types"],
                result["elapsed_ms"],
                result["observation"],
            ]
        ],
    )
