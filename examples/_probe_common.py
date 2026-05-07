from __future__ import annotations

import json
from typing import Any

from openai import APIStatusError, OpenAIError


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return json.loads(json.dumps(response, default=str))


def find_key_values(value: Any, key: str, path: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        matches = []
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
        matches = []
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
    return [item.get("type", "<missing>") for item in output if isinstance(item, dict)]


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


def error_message(error: OpenAIError) -> str:
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
