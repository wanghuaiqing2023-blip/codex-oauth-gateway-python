from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from openai import APIStatusError, OpenAI, OpenAIError


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

OUTPUT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OUTPUT_DIR.parent.parent

SAFE_COMMAND = "python --version"
FINAL_MARKER = "openai-shell-local-roundtrip-ok"

RESULT_HEADERS = [
    "phase",
    "status",
    "actual_model",
    "response_status",
    "output_item_types",
    "elapsed_ms",
    "call_id",
    "observation",
]


OPENAI_SHELL_LOCAL_TOOL = {
    "type": "shell",
    "environment": {"type": "local"},
}

OPENAI_SHELL_HOSTED_TOOL = {
    "type": "shell",
    "environment": {"type": "container_auto"},
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


def error_payload(error: BaseException) -> dict[str, Any]:
    if isinstance(error, APIStatusError):
        try:
            payload = error.response.json()
        except Exception:
            payload = {"error": error.response.text}
        return {
            "status_code": error.status_code,
            "payload": payload,
        }
    return {
        "error_type": type(error).__name__,
        "message": str(error),
    }


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


def find_shell_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    matches = find_objects_by_type(payload, "shell_call")
    return matches[0] if matches else None


def find_shell_call_output(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    matches = find_objects_by_type(payload, "shell_call_output")
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


def shell_action(shell_call: dict[str, Any]) -> dict[str, Any]:
    action = shell_call.get("action")
    return action if isinstance(action, dict) else {}


def shell_commands(shell_call: dict[str, Any]) -> list[str]:
    commands = shell_action(shell_call).get("commands")
    if not isinstance(commands, list):
        return []
    return [str(command) for command in commands]


def max_output_length(shell_call: dict[str, Any]) -> int:
    raw = shell_action(shell_call).get("max_output_length")
    if isinstance(raw, int) and raw > 0:
        return min(raw, 8192)
    return 4096


def timeout_seconds(shell_call: dict[str, Any]) -> float:
    raw = shell_action(shell_call).get("timeout_ms")
    if isinstance(raw, (int, float)) and raw > 0:
        return min(float(raw) / 1000.0, 10.0)
    return 10.0


def validate_safe_shell_call(shell_call: dict[str, Any]) -> tuple[bool, str]:
    commands = shell_commands(shell_call)
    if commands == [SAFE_COMMAND]:
        return True, "command matched whitelist"
    return False, f"expected commands=[{SAFE_COMMAND!r}], got {commands!r}"


def make_shell_call_context_item(shell_call: dict[str, Any]) -> dict[str, Any]:
    item = {
        "type": "shell_call",
        "call_id": shell_call["call_id"],
        "action": shell_action(shell_call),
        "status": shell_call.get("status") or "completed",
    }
    if shell_call.get("id"):
        item["id"] = shell_call["id"]
    return item


def run_whitelisted_command(shell_call: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    command = shell_commands(shell_call)[0]
    timeout = timeout_seconds(shell_call)
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=True,
        )
    except subprocess.TimeoutExpired as error:
        stdout = (error.stdout or "") if isinstance(error.stdout, str) else ""
        stderr = (error.stderr or "") if isinstance(error.stderr, str) else ""
        return {
            "stdout": stdout[: max_output_length(shell_call)],
            "stderr": stderr[: max_output_length(shell_call)],
            "outcome": {"type": "timeout"},
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    output_limit = max_output_length(shell_call)
    return {
        "stdout": completed.stdout[:output_limit],
        "stderr": completed.stderr[:output_limit],
        "outcome": {"type": "exit", "exit_code": completed.returncode},
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def make_shell_call_output_item(shell_call: dict[str, Any], command_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "shell_call_output",
        "call_id": shell_call["call_id"],
        "max_output_length": max_output_length(shell_call),
        "output": [
            {
                "stdout": command_output["stdout"],
                "stderr": command_output["stderr"],
                "outcome": command_output["outcome"],
            }
        ],
    }


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
    tool: dict[str, Any],
    summary_rows: list[list[Any]],
    detail_rows: list[list[Any]] | None = None,
) -> None:
    result_json_path.write_text(
        json.dumps(
            {
                "base_url": BASE_URL,
                "requested_model": MODEL,
                "tool": tool,
                "summary": [dict(zip(RESULT_HEADERS, row)) for row in summary_rows],
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
        f"- tool: `{format_value(tool)}`",
        "",
        "## Summary",
        markdown_table(RESULT_HEADERS, summary_rows),
    ]
    if detail_rows:
        sections.extend(
            [
                "## Details",
                markdown_table(["key", "value"], detail_rows),
            ]
        )
    result_md_path.write_text("\n\n".join(sections), encoding="utf-8")


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


import json
import time

from openai import OpenAIError



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
