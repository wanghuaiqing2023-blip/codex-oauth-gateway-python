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
import re
from typing import Any

import requests
from openai import OpenAIError



VERBOSITY_VALUES = ("low", "medium", "high")
REASONING = {"effort": "medium", "summary": "auto"}
PROMPT = (
    "Explain this Python snippet for a new developer, including how total changes "
    "during the loop:\n\n"
    "items = [3, 5, 8, 13]\n"
    "total = 0\n"
    "for index, value in enumerate(items):\n"
    "    if index % 2 == 0:\n"
    "        total += value * 2\n"
    "    else:\n"
    "        total -= value\n"
    "print(total)\n"
)


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    values = [[format_value(value) for value in row] for row in rows]
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


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def codex_models_payload() -> dict[str, Any] | None:
    response = requests.get(f"{gateway_root()}/codex/models", timeout=30)
    if not response.ok:
        print(f"metadata_status: rejected http_status={response.status_code}")
        print(f"metadata_observation: {response.text}")
        return None
    payload = response.json()
    if not isinstance(payload, dict):
        print("metadata_status: invalid_payload")
        print("metadata_observation: /codex/models did not return a JSON object")
        return None
    return payload


def model_metadata(payload: dict[str, Any], model_slug: str) -> dict[str, Any] | None:
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    for model in models:
        if isinstance(model, dict) and model.get("slug") == model_slug:
            return model
    return None


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def line_count(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def run_probe_case(client: Any, verbosity: str) -> dict[str, Any]:
    try:
        response = client.responses.create(
            model=MODEL,
            reasoning=REASONING,
            text={"verbosity": verbosity},
            input=PROMPT,
        )
    except OpenAIError as error:
        return {
            "verbosity": verbosity,
            "reasoning": REASONING,
            "status": "rejected",
            "actual_model": "",
            "response_status": "",
            "chars": 0,
            "words": 0,
            "lines": 0,
            "output_text": "",
            "observation": error_message(error),
        }

    output_text = getattr(response, "output_text", None) or ""
    return {
        "verbosity": verbosity,
        "reasoning": REASONING,
        "status": "supported",
        "actual_model": getattr(response, "model", None),
        "response_status": getattr(response, "status", None),
        "chars": len(output_text),
        "words": word_count(output_text),
        "lines": line_count(output_text),
        "output_text": output_text,
        "observation": "request accepted",
    }


def main() -> int:
    print_config()
    print("parameter: text.verbosity")
    print("intent: verify accepted verbosity values and observe output detail differences")
    print("Codex CLI note: public TextControls includes verbosity values low, medium, and high")
    print(f"fixed_reasoning: {json.dumps(REASONING, ensure_ascii=False)}")

    payload = codex_models_payload()
    metadata = model_metadata(payload, MODEL) if payload else None
    support_verbosity = metadata.get("support_verbosity") if metadata else None
    default_verbosity = metadata.get("default_verbosity") if metadata else None

    client = build_client()
    results = [run_probe_case(client, verbosity) for verbosity in VERBOSITY_VALUES]
    observed_actual_models = sorted(
        {
            result["actual_model"]
            for result in results
            if result["actual_model"]
        }
    )

    print("\nModel text metadata:")
    print_table(
        [
            "requested_model",
            "observed_actual_models",
            "support_verbosity",
            "default_verbosity",
            "tested_values",
        ],
        [[MODEL, observed_actual_models, support_verbosity, default_verbosity, VERBOSITY_VALUES]],
    )

    print("\nProbe cases:")
    print_table(
        [
            "verbosity",
            "reasoning",
            "status",
            "actual_model",
            "response_status",
            "chars",
            "words",
            "lines",
        ],
        [
            [
                result["verbosity"],
                result["reasoning"],
                result["status"],
                result["actual_model"],
                result["response_status"],
                result["chars"],
                result["words"],
                result["lines"],
            ]
            for result in results
        ],
    )

    print("\nOutput details:")
    for result in results:
        print(f"[verbosity={result['verbosity']}]")
        print(f"reasoning: {json.dumps(result['reasoning'], ensure_ascii=False)}")
        print(f"actual_model: {result['actual_model']}")
        if result["output_text"]:
            print(result["output_text"])
        else:
            print(f"observation: {result['observation']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
