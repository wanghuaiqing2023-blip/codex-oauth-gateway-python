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
from typing import Any

from openai import OpenAIError



DEFAULT_DOG_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/8/8b/Dog_04343.jpg"
DOG_KEYWORDS = ("dog", "canine", "puppy")
IMAGE_QUESTION = (
    "Answer only based on the image content. "
    "What is the main animal? What is its approximate color? "
    "What posture or scene is it in? "
    "If you cannot see the image, say that clearly."
)


def format_matches(matches: list[tuple[str, Any]], expected_url: str) -> str:
    if not matches:
        return "no image_url fields found in response"

    exact_matches = [path for path, value in matches if value == expected_url]
    if exact_matches:
        return "matched at " + ", ".join(exact_matches)

    return "image_url fields found, but none matched input: " + summarize_match(matches)


def main() -> int:
    print_config()
    image_url = os.getenv("CODEX_GATEWAY_IMAGE_URL", DEFAULT_DOG_IMAGE_URL)
    print(f"image_url_source: {'CODEX_GATEWAY_IMAGE_URL' if image_url != DEFAULT_DOG_IMAGE_URL else 'built-in Wikimedia dog image'}")
    print(f"image_url: {image_url}")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            include=["message.input_image.image_url"],
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": IMAGE_QUESTION,
                        },
                        {"type": "input_image", "image_url": image_url, "detail": "low"},
                    ],
                }
            ],
        )
    except OpenAIError as error:
        print_openai_error(error)
        return 1

    output_text = getattr(response, "output_text", "") or ""
    payload = response_to_dict(response)
    image_url_matches = find_key_values(payload, "image_url")
    include_echoed = any(value == image_url for _, value in image_url_matches)
    mentions_dog = any(keyword in output_text.lower() for keyword in DOG_KEYWORDS)

    print("\nImage input probe result:")
    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"actual_model: {getattr(response, 'model', None)}")
    print(f"output_text: {output_text!r}")
    print(f"mentions_dog_like_term: {'yes' if mentions_dog else 'no'}")
    print(f"include_image_url_echoed: {'yes' if include_echoed else 'no'}")
    print(f"image_url_observation: {format_matches(image_url_matches, image_url)}")

    print("\nInterpretation:")
    print("- If output_text describes the animal and visual details, image input likely reached the backend model.")
    print("- If include_image_url_echoed is no, this path did not implement the official include echo for message.input_image.image_url.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
