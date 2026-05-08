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

SAFE_COMMAND_TEXT = "python --version"
SAFE_COMMAND_ARRAY = ["python", "--version"]
FINAL_MARKER = "gateway-shell-tool-roundtrip-ok"

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


APPROVAL_PROPERTIES = {
    "sandbox_permissions": {
        "type": "string",
        "description": (
            'Sandbox permissions for the command. Set to "require_escalated" to request '
            'running without sandbox restrictions; defaults to "use_default".'
        ),
    },
    "justification": {
        "type": "string",
        "description": 'Only set if sandbox_permissions is "require_escalated".',
    },
    "prefix_rule": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional prefix command pattern for repeated permission requests.",
    },
}


SHELL_COMMAND_TOOL = {
    "type": "function",
    "name": "shell_command",
    "description": "Runs a shell script in the user's default shell and returns its output.",
    "strict": False,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell script to execute in the user's default shell.",
            },
            "workdir": {
                "type": "string",
                "description": "The working directory to execute the command in.",
            },
            "timeout_ms": {
                "type": "number",
                "description": "The timeout for the command in milliseconds.",
            },
            "login": {
                "type": "boolean",
                "description": "Whether to run the shell with login shell semantics.",
            },
            **APPROVAL_PROPERTIES,
        },
        "required": ["command"],
    },
}


SHELL_TOOL = {
    "type": "function",
    "name": "shell",
    "description": "Runs a command array and returns its output.",
    "strict": False,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "command": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The command array to execute.",
            },
            "workdir": {
                "type": "string",
                "description": "The working directory to execute the command in.",
            },
            "timeout_ms": {
                "type": "number",
                "description": "The timeout for the command in milliseconds.",
            },
            **APPROVAL_PROPERTIES,
        },
        "required": ["command"],
    },
}


EXEC_COMMAND_TOOL = {
    "type": "function",
    "name": "exec_command",
    "description": "Runs a command in a PTY-style execution environment and returns its output.",
    "strict": False,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "cmd": {
                "type": "string",
                "description": "Shell command to execute.",
            },
            "workdir": {
                "type": "string",
                "description": "Optional working directory to run the command in.",
            },
            "shell": {
                "type": "string",
                "description": "Shell binary to launch.",
            },
            "tty": {
                "type": "boolean",
                "description": "Whether to allocate a TTY for the command.",
            },
            "yield_time_ms": {
                "type": "number",
                "description": "How long to wait in milliseconds before yielding.",
            },
            "max_output_tokens": {
                "type": "number",
                "description": "Maximum number of tokens to return.",
            },
            "login": {
                "type": "boolean",
                "description": "Whether to run the shell with login shell semantics.",
            },
            **APPROVAL_PROPERTIES,
        },
        "required": ["cmd"],
    },
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


def find_named_function_call(payload: dict[str, Any], tool_name: str) -> tuple[str, dict[str, Any]] | None:
    for path, item in find_objects_by_type(payload, "function_call"):
        if item.get("name") == tool_name:
            return path, item
    return None


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


