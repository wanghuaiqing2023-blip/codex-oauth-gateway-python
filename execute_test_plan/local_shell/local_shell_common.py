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

LOCAL_SHELL_TOOL = {"type": "local_shell"}
SAFE_COMMAND = ["python", "--version"]
SIMULATED_SHELL_OUTPUT = (
    "Exit code: 0\n"
    "Wall time: 0.01 seconds\n"
    "Output:\n"
    "gateway-local-shell-roundtrip-ok\n"
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


def find_local_shell_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    matches = find_objects_by_type(payload, "local_shell_call")
    return matches[0] if matches else None


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


def action_command(local_shell_call: dict[str, Any]) -> list[str]:
    action = local_shell_call.get("action")
    if not isinstance(action, dict):
        return []
    command = action.get("command")
    if not isinstance(command, list):
        return []
    return [str(part) for part in command]


def make_local_shell_call_context_item(local_shell_call: dict[str, Any]) -> dict[str, Any]:
    action = local_shell_call.get("action")
    if not isinstance(action, dict):
        action = {"type": "exec", "command": action_command(local_shell_call)}
    item = {
        "type": "local_shell_call",
        "call_id": local_shell_call["call_id"],
        "status": local_shell_call.get("status") or "completed",
        "action": action,
    }
    if local_shell_call.get("id"):
        item["id"] = local_shell_call["id"]
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


def write_result_files(
    *,
    result_json_path: Path,
    result_md_path: Path,
    title: str,
    summary_rows: list[list[Any]],
    detail_rows: list[list[Any]] | None = None,
) -> None:
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
    result_json_path.write_text(
        json.dumps(
            {
                "base_url": BASE_URL,
                "requested_model": MODEL,
                "summary": [dict(zip(headers, row)) for row in summary_rows],
                "details": detail_rows or [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    sections = [
        f"# {title}",
        f"- gateway base_url: `{BASE_URL}`",
        f"- requested_model: `{MODEL}`",
        "- tool: `local_shell`",
        "- execution: client-local; this probe does not execute the generated command",
        "",
        "## Summary",
        markdown_table(headers, summary_rows),
    ]
    if detail_rows:
        sections.extend(
            [
                "## Details",
                markdown_table(["key", "value"], detail_rows),
            ]
        )
    result_md_path.write_text("\n\n".join(sections), encoding="utf-8")


def make_timing() -> tuple[float, callable]:
    started = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    return started, elapsed_ms
