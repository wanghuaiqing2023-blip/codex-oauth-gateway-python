from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import APIStatusError, OpenAI


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

OUTPUT_DIR = Path(__file__).resolve().parent

RESULT_HEADERS = ["case", "tool", "status", "elapsed_ms", "note"]
MCP_EVIDENCE_TYPES = ("mcp_list_tools", "mcp_call", "mcp_approval_request")


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


def output_item_types(payload: dict[str, Any]) -> list[str]:
    output = payload.get("output")
    if not isinstance(output, list):
        return []
    return [str(item.get("type", "<missing>")) for item in output if isinstance(item, dict)]


def classify_mcp_response(payload: dict[str, Any]) -> tuple[str, str, list[list[Any]]]:
    details: list[list[Any]] = []
    for evidence_type in MCP_EVIDENCE_TYPES:
        matches = find_objects_by_type(payload, evidence_type)
        if not matches:
            continue
        path, item = matches[0]
        details.append(["evidence_type", evidence_type])
        details.append(["evidence_path", path])
        details.append(["evidence_item", item])
        return "supported_unexpectedly", f"found {evidence_type}", details
    return "accepted_no_evidence", "request accepted; no MCP output item observed", details


def make_result_record(
    *,
    case: str,
    tool: str,
    status: str,
    elapsed_ms: int,
    note: str,
    actual_model: str = "",
    response_status: str = "",
    output_types: list[str] | None = None,
    response_json: str = "",
) -> dict[str, Any]:
    return {
        "case": case,
        "tool": tool,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "note": note,
        "actual_model": actual_model,
        "response_status": response_status,
        "output_item_types": output_types or [],
        "response_json": response_json,
    }


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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


def rows_from_records(records: list[dict[str, Any]]) -> list[list[Any]]:
    return [[record.get(header, "") for header in RESULT_HEADERS] for record in records]


def write_result_files(
    *,
    result_json_path: Path,
    result_md_path: Path,
    title: str,
    tool: dict[str, Any],
    prompt: str,
    records: list[dict[str, Any]],
    details: list[list[Any]],
    evidence: dict[str, Any],
) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    result_json_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "base_url": BASE_URL,
                "requested_model": MODEL,
                "tool": tool,
                "prompt": prompt,
                "results": records,
                "details": details,
                "evidence": evidence,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    sections = [
        f"# {title}",
        f"- generated_at: `{generated_at}`",
        f"- gateway base_url: `{BASE_URL}`",
        f"- requested_model: `{MODEL}`",
        f"- tool: `{format_value(tool)}`",
        "",
        "## Summary",
        markdown_table(RESULT_HEADERS, rows_from_records(records)),
    ]
    if details:
        sections.extend(
            [
                "## Details",
                markdown_table(["key", "value"], details),
            ]
        )
    result_md_path.write_text("\n\n".join(sections), encoding="utf-8")


def print_result(records: list[dict[str, Any]], result_json_path: Path, result_md_path: Path) -> None:
    print("\nProbe result:")
    print_table(RESULT_HEADERS, rows_from_records(records))
    print("\nWrote:")
    print(f"- {result_md_path}")
    print(f"- {result_json_path}")


import json
import time

from openai import OpenAIError



CASE_NAME = "connector_mcp_invalid_auth"
TOOL_NAME = "OpenAI MCP connector"
RESPONSE_JSON_PATH = OUTPUT_DIR / "openai_mcp_connector_negative_response.json"
RESULT_JSON_PATH = OUTPUT_DIR / "openai_mcp_connector_negative_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "openai_mcp_connector_negative_results.md"

CONNECTOR_MCP_TOOL = {
    "type": "mcp",
    "server_label": "Gateway_Negative_Connector",
    "connector_id": "connector_gateway_negative_probe",
    "authorization": "Bearer invalid-token-for-negative-probe",
    "require_approval": "never",
}

PROMPT = (
    "Use the configured MCP connector to search for 'gateway negative probe'. "
    "If the connector is unavailable, report the tool failure."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: OpenAI official MCP connector")
    print("shape: connector MCP with fake connector_id and invalid authorization")
    print("intent: verify Codex backend boundary for official type=mcp connectors")

    client = build_client()
    records: list[dict[str, object]] = []
    details: list[list[object]] = []
    evidence: dict[str, object] = {}

    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            tools=[CONNECTOR_MCP_TOOL],
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        payload = error_payload(error)
        RESPONSE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        records.append(
            make_result_record(
                case=CASE_NAME,
                tool=TOOL_NAME,
                status="rejected",
                elapsed_ms=elapsed_ms(started),
                note=error_message(error),
                response_json=str(RESPONSE_JSON_PATH),
            )
        )
        details.append(["response_json", str(RESPONSE_JSON_PATH)])
        evidence["error"] = payload
    except Exception as error:  # noqa: BLE001
        payload = error_payload(error)
        RESPONSE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        records.append(
            make_result_record(
                case=CASE_NAME,
                tool=TOOL_NAME,
                status="client_error",
                elapsed_ms=elapsed_ms(started),
                note=f"{type(error).__name__}: {error}",
                response_json=str(RESPONSE_JSON_PATH),
            )
        )
        details.append(["response_json", str(RESPONSE_JSON_PATH)])
        evidence["error"] = payload
    else:
        payload = response_to_dict(response)
        RESPONSE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        status, note, evidence_details = classify_mcp_response(payload)
        details.extend(evidence_details)
        details.append(["response_json", str(RESPONSE_JSON_PATH)])
        records.append(
            make_result_record(
                case=CASE_NAME,
                tool=TOOL_NAME,
                status=status,
                elapsed_ms=elapsed_ms(started),
                note=note,
                actual_model=str(getattr(response, "model", "") or payload.get("model") or ""),
                response_status=str(payload.get("status") or ""),
                output_types=output_item_types(payload),
                response_json=str(RESPONSE_JSON_PATH),
            )
        )
        evidence["response"] = payload

    write_result_files(
        result_json_path=RESULT_JSON_PATH,
        result_md_path=RESULT_MD_PATH,
        title="OpenAI MCP Connector Negative Results",
        tool=CONNECTOR_MCP_TOOL,
        prompt=PROMPT,
        records=records,
        details=details,
        evidence=evidence,
    )
    print_result(records, RESULT_JSON_PATH, RESULT_MD_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
