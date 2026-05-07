from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import error_message, response_to_dict


PROMPT = "Reply exactly: metadata-probe-ok"

METADATA = {
    "probe": "metadata",
    "scenario": "basic",
    "trace_id": "metadata-probe-001",
}


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    values = [[format_value(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        if len(row) != len(headers):
            raise ValueError(f"table row has {len(row)} columns, but headers have {len(headers)} columns")
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()

    print(format_row(headers))
    print(format_row(["-" * width for width in widths]))
    for row in values:
        print(format_row(row))


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return str(value)


def classify_metadata_echo(expected: dict[str, Any], observed: Any) -> str:
    if expected == {}:
        if observed in (None, {}):
            return "accepted_empty"
        return "accepted_empty_with_unexpected_echo"

    if observed == expected:
        return "supported_with_echo"

    if observed in (None, {}):
        return "accepted_no_echo"

    if isinstance(observed, dict):
        matched = {
            key: value
            for key, value in expected.items()
            if observed.get(key) == value
        }
        if matched:
            return "accepted_partial_echo"

    return "accepted_different_echo"


def run_probe_case(client: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            metadata=METADATA,
        )
    except OpenAIError as error:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "case": "basic",
            "intent": "verify whether official metadata is accepted and echoed",
            "sent_metadata": METADATA,
            "status": "backend_rejected",
            "actual_model": "",
            "response_status": "",
            "response_metadata": "",
            "elapsed_ms": elapsed_ms,
            "output_text": "",
            "observation": error_message(error),
        }
    except Exception as error:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "case": "basic",
            "intent": "verify whether official metadata is accepted and echoed",
            "sent_metadata": METADATA,
            "status": "client_rejected",
            "actual_model": "",
            "response_status": "",
            "response_metadata": "",
            "elapsed_ms": elapsed_ms,
            "output_text": "",
            "observation": f"{type(error).__name__}: {error}",
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    observed_metadata = payload.get("metadata")
    return {
        "case": "basic",
        "intent": "verify whether official metadata is accepted and echoed",
        "sent_metadata": METADATA,
        "status": classify_metadata_echo(METADATA, observed_metadata),
        "actual_model": getattr(response, "model", None),
        "response_status": getattr(response, "status", None),
        "response_metadata": observed_metadata,
        "elapsed_ms": elapsed_ms,
        "output_text": getattr(response, "output_text", None) or "",
        "observation": "request accepted",
    }


def main() -> int:
    print_config()
    print("parameter: metadata")
    print("intent: verify whether official Responses API metadata is accepted, rejected, or echoed")
    print("Codex CLI note: public ResponsesApiRequest does not include official metadata")
    print("Codex CLI note: Codex uses private client_metadata instead, which is a different field")
    print(f"fixed_input: {PROMPT!r}")
    print(f"sent_metadata: {json.dumps(METADATA, ensure_ascii=False)}")

    client = build_client()
    result = run_probe_case(client)

    observed_actual_models = [result["actual_model"]] if result["actual_model"] else []

    print("\nProbe scope:")
    print_table(
        [
            "requested_model",
            "observed_actual_models",
            "tested_cases",
        ],
        [
            [
                MODEL,
                observed_actual_models,
                ["basic"],
            ]
        ],
    )

    print("\nProbe cases:")
    print_table(
        [
            "case",
            "status",
            "actual_model",
            "response_status",
            "response_metadata",
            "elapsed_ms",
            "output_text",
        ],
        [
            [
                result["case"],
                result["status"],
                result["actual_model"],
                result["response_status"],
                result["response_metadata"],
                result["elapsed_ms"],
                result["output_text"],
            ]
        ],
    )

    print("\nIntent and observations:")
    print_table(
        [
            "case",
            "intent",
            "sent_metadata",
            "observation",
        ],
        [
            [
                result["case"],
                result["intent"],
                result["sent_metadata"],
                result["observation"],
            ]
        ],
    )

    print("\nStatus meanings:")
    print("supported_with_echo = request succeeded and response.metadata matched the sent metadata")
    print("accepted_no_echo = request succeeded but response.metadata was absent or empty")
    print("accepted_partial_echo = request succeeded and only part of metadata was echoed")
    print("accepted_different_echo = request succeeded but response.metadata differed")
    print("accepted_empty = empty metadata request succeeded")
    print("backend_rejected = request reached the gateway/backend path and was rejected")
    print("client_rejected = the OpenAI Python SDK or local client validation rejected the request")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
