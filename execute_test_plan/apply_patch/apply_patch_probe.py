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
REPO_ROOT = OUTPUT_DIR.parent.parent
CODEX_GRAMMAR_PATH = REPO_ROOT / "codex" / "codex-rs" / "tools" / "src" / "tool_apply_patch.lark"
OFFICIAL_RESPONSE_JSON_PATH = OUTPUT_DIR / "apply_patch_official_response.json"
FREEFORM_RESPONSE_JSON_PATH = OUTPUT_DIR / "apply_patch_codex_freeform_response.json"

FALLBACK_APPLY_PATCH_GRAMMAR = """start: begin_patch hunk+ end_patch
begin_patch: "*** Begin Patch" LF
end_patch: "*** End Patch" LF?

hunk: add_hunk | delete_hunk | update_hunk
add_hunk: "*** Add File: " filename LF add_line+
delete_hunk: "*** Delete File: " filename LF
update_hunk: "*** Update File: " filename LF change_move? change?

filename: /(.+)/
add_line: "+" /(.*)/ LF -> line

change_move: "*** Move to: " filename LF
change: (change_context | change_line)+ eof_line?
change_context: ("@@" | "@@ " /(.+)/) LF
change_line: ("+" | "-" | " ") /(.*)/ LF
eof_line: "*** End of File" LF

%import common.LF
"""

PROMPT = (
    "Use the apply_patch tool to propose creating a file named "
    "execute_test_plan/apply_patch/apply_patch_probe_target.txt containing exactly one line: "
    "apply-patch-probe-ok. Do not modify any real files yourself; only emit the "
    "tool call."
)

OFFICIAL_HOSTED_APPLY_PATCH_TOOL = {"type": "apply_patch"}


def load_apply_patch_grammar() -> tuple[str, str]:
    if CODEX_GRAMMAR_PATH.exists():
        return CODEX_GRAMMAR_PATH.read_text(encoding="utf-8"), str(CODEX_GRAMMAR_PATH)
    return FALLBACK_APPLY_PATCH_GRAMMAR, "embedded fallback grammar"


