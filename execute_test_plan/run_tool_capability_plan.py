from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from openai import APIStatusError, OpenAI, OpenAIError


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")
VECTOR_STORE_ENV = "CODEX_GATEWAY_VECTOR_STORE_ID"

OUTPUT_DIR = Path(__file__).resolve().parent
RESULT_JSON = OUTPUT_DIR / "tool_capability_results.json"
RESULT_MD = OUTPUT_DIR / "tool_capability_results.md"


def gateway_root() -> str:
    parsed = urlsplit(BASE_URL)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def build_client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY, max_retries=0)


def fetch_json(path: str) -> dict[str, Any]:
    url = f"{gateway_root()}{path}"
    with urllib.request.urlopen(url) as response:  # noqa: S310 - local configured gateway URL.
        return json.loads(response.read().decode("utf-8"))


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


def find_key_values(value: Any, key: str, path: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        matches: list[tuple[str, Any]] = []
        for child_key, child_value in value.items():
            child_path = f"{path}.{child_key}"
            if child_key == key:
                matches.append((child_path, child_value))
            matches.extend(find_key_values(child_value, key, child_path))
        return matches
    if isinstance(value, list):
        matches = []
        for index, child_value in enumerate(value):
            matches.extend(find_key_values(child_value, key, f"{path}[{index}]"))
        return matches
    return []


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


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def truncate(value: Any, limit: int = 220) -> str:
    text = value if isinstance(value, str) else compact_json(value)
    text = text.replace("\r", " ").replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict, tuple)):
        return compact_json(value)
    return str(value)


