from __future__ import annotations

import json
import time

from openai import OpenAIError

from openai_mcp_common import (
    BASE_URL,
    MODEL,
    OUTPUT_DIR,
    build_client,
    classify_mcp_response,
    elapsed_ms,
    error_message,
    error_payload,
    make_result_record,
    output_item_types,
    print_result,
    response_to_dict,
    write_result_files,
)


CASE_NAME = "remote_mcp_unreachable"
TOOL_NAME = "OpenAI MCP remote"
RESPONSE_JSON_PATH = OUTPUT_DIR / "openai_mcp_remote_negative_response.json"
RESULT_JSON_PATH = OUTPUT_DIR / "openai_mcp_remote_negative_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "openai_mcp_remote_negative_results.md"

REMOTE_MCP_TOOL = {
    "type": "mcp",
    "server_label": "gateway_mcp_negative",
    "server_url": "https://example.invalid/mcp",
    "require_approval": "never",
    "allowed_tools": ["gateway_probe"],
}

PROMPT = (
    "Use the gateway_probe MCP tool from the configured remote MCP server. "
    "If the tool is unavailable, report the tool failure."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: OpenAI official MCP")
    print("shape: remote MCP with unreachable server_url")
    print("intent: verify Codex backend boundary for official type=mcp remote servers")

    client = build_client()
    records: list[dict[str, object]] = []
    details: list[list[object]] = []
    evidence: dict[str, object] = {}

    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            tools=[REMOTE_MCP_TOOL],
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
        title="OpenAI MCP Remote Negative Results",
        tool=REMOTE_MCP_TOOL,
        prompt=PROMPT,
        records=records,
        details=details,
        evidence=evidence,
    )
    print_result(records, RESULT_JSON_PATH, RESULT_MD_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
