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


import requests
from openai import OpenAIError



def print_table(headers: list[str], rows: list[list[object]]) -> None:
    values = [[str(value) if value is not None else "" for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()

    print(format_row(headers))
    print(format_row(["-" * width for width in widths]))
    for row in values:
        print(format_row(row))


def print_sdk_models() -> bool:
    client = build_client()
    try:
        models = client.models.list()
    except OpenAIError as error:
        print_openai_error(error)
        return False

    print("\nOpenAI-compatible /v1/models:")
    rows = []
    for model in models.data:
        rows.append([model.id, getattr(model, "owned_by", None)])
    print_table(["id", "owned_by"], rows)
    return True


def print_codex_models() -> bool:
    url = f"{gateway_root()}/codex/models"
    response = requests.get(url, timeout=30)
    print(f"\nCodex backend metadata from {url}:")
    if not response.ok:
        print(f"status: {response.status_code}")
        print(response.text)
        return False

    payload = response.json()
    models = payload.get("models") or []
    rows = []
    for model in models:
        upgrade = model.get("upgrade") or {}
        rows.append(
            [
                model.get("slug"),
                model.get("visibility"),
                model.get("supported_in_api"),
                model.get("context_window"),
                upgrade.get("model", ""),
            ]
        )
    print_table(["slug", "visibility", "supported_in_api", "context_window", "upgrade_to"], rows)
    return True


def main() -> int:
    print_config()
    sdk_ok = print_sdk_models()
    codex_ok = print_codex_models()
    return 0 if sdk_ok and codex_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