def print_table(headers: list[str], rows: list[list[Any]]) -> None:
    values = [[format_value(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        if len(row) != len(headers):
            raise ValueError(f"row has {len(row)} columns but table has {len(headers)} headers")
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()

    print(format_row(headers))
    print(format_row(["-" * width for width in widths]))
    for row in values:
        print(format_row(row))


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    values = [[format_value(value) for value in row] for row in rows]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in values:
        escaped = [cell.replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def observation_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return compact_json(value)


def result_note(row: dict[str, Any]) -> str:
    status = str(row.get("status") or "")
    observation = observation_text(row.get("observation"))
    output_types = row.get("output_item_types") or []
    output_types_text = " ".join(str(item) for item in output_types)
    evidence_text = f"{output_types_text} {observation}"

    if status == "supported":
        if row.get("tool") == "gateway_health":
            return "gateway healthy"
        if row.get("tool") == "capability_discovery":
            return observation or "models discovered"
        if "request accepted without function_call" in observation:
            return "tool_choice=none suppressed function_call"
        if "$.output_text=" in observation:
            return "function output accepted"
        for object_type in [
            "web_search_call",
            "function_call",
            "image_generation_call",
            "file_search_call",
            "code_interpreter_call",
            "computer_call",
            "local_shell_call",
        ]:
            if object_type in evidence_text:
                return f"found {object_type}"
        return "request accepted"

    if status == "accepted_no_evidence":
        return "request accepted; no expected object observed"

    if status == "skipped":
        if VECTOR_STORE_ENV in observation:
            return f"missing {VECTOR_STORE_ENV}"
        return truncate(observation, 100)

    if status in {"rejected", "client_error"}:
        return truncate(observation, 100)

    return truncate(observation, 100) if observation else status


def summary_rows(rows: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            row["case"],
            row["tool"],
            row["status"],
            row["elapsed_ms"],
            result_note(row),
        ]
        for row in rows
    ]


def status_summary_rows(rows: list[dict[str, Any]]) -> list[list[Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1

    preferred_order = ["supported", "accepted_no_evidence", "rejected", "client_error", "skipped"]
    ordered_statuses = [status for status in preferred_order if status in counts]
    ordered_statuses.extend(sorted(status for status in counts if status not in preferred_order))
    return [[status, counts[status]] for status in ordered_statuses]


def visible_api_models(payload: dict[str, Any]) -> list[dict[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    result = []
    for model in models:
        if not isinstance(model, dict):
            continue
        if model.get("visibility") == "list" and model.get("supported_in_api") is True:
            result.append(model)
    return result


def derive_tool_candidates(model: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    if model.get("supports_search_tool") is True:
        candidates.append("web_search")
    if model.get("apply_patch_tool_type"):
        candidates.append("apply_patch")
    for tool in model.get("experimental_supported_tools") or []:
        candidates.append(str(tool))
    if "image" in (model.get("input_modalities") or []):
        candidates.append("image_input")
    return candidates


def make_result(
    *,
    case: str,
    tool: str,
    source: str,
    status: str,
    actual_model: str = "",
    output_types: list[str] | None = None,
    observation: Any = "",
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "case": case,
        "tool": tool,
        "source": source,
        "status": status,
        "actual_model": actual_model,
        "output_item_types": output_types or [],
        "elapsed_ms": elapsed_ms,
        "observation": observation_text(observation),
    }


def run_response_case(
    client: OpenAI,
    *,
    case: str,
    tool: str,
    source: str,
    request: dict[str, Any],
    expected_object_type: str | None = None,
    expected_key: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.responses.create(**request)
    except OpenAIError as error:
        return make_result(
            case=case,
            tool=tool,
            source=source,
            status="rejected",
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            observation=error_message(error),
        )
    except Exception as error:  # noqa: BLE001 - report client-side probe failures.
        return make_result(
            case=case,
            tool=tool,
            source=source,
            status="client_error",
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            observation=f"{type(error).__name__}: {error}",
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    types = output_item_types(payload)
    object_matches = find_objects_by_type(payload, expected_object_type) if expected_object_type else []
    key_matches = find_key_values(payload, expected_key) if expected_key else []
    has_evidence = bool(object_matches or key_matches)
    status = "supported" if has_evidence else "accepted_no_evidence"
    observation = "request accepted"
    if object_matches:
        observation = f"{object_matches[0][0]}={compact_json(object_matches[0][1])}"
    elif key_matches:
        observation = f"{key_matches[0][0]}={observation_text(key_matches[0][1])}"
    elif getattr(response, "output_text", None):
        observation = f"output_text={getattr(response, 'output_text')}"

    return make_result(
        case=case,
        tool=tool,
        source=source,
        status=status,
        actual_model=str(getattr(response, "model", "") or ""),
        output_types=types,
        elapsed_ms=elapsed_ms,
        observation=observation,
    )


def parse_vector_store_ids() -> list[str]:
    raw = os.getenv(VECTOR_STORE_ENV, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


FUNCTION_TOOL = {
    "type": "function",
    "name": "get_gateway_probe_value",
    "description": "Return a deterministic value for the gateway tool probe.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The key to look up. Use probe_status for this test.",
            }
        },
        "required": ["key"],
        "additionalProperties": False,
    },
}


def run_function_call_output_probe(client: OpenAI) -> dict[str, Any]:
    first = None
    try:
        first = client.responses.create(
            model=MODEL,
            input="Call get_gateway_probe_value with key probe_status. Do not answer directly.",
            tools=[FUNCTION_TOOL],
            tool_choice="required",
        )
    except OpenAIError as error:
        return make_result(
            case="34A",
            tool="function_call_output",
            source="OpenAI official API",
            status="rejected",
            observation=f"first call failed: {error_message(error)}",
        )
    except Exception as error:  # noqa: BLE001
        return make_result(
            case="34A",
            tool="function_call_output",
            source="OpenAI official API",
            status="client_error",
            observation=f"first call failed: {type(error).__name__}: {error}",
        )

    first_payload = response_to_dict(first)
    calls = find_objects_by_type(first_payload, "function_call")
    if not calls:
        return make_result(
            case="34A",
            tool="function_call_output",
            source="OpenAI official API",
            status="skipped",
            actual_model=str(getattr(first, "model", "") or ""),
            output_types=output_item_types(first_payload),
            observation="first call did not produce function_call",
        )

    call = calls[0][1]
    call_id = call.get("call_id") or call.get("id")
    if not call_id:
        return make_result(
            case="34A",
            tool="function_call_output",
            source="OpenAI official API",
            status="skipped",
            actual_model=str(getattr(first, "model", "") or ""),
            output_types=output_item_types(first_payload),
            observation="function_call did not include call_id",
        )

    input_items = [
        {"role": "user", "content": "Call get_gateway_probe_value with key probe_status, then report the value."},
        call,
        {"type": "function_call_output", "call_id": call_id, "output": '{"probe_status":"function-output-ok"}'},
    ]
    return run_response_case(
        client,
        case="34A",
        tool="function_call_output",
        source="OpenAI official API",
        request={
            "model": MODEL,
            "input": input_items,
            "tools": [FUNCTION_TOOL],
        },
        expected_key="output_text",
    )


def run_plan() -> dict[str, Any]:
    client = build_client()
    results: list[dict[str, Any]] = []
    model_rows: list[list[Any]] = []

    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")

    try:
        health = fetch_json("/health")
        results.append(
            make_result(
                case="00A",
                tool="gateway_health",
                source="gateway",
                status="supported" if health.get("ok") else "rejected",
                observation=health,
            )
        )
    except Exception as error:  # noqa: BLE001
        results.append(
            make_result(
                case="00A",
                tool="gateway_health",
                source="gateway",
                status="rejected",
                observation=f"{type(error).__name__}: {error}",
            )
        )

    try:
        models_payload = fetch_json("/codex/models")
        models = visible_api_models(models_payload)
        for model in models:
            model_rows.append(
                [
                    model.get("slug"),
                    model.get("supports_search_tool"),
                    model.get("web_search_tool_type"),
                    model.get("apply_patch_tool_type"),
                    model.get("experimental_supported_tools") or [],
                    model.get("input_modalities") or [],
                    derive_tool_candidates(model),
                ]
            )
        results.append(
            make_result(
                case="31A",
                tool="capability_discovery",
                source="/codex/models",
                status="supported",
                observation=f"visible_api_models={len(models)}",
            )
        )
    except (urllib.error.URLError, json.JSONDecodeError, Exception) as error:  # noqa: BLE001
        results.append(
            make_result(
                case="31A",
                tool="capability_discovery",
                source="/codex/models",
                status="rejected",
                observation=f"{type(error).__name__}: {error}",
            )
        )

    print("\nModel tool metadata:")
    if model_rows:
        print_table(
            [
                "model",
                "search",
                "search_type",
                "patch_type",
                "experimental",
                "modalities",
                "derived_tools",
            ],
            model_rows,
        )
    else:
        print("(no model metadata)")

    web_search_cases = [
        (
            "32A",
            {"type": "web_search", "external_web_access": True},
            "live web search",
        ),
        (
            "32B",
            {"type": "web_search", "external_web_access": False},
            "cached or non-live web search",
        ),
        (
            "32C",
            {"type": "web_search", "external_web_access": True, "search_context_size": "low"},
            "search_context_size",
        ),
        (
            "32D",
            {
                "type": "web_search",
                "external_web_access": True,
                "user_location": {
                    "type": "approximate",
                    "country": "US",
                    "city": "San Francisco",
                    "region": "California",
                    "timezone": "America/Los_Angeles",
                },
            },
            "user_location",
        ),
        (
            "32E",
            {
                "type": "web_search",
                "external_web_access": True,
                "filters": {"allowed_domains": ["openai.com"]},
            },
            "filters allowed_domains",
        ),
        (
            "32F",
            {
                "type": "web_search",
                "external_web_access": True,
                "search_content_types": ["text", "image"],
            },
            "text_and_image search_content_types",
        ),
    ]
    for case, tool_shape, intent in web_search_cases:
        results.append(
            run_response_case(
                client,
                case=case,
                tool="web_search",
                source=f"Codex CLI + models ({intent})",
                request={
                    "model": MODEL,
                    "input": (
                        "Use web search to find the current title or headline on openai.com. "
                        "Answer in one short sentence."
                    ),
                    "tools": [tool_shape],
                    "tool_choice": "required",
                    "include": ["web_search_call.results", "web_search_call.action.sources"],
                },
                expected_object_type="web_search_call",
            )
        )

    function_cases = [
        ("33A", "auto", "Call get_gateway_probe_value with key probe_status if a tool is available."),
        ("33B", "required", "Call get_gateway_probe_value with key probe_status. Do not answer directly."),
        ("33C", "none", "Do not call tools. Reply exactly: function-none-ok"),
        (
            "33D",
            {"type": "function", "name": "get_gateway_probe_value"},
            "Call get_gateway_probe_value with key probe_status. Do not answer directly.",
        ),
    ]
    for case, tool_choice, prompt in function_cases:
        result = run_response_case(
            client,
            case=case,
            tool="function",
            source="OpenAI official API",
            request={
                "model": MODEL,
                "input": prompt,
                "tools": [FUNCTION_TOOL],
                "tool_choice": tool_choice,
            },
            expected_object_type="function_call" if tool_choice != "none" else None,
        )
        if tool_choice == "none" and result["status"] == "accepted_no_evidence":
            result["status"] = "supported"
            result["observation"] = "request accepted without function_call"
        results.append(result)

    results.append(run_function_call_output_probe(client))

    vector_store_ids = parse_vector_store_ids()
    if not vector_store_ids:
        results.append(
            make_result(
                case="13A",
                tool="file_search",
                source="OpenAI official API",
                status="skipped",
                observation=f"set {VECTOR_STORE_ENV} to run file_search with vector_store_ids",
            )
        )
    else:
        results.append(
            run_response_case(
                client,
                case="13B",
                tool="file_search",
                source="OpenAI official API",
                request={
                    "model": MODEL,
                    "input": "Search the supplied files for information about this gateway.",
                    "tools": [{"type": "file_search", "vector_store_ids": vector_store_ids}],
                    "include": ["file_search_call.results"],
                },
                expected_object_type="file_search_call",
            )
        )

    boundary_cases = [
        (
            "14A",
            "code_interpreter",
            {
                "model": MODEL,
                "input": "Use code interpreter to compute sum(range(1, 11)) and reply with the result.",
                "tools": [{"type": "code_interpreter", "container": {"type": "auto"}}],
                "include": ["code_interpreter_call.outputs"],
            },
            "code_interpreter_call",
        ),
        (
            "15A",
            "computer_use_preview",
            {
                "model": MODEL,
                "input": "If a computer tool is available, request a harmless screenshot action.",
                "tools": [
                    {
                        "type": "computer_use_preview",
                        "display_width": 1024,
                        "display_height": 768,
                        "environment": "browser",
                    }
                ],
                "include": ["computer_call_output.output.image_url"],
            },
            "computer_call",
        ),
        (
            "16A",
            "local_shell",
            {
                "model": MODEL,
                "input": (
                    "Use the local_shell tool to run exactly this command array: "
                    '["python","--version"]. Do not answer directly.'
                ),
                "tools": [{"type": "local_shell"}],
                "tool_choice": "required",
            },
            "local_shell_call",
        ),
        (
            "35A",
            "image_generation",
            {
                "model": MODEL,
                "input": "If image generation is available, create a tiny simple red square.",
                "tools": [{"type": "image_generation", "output_format": "png"}],
            },
            "image_generation_call",
        ),
    ]
    for case, tool, request, expected_type in boundary_cases:
        results.append(
            run_response_case(
                client,
                case=case,
                tool=tool,
                source="OpenAI/Codex tool shape",
                request=request,
                expected_object_type=expected_type,
            )
        )

    print("\nTool probe results:")
    print_table(
        ["case", "tool", "status", "elapsed_ms", "note"],
        summary_rows(results),
    )

    print("\nStatus summary:")
    print_table(
        ["status", "count"],
        status_summary_rows(results),
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "requested_model": MODEL,
        "vector_store_env": VECTOR_STORE_ENV,
        "model_tool_metadata": model_rows,
        "results": results,
    }


def write_results(payload: dict[str, Any]) -> None:
    RESULT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = payload["results"]
    md = [
        "# Tool Capability Results",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- base_url: `{payload['base_url']}`",
        f"- requested_model: `{payload['requested_model']}`",
        "",
        "## Status Summary",
        "",
        md_table(["status", "count"], status_summary_rows(rows)),
        "",
        "## Probe Results",
        "",
        md_table(
            ["case", "tool", "status", "elapsed_ms", "note"],
            summary_rows(rows),
        ),
        "",
        "Full observations, source labels, actual models, and output item types are in the JSON result file.",
        "",
        "## Model Tool Metadata",
        "",
        md_table(
            [
                "model",
                "search",
                "search_type",
                "patch_type",
                "experimental",
                "modalities",
                "derived_tools",
            ],
            payload["model_tool_metadata"],
        )
        if payload["model_tool_metadata"]
        else "(no model metadata)",
        "",
    ]
    RESULT_MD.write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    payload = run_plan()
    write_results(payload)
    print("\nWrote:")
    print(f"- {relative_path(RESULT_MD)}")
    print(f"- {relative_path(RESULT_JSON)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
