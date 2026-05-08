from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from openai import APIStatusError, OpenAI, OpenAIError


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")


def gateway_root() -> str:
    parsed = urlsplit(BASE_URL)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def build_client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY, max_retries=0)


def print_config() -> None:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")


def print_response(response: Any) -> None:
    actual_model = getattr(response, "model", None)
    print(f"id: {getattr(response, 'id', None)}")
    print(f"object: {getattr(response, 'object', None)}")
    print(f"status: {getattr(response, 'status', None)}")
    print(f"requested_model: {MODEL}")
    print(f"actual_model: {actual_model}")
    if actual_model and actual_model != MODEL:
        print("model_note: upstream returned a different actual model than requested")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    print(f"usage: {getattr(response, 'usage', None)}")


def print_openai_error(error: OpenAIError) -> None:
    print(f"{type(error).__name__}: {error}")
    if isinstance(error, APIStatusError):
        try:
            print(json.dumps(error.response.json(), ensure_ascii=False, indent=2))
        except Exception:
            print(error.response.text)


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        payload = response.model_dump(mode="json")
        if isinstance(payload, dict):
            return payload
    if hasattr(response, "to_dict"):
        payload = response.to_dict()
        if isinstance(payload, dict):
            return payload
    payload = json.loads(json.dumps(response, default=str))
    return payload if isinstance(payload, dict) else {}


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


def value_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def summarize_match(matches: list[tuple[str, Any]]) -> str:
    if not matches:
        return "expected field not found"
    path, value = matches[0]
    if isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    return f"{path}={rendered!r}"


def summarize_object_match(matches: list[tuple[str, dict[str, Any]]]) -> str:
    if not matches:
        return "expected object not found"
    path, value = matches[0]
    rendered = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    return f"{path}={rendered}"


def error_message(error: BaseException) -> str:
    if isinstance(error, APIStatusError):
        try:
            payload = error.response.json()
        except Exception:
            return error.response.text
        message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
        return message or json.dumps(payload, ensure_ascii=False)
    return str(error)


def print_probe_result(status: str, observation: str) -> None:
    print(f"status: {status}")
    print(f"observation: {observation}")


import json
import time
from typing import Any

from openai import OpenAIError



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
