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


import os
import uuid

from openai import APIStatusError, OpenAIError



def _contains_token(text: str | None, token: str) -> bool:
    return token in (text or "")


def _is_unsupported_previous_response_id(error: OpenAIError) -> bool:
    if not isinstance(error, APIStatusError):
        return False
    try:
        payload = error.response.json()
    except Exception:
        return False
    message = ((payload.get("error") or {}).get("message") or "").lower()
    return "unsupported parameter" in message and "previous_response_id" in message


def main() -> int:
    print_config()
    token = os.getenv("CODEX_GATEWAY_STATE_PROBE_TOKEN") or f"probe-{uuid.uuid4().hex[:12]}"
    client = build_client()

    try:
        first = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": (
                        f"Remember this one-time token for this conversation: {token}. "
                        "Reply exactly: OK"
                    ),
                }
            ],
            instructions="Follow exact-output instructions from the user.",
        )
    except OpenAIError as error:
        print("first request failed")
        print_openai_error(error)
        return 1

    first_id = getattr(first, "id", None)
    print()
    print("First response:")
    print(f"probe_token: {token}")
    print(f"response1.id: {first_id}")
    print(f"response1.output_text: {getattr(first, 'output_text', None)!r}")

    if not first_id:
        print("Cannot run previous_response_id probe because the first response did not include an id.")
        return 1

    try:
        second = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": (
                        "What one-time token did I ask you to remember in the previous response? "
                        "If you cannot recover it from conversation state, reply exactly: UNKNOWN"
                    ),
                }
            ],
            previous_response_id=first_id,
            instructions="Follow exact-output instructions from the user.",
        )
    except OpenAIError as error:
        print()
        print("Second request with previous_response_id failed.")
        print("This means previous_response_id is not usable as a conversation-state mechanism in this path.")
        print_openai_error(error)
        if _is_unsupported_previous_response_id(error):
            print()
            print("probe_result: BACKEND_UNSUPPORTED_PREVIOUS_RESPONSE_ID")
            print("The probe succeeded: this Codex backend path explicitly rejects previous_response_id.")
            return 0
        return 1

    second_id = getattr(second, "id", None)
    second_previous_id = getattr(second, "previous_response_id", None)
    second_text = getattr(second, "output_text", None)

    print()
    print("Second response:")
    print(f"sent_previous_response_id: {first_id}")
    print(f"response2.id: {second_id}")
    print(f"response2.previous_response_id: {second_previous_id}")
    print(f"response2.output_text: {second_text!r}")

    print()
    print("Observed behavior:")
    if second_id and second_id != first_id:
        print("id_check: PASS - the second request returned a new response id.")
    else:
        print("id_check: CHECK MANUALLY - the second response id was missing or matched the first id.")

    if _contains_token(second_text, token):
        print("state_probe: TOKEN_FOUND - previous_response_id appeared to recover prior context in this run.")
    else:
        print("state_probe: TOKEN_NOT_FOUND - previous_response_id alone did not recover prior context in this run.")

    print()
    print("Note: this is an observed-behavior probe, not proof of backend internals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