def validate_safe_arguments(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    denied_permission = arguments.get("sandbox_permissions") == "require_escalated"
    if denied_permission:
        return False, "sandbox_permissions=require_escalated is outside this probe scope"

    workdir = arguments.get("workdir")
    if workdir not in (None, "", str(PROJECT_ROOT)):
        return False, f"unexpected workdir={workdir!r}"

    if tool_name == "shell_command":
        command = arguments.get("command")
        if command == SAFE_COMMAND_TEXT:
            return True, "command matched whitelist"
        return False, f"expected command={SAFE_COMMAND_TEXT!r}, got {command!r}"

    if tool_name == "shell":
        command = arguments.get("command")
        if command == SAFE_COMMAND_ARRAY:
            return True, "command array matched whitelist"
        return False, f"expected command={SAFE_COMMAND_ARRAY!r}, got {command!r}"

    if tool_name == "exec_command":
        command = arguments.get("cmd")
        if command == SAFE_COMMAND_TEXT:
            return True, "cmd matched whitelist"
        return False, f"expected cmd={SAFE_COMMAND_TEXT!r}, got {command!r}"

    return False, f"unknown tool_name={tool_name!r}"


def timeout_seconds(arguments: dict[str, Any]) -> float:
    timeout_ms = arguments.get("timeout_ms")
    if isinstance(timeout_ms, (int, float)) and timeout_ms > 0:
        return min(float(timeout_ms) / 1000.0, 10.0)
    return 10.0


def command_workdir(arguments: dict[str, Any]) -> str:
    workdir = arguments.get("workdir")
    if isinstance(workdir, str) and workdir:
        return workdir
    return str(PROJECT_ROOT)


def run_model_returned_command(tool_name: str, arguments: dict[str, Any]) -> str:
    started = time.perf_counter()
    timeout = timeout_seconds(arguments)
    cwd = command_workdir(arguments)

    if tool_name == "shell_command":
        command = str(arguments["command"])
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=True,
        )
        executed = command
    elif tool_name == "shell":
        command_array = [str(part) for part in arguments["command"]]
        completed = subprocess.run(
            command_array,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        executed = json.dumps(command_array, ensure_ascii=False)
    elif tool_name == "exec_command":
        command = str(arguments["cmd"])
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=True,
        )
        executed = command
    else:
        raise ValueError(f"unsupported tool_name={tool_name!r}")

    elapsed = time.perf_counter() - started
    output = (completed.stdout + completed.stderr).strip()
    return (
        f"Executed: {executed}\n"
        f"Workdir: {cwd}\n"
        f"Exit code: {completed.returncode}\n"
        f"Wall time: {elapsed:.2f} seconds\n"
        "Output:\n"
        f"{output}\n"
        f"Probe marker: {FINAL_MARKER}\n"
    )


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
    tool_name: str,
    summary_rows: list[list[Any]],
    detail_rows: list[list[Any]],
) -> None:
    result_json_path.write_text(
        json.dumps(
            {
                "base_url": BASE_URL,
                "requested_model": MODEL,
                "tool_name": tool_name,
                "summary": [dict(zip(RESULT_HEADERS, row)) for row in summary_rows],
                "details": detail_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    result_md_path.write_text(
        "\n\n".join(
            [
                f"# {title}",
                f"- gateway base_url: `{BASE_URL}`",
                f"- requested_model: `{MODEL}`",
                f"- tool_name: `{tool_name}`",
                "- execution guard: model-returned arguments are executed only after exact whitelist validation",
                "",
                "## Summary",
                markdown_table(RESULT_HEADERS, summary_rows),
                "## Details",
                markdown_table(["key", "value"], detail_rows),
            ]
        ),
        encoding="utf-8",
    )


def run_shell_tool_roundtrip(
    *,
    tool_name: str,
    tool_definition: dict[str, Any],
    phase1_prompt: str,
    response1_json_path: Path,
    response2_json_path: Path,
    result_json_path: Path,
    result_md_path: Path,
    title: str,
) -> int:
    client = build_client()
    started1 = time.perf_counter()

    try:
        response1 = client.responses.create(
            model=MODEL,
            input=phase1_prompt,
            tools=[tool_definition],
            tool_choice={"type": "function", "name": tool_name},
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows = [["phase1_tool_call", "rejected", "", "", [], int((time.perf_counter() - started1) * 1000), "", error_message(error)]]
        write_result_files(
            result_json_path=result_json_path,
            result_md_path=result_md_path,
            title=title,
            tool_name=tool_name,
            summary_rows=rows,
            detail_rows=[],
        )
        print_table(RESULT_HEADERS, rows)
        return 0

    elapsed1_ms = int((time.perf_counter() - started1) * 1000)
    payload1 = response_to_dict(response1)
    response1_json_path.write_text(json.dumps(payload1, ensure_ascii=False, indent=2), encoding="utf-8")

    actual_model1 = getattr(response1, "model", None) or payload1.get("model") or ""
    response_status1 = getattr(response1, "status", None) or payload1.get("status") or ""
    item_types1 = output_item_types(payload1)
    match = find_named_function_call(payload1, tool_name)

    if not match:
        rows = [
            [
                "phase1_tool_call",
                "accepted_no_function_call",
                actual_model1,
                response_status1,
                item_types1,
                elapsed1_ms,
                "",
                f"no function_call named {tool_name!r} found",
            ]
        ]
        details = [["response1_json", str(response1_json_path)]]
        write_result_files(
            result_json_path=result_json_path,
            result_md_path=result_md_path,
            title=title,
            tool_name=tool_name,
            summary_rows=rows,
            detail_rows=details,
        )
        print_table(RESULT_HEADERS, rows)
        return 0

    function_call_path, function_call = match
    call_id = str(function_call.get("call_id") or "")
    arguments = parse_arguments(function_call)
    safe, safety_observation = validate_safe_arguments(tool_name, arguments)

    if not call_id:
        rows = [
            [
                "phase1_tool_call",
                "missing_call_id",
                actual_model1,
                response_status1,
                item_types1,
                elapsed1_ms,
                "",
                f"{function_call_path} has no call_id",
            ]
        ]
        details = [
            ["function_call_path", function_call_path],
            ["arguments", arguments],
            ["response1_json", str(response1_json_path)],
        ]
        write_result_files(
            result_json_path=result_json_path,
            result_md_path=result_md_path,
            title=title,
            tool_name=tool_name,
            summary_rows=rows,
            detail_rows=details,
        )
        print_table(RESULT_HEADERS, rows)
        return 0

    if not safe:
        rows = [
            [
                "phase1_tool_call",
                "supported_protocol",
                actual_model1,
                response_status1,
                item_types1,
                elapsed1_ms,
                call_id,
                f"{function_call_path} found",
            ],
            [
                "phase2_tool_output",
                "blocked_unexpected_arguments",
                "",
                "",
                [],
                "",
                call_id,
                safety_observation,
            ],
        ]
        details = [
            ["function_call_path", function_call_path],
            ["arguments", arguments],
            ["safe_to_execute", False],
            ["safety_observation", safety_observation],
            ["response1_json", str(response1_json_path)],
        ]
        write_result_files(
            result_json_path=result_json_path,
            result_md_path=result_md_path,
            title=title,
            tool_name=tool_name,
            summary_rows=rows,
            detail_rows=details,
        )
        print_table(RESULT_HEADERS, rows)
        return 0

    tool_output = run_model_returned_command(tool_name, arguments)
    phase2_input = [
        {
            "role": "user",
            "content": (
                "Use the supplied shell tool output to answer. "
                f"Reply exactly with {FINAL_MARKER} and nothing else."
            ),
        },
        make_function_call_context_item(function_call),
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": tool_output,
        },
    ]

    started2 = time.perf_counter()
    try:
        response2 = client.responses.create(
            model=MODEL,
            input=phase2_input,
            tools=[tool_definition],
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
                item_types1,
                elapsed1_ms,
                call_id,
                f"{function_call_path} found",
            ],
            ["phase2_tool_output", "rejected", "", "", [], int((time.perf_counter() - started2) * 1000), call_id, error_message(error)],
        ]
        details = [
            ["function_call_path", function_call_path],
            ["arguments", arguments],
            ["safe_to_execute", True],
            ["tool_output", tool_output],
            ["response1_json", str(response1_json_path)],
        ]
        write_result_files(
            result_json_path=result_json_path,
            result_md_path=result_md_path,
            title=title,
            tool_name=tool_name,
            summary_rows=rows,
            detail_rows=details,
        )
        print_table(RESULT_HEADERS, rows)
        return 0

    elapsed2_ms = int((time.perf_counter() - started2) * 1000)
    payload2 = response_to_dict(response2)
    response2_json_path.write_text(json.dumps(payload2, ensure_ascii=False, indent=2), encoding="utf-8")
    actual_model2 = getattr(response2, "model", None) or payload2.get("model") or ""
    response_status2 = getattr(response2, "status", None) or payload2.get("status") or ""
    item_types2 = output_item_types(payload2)
    final_text = output_text(response2, payload2)
    expected_seen = FINAL_MARKER in final_text

    rows = [
        [
            "phase1_tool_call",
            "supported_protocol",
            actual_model1,
            response_status1,
            item_types1,
            elapsed1_ms,
            call_id,
            f"{function_call_path} found",
        ],
        [
            "phase2_tool_output",
            "supported_roundtrip" if expected_seen else "accepted_without_expected_text",
            actual_model2,
            response_status2,
            item_types2,
            elapsed2_ms,
            call_id,
            "final text contains marker" if expected_seen else "final text did not contain marker",
        ],
    ]
    details = [
        ["function_call_path", function_call_path],
        ["arguments", arguments],
        ["safe_to_execute", True],
        ["safety_observation", safety_observation],
        ["tool_output", tool_output],
        ["response1_json", str(response1_json_path)],
        ["response2_json", str(response2_json_path)],
        ["final_output_text", final_text],
    ]
    write_result_files(
        result_json_path=result_json_path,
        result_md_path=result_md_path,
        title=title,
        tool_name=tool_name,
        summary_rows=rows,
        detail_rows=details,
    )
    print_table(RESULT_HEADERS, rows)
    print("\nDetails:")
    for key, value in details:
        print(f"{key}: {value}")
    return 0


import json



TOOL_NAME = "shell"
RESPONSE1_JSON_PATH = OUTPUT_DIR / "shell_roundtrip_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "shell_roundtrip_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "shell_roundtrip_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "shell_roundtrip_results.md"

PHASE1_PROMPT = (
    "Call the shell function to inspect the local Python runtime. "
    f"The command argument must be exactly this JSON array: {json.dumps(SAFE_COMMAND_ARRAY)}. "
    "Do not answer directly."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: function")
    print(f"tool_name: {TOOL_NAME}")
    print("intent: verify Codex shell function-call roundtrip")
    print(f"allowed_command_array: {json.dumps(SAFE_COMMAND_ARRAY)}")
    print("\nRoundtrip result:")
    return run_shell_tool_roundtrip(
        tool_name=TOOL_NAME,
        tool_definition=SHELL_TOOL,
        phase1_prompt=PHASE1_PROMPT,
        response1_json_path=RESPONSE1_JSON_PATH,
        response2_json_path=RESPONSE2_JSON_PATH,
        result_json_path=RESULT_JSON_PATH,
        result_md_path=RESULT_MD_PATH,
        title="Shell Roundtrip Results",
    )


if __name__ == "__main__":
    raise SystemExit(main())
