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
PROJECT_ROOT = OUTPUT_DIR.parents[2]
WORKSPACE_DIR = OUTPUT_DIR / "apply_patch_article_workspace"
ARTICLE_RELATIVE_PATH = "examples/tool/apply_patch/apply_patch_article_workspace/gateway_note.md"
ARTICLE_PATH = PROJECT_ROOT / ARTICLE_RELATIVE_PATH

RESPONSE1_JSON_PATH = OUTPUT_DIR / "apply_patch_article_edit_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "apply_patch_article_edit_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "apply_patch_article_edit_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "apply_patch_article_edit_results.md"

FINAL_MARKER = "apply-patch-article-edit-ok"

INITIAL_ARTICLE = """# Gateway Note

This project is a proxy gateway. It forward requests to a backend.
The client side is hard to use because every caller builds JSON by hand.

## Problems

- Message construction is not consistent.
- Response parsing is scattered.
- Tool calls are confusing.

## Plan

We should document examples.
"""

APPLY_PATCH_FUNCTION_TOOL = {
    "type": "function",
    "name": "apply_patch",
    "description": (
        "Use the `apply_patch` tool to edit files. The input is the entire contents "
        "of the apply_patch command."
    ),
    "strict": False,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "input": {
                "type": "string",
                "description": "The entire contents of the apply_patch command.",
            }
        },
        "required": ["input"],
    },
}

EDIT_PROMPT = f"""You are editing this article file:
{ARTICLE_RELATIVE_PATH}

Current article:
```markdown
{INITIAL_ARTICLE}
```

Use the apply_patch function to make these editorial changes:

1. Change the title to "Gateway Client Usability Note".
2. Fix the grammar mistake "It forward" so the sentence reads naturally.
3. Improve the opening paragraph so it mentions OpenAI-compatible client wrappers.
4. Add one Problems bullet about model names being hard to discover from backend metadata.
5. Add a new "Recommendation" section that recommends small typed helpers for common request and response flows.

Only modify {ARTICLE_RELATIVE_PATH}. Use a normal apply_patch patch in the function argument named input.
Do not answer directly."""