def build_codex_freeform_apply_patch_tool() -> dict[str, Any]:
    grammar, _source = load_apply_patch_grammar()
    return {
        "type": "custom",
        "name": "apply_patch",
        "description": (
            "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, "
            "so do not wrap the patch in JSON."
        ),
        "format": {
            "type": "grammar",
            "syntax": "lark",
            "definition": grammar,
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


def find_tool_name_objects(value: Any, tool_name: str, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        matches: list[tuple[str, dict[str, Any]]] = []
        if value.get("name") == tool_name:
            matches.append((path, value))
        for child_key, child_value in value.items():
            matches.extend(find_tool_name_objects(child_value, tool_name, f"{path}.{child_key}"))
        return matches
    if isinstance(value, list):
        matches = []
        for index, child_value in enumerate(value):
            matches.extend(find_tool_name_objects(child_value, tool_name, f"{path}[{index}]"))
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


def summarize_patch_call(call: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    call_id = str(call.get("call_id") or call.get("id") or "")
    item_type = str(call.get("type") or "")
    name = str(call.get("name") or "")

    operation = call.get("operation")
    if isinstance(operation, dict):
        operation_type = str(operation.get("type") or "")
        path = str(operation.get("path") or "")
    else:
        operation_type = ""
        path = ""

    input_value = call.get("input") or call.get("arguments")
    if isinstance(input_value, dict):
        input_value = input_value.get("input")
    if not isinstance(input_value, str):
        input_value = ""

    if not path and "apply_patch_probe_target.txt" in input_value:
        path = "execute_test_plan/apply_patch/apply_patch_probe_target.txt"
    excerpt = input_value.replace("\r\n", "\n")[:240]

    return item_type, name, call_id, operation_type, path, excerpt


def find_apply_patch_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    official_calls = find_objects_by_type(payload, "apply_patch_call")
    if official_calls:
        return official_calls[0]

    custom_calls = [
        (path, call)
        for path, call in find_objects_by_type(payload, "custom_tool_call")
        if call.get("name") == "apply_patch"
    ]
    if custom_calls:
        return custom_calls[0]

    name_matches = find_tool_name_objects(payload, "apply_patch")
    if name_matches:
        return name_matches[0]
    return None


def run_case(
    client: OpenAI,
    *,
    case: str,
    tool_shape: dict[str, Any],
    response_json_path: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            tools=[tool_shape],
            tool_choice="required",
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        return {
            "case": case,
            "status": "rejected",
            "actual_model": "",
            "response_status": "",
            "output_item_types": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "call_type": "",
            "tool_name": "",
            "operation": "",
            "target_path": "",
            "observation": error_message(error),
            "call_id": "",
            "patch_excerpt": "",
            "response_json": "",
            "output_text": "",
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    response_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    match = find_apply_patch_call(payload)
    if match:
        path, call = match
        item_type, name, call_id, operation_type, target_path, excerpt = summarize_patch_call(call)
        status = "supported_protocol"
        observation = f"{path} found"
    else:
        item_type = ""
        name = ""
        call_id = ""
        operation_type = ""
        target_path = ""
        excerpt = ""
        status = "accepted_no_patch_call"
        observation = "request accepted, but no apply_patch call was found"

    return {
        "case": case,
        "status": status,
        "actual_model": getattr(response, "model", None) or payload.get("model") or "",
        "response_status": getattr(response, "status", None) or payload.get("status") or "",
        "output_item_types": output_item_types(payload),
        "elapsed_ms": elapsed_ms,
        "call_type": item_type,
        "tool_name": name,
        "operation": operation_type,
        "target_path": target_path,
        "observation": observation,
        "call_id": call_id,
        "patch_excerpt": excerpt,
        "response_json": str(response_json_path),
        "output_text": getattr(response, "output_text", None) or payload.get("output_text") or "",
    }


def main() -> int:
    grammar, grammar_source = load_apply_patch_grammar()
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: apply_patch")
    print("scope: protocol probe only; this script does not apply returned patches")
    print("intent: compare official hosted-tool shape with Codex freeform/custom shape")
    print(f"codex_freeform_grammar_source: {grammar_source}")
    print(f"codex_freeform_grammar_chars: {len(grammar)}")
    print(f"prompt: {PROMPT!r}")

    client = build_client()
    cases = [
        (
            "official_hosted_apply_patch",
            OFFICIAL_HOSTED_APPLY_PATCH_TOOL,
            OFFICIAL_RESPONSE_JSON_PATH,
        ),
        (
            "codex_freeform_apply_patch",
            build_codex_freeform_apply_patch_tool(),
            FREEFORM_RESPONSE_JSON_PATH,
        ),
    ]
    results = [
        run_case(client, case=case, tool_shape=tool_shape, response_json_path=response_json_path)
        for case, tool_shape, response_json_path in cases
    ]

    print("\nProbe results:")
    print_table(
        [
            "case",
            "status",
            "actual_model",
            "response_status",
            "output_item_types",
            "elapsed_ms",
            "call_type",
            "tool_name",
            "target_path",
        ],
        [
            [
                result["case"],
                result["status"],
                result["actual_model"],
                result["response_status"],
                result["output_item_types"],
                result["elapsed_ms"],
                result["call_type"],
                result["tool_name"],
                result["target_path"],
            ]
            for result in results
        ],
    )

    print("\nObservations:")
    for result in results:
        print(f"[{result['case']}]")
        print(f"observation: {result['observation']}")
        if result["call_id"]:
            print(f"call_id: {result['call_id']}")
        if result["response_json"]:
            print(f"response_json: {result['response_json']}")
        if result["patch_excerpt"]:
            print("patch_excerpt:")
            print(result["patch_excerpt"])
        if result["output_text"]:
            print(f"output_text: {result['output_text']!r}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
