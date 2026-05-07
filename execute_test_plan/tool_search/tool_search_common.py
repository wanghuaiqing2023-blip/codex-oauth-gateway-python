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

TOOL_SEARCH_TOOL = {
    "type": "tool_search",
    "execution": "client",
    "description": (
        "# Tool discovery\n\n"
        "Searches over deferred tool metadata with BM25 and exposes matching tools "
        "for the next model call.\n\n"
        "You have access to tools from the following sources:\n"
        "- Calendar: Plan events and manage your calendar.\n"
        "Some tools may not have been provided upfront, and you should use this tool "
        "to search for the required tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for deferred tools."},
            "limit": {
                "type": "number",
                "description": "Maximum number of tools to return (defaults to 8).",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

SIMULATED_CALENDAR_NAMESPACE_TOOL = {
    "type": "namespace",
    "name": "mcp__codex_apps__calendar",
    "description": "Plan events and manage your calendar.",
    "tools": [
        {
            "type": "function",
            "name": "_create_event",
            "description": "Create a calendar event.",
            "strict": False,
            "defer_loading": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "starts_at": {"type": "string"},
                    "timezone": {"type": "string"},
                },
                "required": ["title", "starts_at"],
                "additionalProperties": False,
            },
        }
    ],
}

PROMPT_TOOL_SEARCH_CALL = (
    "A calendar event creation tool is deferred and is not otherwise visible. "
    "You must call tool_search to find that deferred tool. "
    "Search for a tool that can create calendar events. Do not answer directly."
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


def parse_arguments(tool_search_call: dict[str, Any]) -> dict[str, Any]:
    raw_arguments = tool_search_call.get("arguments")
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str) and raw_arguments:
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def first_tool_search_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    matches = find_objects_by_type(payload, "tool_search_call")
    return matches[0] if matches else None


def make_tool_search_call_context_item(tool_search_call: dict[str, Any]) -> dict[str, Any]:
    context_item = {
        "type": "tool_search_call",
        "call_id": tool_search_call["call_id"],
        "execution": tool_search_call.get("execution") or "client",
        "arguments": parse_arguments(tool_search_call),
    }
    if tool_search_call.get("id"):
        context_item["id"] = tool_search_call["id"]
    if tool_search_call.get("status"):
        context_item["status"] = tool_search_call["status"]
    return context_item


def make_tool_search_output(call_id: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "tool_search_output",
        "call_id": call_id,
        "status": "completed",
        "execution": "client",
        "tools": tools,
    }


def request_tool_search_call(client: OpenAI, response_json_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT_TOOL_SEARCH_CALL,
            tools=[TOOL_SEARCH_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        return {
            "phase": "tool_search_call",
            "status": "rejected",
            "actual_model": "",
            "output_item_types": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "call_id": "",
            "query": "",
            "limit": "",
            "response_json": "",
            "output_text": "",
            "observation": error_message(error),
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    response_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    match = first_tool_search_call(payload)
    if not match:
        return {
            "phase": "tool_search_call",
            "status": "accepted_no_tool_search_call",
            "actual_model": getattr(response, "model", None) or payload.get("model") or "",
            "output_item_types": output_item_types(payload),
            "elapsed_ms": elapsed_ms,
            "call_id": "",
            "query": "",
            "limit": "",
            "response_json": str(response_json_path),
            "output_text": output_text(response, payload),
            "observation": "no tool_search_call found",
        }

    path, tool_search_call = match
    arguments = parse_arguments(tool_search_call)
    call_id = str(tool_search_call.get("call_id") or "")
    return {
        "phase": "tool_search_call",
        "status": "supported" if call_id else "missing_call_id",
        "actual_model": getattr(response, "model", None) or payload.get("model") or "",
        "output_item_types": output_item_types(payload),
        "elapsed_ms": elapsed_ms,
        "call_id": call_id,
        "query": arguments.get("query", ""),
        "limit": arguments.get("limit", ""),
        "response_json": str(response_json_path),
        "output_text": output_text(response, payload),
        "observation": f"{path} found",
        "tool_search_call": tool_search_call,
    }


def request_after_tool_search_output(
    client: OpenAI,
    response_json_path: Path,
    prompt: str,
    tool_search_call: dict[str, Any],
    output_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    call_id = str(tool_search_call.get("call_id") or "")
    input_items = [
        {"role": "user", "content": prompt},
        make_tool_search_call_context_item(tool_search_call),
        make_tool_search_output(call_id, output_tools),
    ]
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=input_items,
            tools=[TOOL_SEARCH_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        return {
            "phase": "after_tool_search_output",
            "status": "rejected",
            "actual_model": "",
            "output_item_types": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "call_id": call_id,
            "query": "",
            "limit": "",
            "response_json": "",
            "output_text": "",
            "observation": error_message(error),
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    response_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    next_search = first_tool_search_call(payload)
    next_args = parse_arguments(next_search[1]) if next_search else {}
    return {
        "phase": "after_tool_search_output",
        "status": "accepted",
        "actual_model": getattr(response, "model", None) or payload.get("model") or "",
        "output_item_types": output_item_types(payload),
        "elapsed_ms": elapsed_ms,
        "call_id": str(next_search[1].get("call_id") or "") if next_search else "",
        "query": next_args.get("query", ""),
        "limit": next_args.get("limit", ""),
        "response_json": str(response_json_path),
        "output_text": output_text(response, payload),
        "observation": "response completed",
    }


def clean_result(result: dict[str, Any]) -> dict[str, Any]:
    clean = dict(result)
    clean.pop("tool_search_call", None)
    return clean


def write_result_files(
    title: str,
    result_json_path: Path,
    result_md_path: Path,
    results: list[dict[str, Any]],
    extra_payload: dict[str, Any] | None = None,
) -> None:
    clean_results = [clean_result(result) for result in results]
    payload = {
        "base_url": BASE_URL,
        "requested_model": MODEL,
        "tool": TOOL_SEARCH_TOOL,
        "results": clean_results,
    }
    if extra_payload:
        payload.update(extra_payload)
    result_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = [
        [
            result["phase"],
            result["status"],
            result["actual_model"],
            result["output_item_types"],
            result["call_id"],
            result["query"],
            result["limit"],
            result["elapsed_ms"],
            result["response_json"],
            result["observation"],
        ]
        for result in clean_results
    ]
    output_rows = [[result["phase"], result["output_text"]] for result in clean_results]
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
                        "phase",
                        "status",
                        "actual_model",
                        "output_item_types",
                        "call_id",
                        "query",
                        "limit",
                        "elapsed_ms",
                        "response_json",
                        "observation",
                    ],
                    rows,
                ),
                "## Output Text",
                markdown_table(["phase", "output_text"], output_rows),
            ]
        ),
        encoding="utf-8",
    )


def print_results(results: list[dict[str, Any]]) -> None:
    print_table(
        [
            "phase",
            "status",
            "actual_model",
            "output_item_types",
            "call_id",
            "query",
            "limit",
            "elapsed_ms",
            "observation",
        ],
        [
            [
                result["phase"],
                result["status"],
                result["actual_model"],
                result["output_item_types"],
                result["call_id"],
                result["query"],
                result["limit"],
                result["elapsed_ms"],
                result["observation"],
            ]
            for result in results
        ],
    )