FINAL_PROMPT = (
    "Use the supplied apply_patch tool output to answer. "
    f"Reply exactly with {FINAL_MARKER} and nothing else."
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


def find_apply_patch_function_call(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for path, item in find_objects_by_type(payload, "function_call"):
        if item.get("name") == "apply_patch":
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


def initialize_article() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLE_PATH.write_text(INITIAL_ARTICLE, encoding="utf-8")


def normalize_patch(patch: str) -> str:
    return patch.replace("\r\n", "\n").replace("\r", "\n")


def validate_patch_scope(patch: str) -> tuple[bool, str]:
    normalized = normalize_patch(patch)
    if not normalized.startswith("*** Begin Patch\n"):
        return False, "patch does not start with apply_patch begin marker"
    if "*** End Patch" not in normalized:
        return False, "patch does not contain apply_patch end marker"

    forbidden_markers = ["*** Add File:", "*** Delete File:", "*** Move to:"]
    for marker in forbidden_markers:
        if marker in normalized:
            return False, f"unexpected patch operation: {marker}"

    update_paths: list[str] = []
    for line in normalized.splitlines():
        if line.startswith("*** Update File: "):
            update_paths.append(line.removeprefix("*** Update File: ").strip())

    if update_paths != [ARTICLE_RELATIVE_PATH]:
        return False, f"expected one update path {ARTICLE_RELATIVE_PATH!r}, got {update_paths!r}"

    path = Path(update_paths[0])
    if path.is_absolute() or ".." in path.parts:
        return False, f"unsafe update path: {update_paths[0]}"

    return True, "patch scope is limited to the article file"


def parse_update_hunks(patch: str) -> list[list[str]]:
    normalized = normalize_patch(patch)
    lines = normalized.splitlines()
    hunks: list[list[str]] = []
    current: list[str] | None = None
    in_target_file = False

    for line in lines:
        if line == "*** Begin Patch":
            continue
        if line == "*** End Patch":
            if current is not None:
                hunks.append(current)
            break
        if line.startswith("*** Update File: "):
            in_target_file = line.removeprefix("*** Update File: ").strip() == ARTICLE_RELATIVE_PATH
            continue
        if not in_target_file:
            continue
        if line.startswith("@@"):
            if current is not None:
                hunks.append(current)
            current = []
            continue
        if current is None:
            continue
        if line == "*** End of File":
            continue
        current.append(line)

    if not hunks:
        raise ValueError("no update hunks found")
    return hunks


def find_subsequence(haystack: list[str], needle: list[str], start: int) -> int:
    if not needle:
        raise ValueError("empty hunk old block is not supported")
    for index in range(start, len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            return index
    raise ValueError(f"could not match hunk old block: {needle!r}")


def find_matching_blocks(
    current_lines: list[str],
    old_block: list[str],
    new_block: list[str],
    search_start: int,
) -> tuple[int, list[str], list[str]]:
    candidates = [(old_block, new_block)]
    trimmed_old = list(old_block)
    trimmed_new = list(new_block)

    while trimmed_old and trimmed_old[-1] == "":
        trimmed_old = trimmed_old[:-1]
        if trimmed_new and trimmed_new[-1] == "":
            trimmed_new = trimmed_new[:-1]
        candidates.append((trimmed_old, trimmed_new))

    last_error: ValueError | None = None
    for candidate_old, candidate_new in candidates:
        try:
            index = find_subsequence(current_lines, candidate_old, search_start)
        except ValueError as error:
            last_error = error
            continue
        return index, candidate_old, candidate_new

    if last_error is not None:
        raise last_error
    raise ValueError(f"could not match hunk old block: {old_block!r}")


def apply_update_hunks(original_text: str, hunks: list[list[str]]) -> str:
    current_lines = original_text.splitlines()
    search_start = 0

    for hunk in hunks:
        old_block: list[str] = []
        new_block: list[str] = []
        for line in hunk:
            if not line:
                raise ValueError("empty patch line without prefix")
            prefix = line[0]
            content = line[1:]
            if prefix == " ":
                old_block.append(content)
                new_block.append(content)
            elif prefix == "-":
                old_block.append(content)
            elif prefix == "+":
                new_block.append(content)
            else:
                raise ValueError(f"unexpected hunk line prefix: {line!r}")

        index, matched_old_block, matched_new_block = find_matching_blocks(
            current_lines,
            old_block,
            new_block,
            search_start,
        )
        current_lines[index : index + len(matched_old_block)] = matched_new_block
        search_start = index + len(matched_new_block)

    return "\n".join(current_lines) + "\n"


def validate_article_result(article: str) -> list[str]:
    checks = [
        ("title_changed", "# Gateway Client Usability Note" in article),
        ("grammar_fixed", "It forwards requests" in article or "forwards requests" in article),
        ("old_grammar_removed", "It forward requests" not in article),
        ("client_wrappers", "OpenAI-compatible" in article and "client" in article.lower()),
        ("model_names_problem", "model" in article.lower() and "metadata" in article.lower()),
        ("recommendation_section", "## Recommendation" in article),
        ("typed_helpers", "typed helpers" in article.lower()),
    ]
    return [name for name, passed in checks if not passed]


def apply_model_patch(patch: str) -> str:
    safe, observation = validate_patch_scope(patch)
    if not safe:
        raise ValueError(observation)

    original_text = ARTICLE_PATH.read_text(encoding="utf-8")
    hunks = parse_update_hunks(patch)
    updated_text = apply_update_hunks(original_text, hunks)
    missing = validate_article_result(updated_text)
    if missing:
        raise ValueError(f"article failed semantic checks: {missing}")

    ARTICLE_PATH.write_text(updated_text, encoding="utf-8")
    return (
        "Success. Updated the following files:\n"
        f"- {ARTICLE_RELATIVE_PATH}\n"
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


def write_result_files(summary_rows: list[list[Any]], detail_rows: list[list[Any]]) -> None:
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
                "article_path": str(ARTICLE_PATH),
                "summary": [dict(zip(headers, row)) for row in summary_rows],
                "details": detail_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    RESULT_MD_PATH.write_text(
        "\n\n".join(
            [
                "# Apply Patch Article Edit Results",
                f"- gateway base_url: `{BASE_URL}`",
                f"- requested_model: `{MODEL}`",
                "- tool type: `function`",
                "- tool name: `apply_patch`",
                f"- article file: `{ARTICLE_PATH}`",
                "",
                "## Summary",
                markdown_table(headers, summary_rows),
                "## Details",
                markdown_table(["key", "value"], detail_rows),
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: function")
    print("tool_name: apply_patch")
    print("intent: test whether the model can generate a precise patch for an article edit")
    print(f"article_file: {ARTICLE_PATH}")

    initialize_article()
    client = build_client()

    started1 = time.perf_counter()
    try:
        response1 = client.responses.create(
            model=MODEL,
            input=EDIT_PROMPT,
            tools=[APPLY_PATCH_FUNCTION_TOOL],
            tool_choice={"type": "function", "name": "apply_patch"},
            reasoning={"effort": "medium", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows = [["phase1_tool_call", "rejected", "", "", [], int((time.perf_counter() - started1) * 1000), "", error_message(error)]]
        write_result_files(rows, [["initial_article", INITIAL_ARTICLE]])
        print_table(
            ["phase", "status", "actual_model", "response_status", "output_item_types", "elapsed_ms", "call_id", "observation"],
            rows,
        )
        return 0

    elapsed1_ms = int((time.perf_counter() - started1) * 1000)
    payload1 = response_to_dict(response1)
    RESPONSE1_JSON_PATH.write_text(json.dumps(payload1, ensure_ascii=False, indent=2), encoding="utf-8")
    actual_model1 = getattr(response1, "model", None) or payload1.get("model") or ""
    response_status1 = getattr(response1, "status", None) or payload1.get("status") or ""
    item_types1 = output_item_types(payload1)
    match = find_apply_patch_function_call(payload1)

    if not match:
        rows = [
            [
                "phase1_tool_call",
                "accepted_no_apply_patch_call",
                actual_model1,
                response_status1,
                item_types1,
                elapsed1_ms,
                "",
                "request accepted but no function_call named apply_patch found",
            ]
        ]
        write_result_files(rows, [["response1_json", str(RESPONSE1_JSON_PATH)]])
        print_table(
            ["phase", "status", "actual_model", "response_status", "output_item_types", "elapsed_ms", "call_id", "observation"],
            rows,
        )
        return 0

    function_call_path, function_call = match
    call_id = str(function_call.get("call_id") or "")
    arguments = parse_arguments(function_call)
    patch_input = arguments.get("input")
    if not isinstance(patch_input, str):
        patch_input = ""

    try:
        apply_output = apply_model_patch(patch_input)
        patch_applied = True
        patch_observation = "model patch parsed, matched article context, and passed semantic checks"
    except ValueError as error:
        apply_output = f"Patch blocked: {error}"
        patch_applied = False
        patch_observation = str(error)

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
        ]
    ]

    if not patch_applied:
        rows.append(["patch_apply", "blocked_patch", "", "", [], "", call_id, patch_observation])
        details = [
            ["function_call_path", function_call_path],
            ["arguments", arguments],
            ["patch_input", patch_input],
            ["apply_output", apply_output],
            ["response1_json", str(RESPONSE1_JSON_PATH)],
            ["article_after_attempt", ARTICLE_PATH.read_text(encoding="utf-8")],
        ]
        write_result_files(rows, details)
        print_table(
            ["phase", "status", "actual_model", "response_status", "output_item_types", "elapsed_ms", "call_id", "observation"],
            rows,
        )
        return 0

    phase2_input = [
        {"role": "user", "content": FINAL_PROMPT},
        make_function_call_context_item(function_call),
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": apply_output,
        },
    ]

    started2 = time.perf_counter()
    try:
        response2 = client.responses.create(
            model=MODEL,
            input=phase2_input,
            tools=[APPLY_PATCH_FUNCTION_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        rows.append(["phase2_tool_output", "rejected", "", "", [], int((time.perf_counter() - started2) * 1000), call_id, error_message(error)])
        details = [
            ["function_call_path", function_call_path],
            ["arguments", arguments],
            ["patch_input", patch_input],
            ["apply_output", apply_output],
            ["response1_json", str(RESPONSE1_JSON_PATH)],
            ["article_after_patch", ARTICLE_PATH.read_text(encoding="utf-8")],
        ]
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
    article_after_patch = ARTICLE_PATH.read_text(encoding="utf-8")
    missing_checks = validate_article_result(article_after_patch)
    roundtrip_ok = FINAL_MARKER in final_text and not missing_checks

    rows.append(
        [
            "phase2_tool_output",
            "supported_roundtrip" if roundtrip_ok else "accepted_without_expected_state",
            getattr(response2, "model", None) or payload2.get("model") or "",
            getattr(response2, "status", None) or payload2.get("status") or "",
            output_item_types(payload2),
            elapsed2_ms,
            call_id,
            "article edit and final marker are correct" if roundtrip_ok else f"missing checks: {missing_checks}",
        ]
    )
    details = [
        ["function_call_path", function_call_path],
        ["arguments", arguments],
        ["patch_input", patch_input],
        ["apply_output", apply_output],
        ["response1_json", str(RESPONSE1_JSON_PATH)],
        ["response2_json", str(RESPONSE2_JSON_PATH)],
        ["initial_article", INITIAL_ARTICLE],
        ["article_after_patch", article_after_patch],
        ["final_output_text", final_text],
    ]
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
