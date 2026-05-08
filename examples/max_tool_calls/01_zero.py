from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError


MAX_TOOL_CALLS = 0
WEB_SEARCH_TOOL = {"type": "web_search", "external_web_access": True}
PROMPT = (
    "Find the current title or headline on openai.com, "
    "then answer in one short sentence."
)


def error_message(error: BaseException) -> str:
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            detail = payload.get("error")
            if isinstance(detail, dict):
                return str(detail.get("message") or detail)
            return json.dumps(payload, ensure_ascii=False)
    return str(error)


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        payload = response.model_dump(mode="json")
        if isinstance(payload, dict):
            return payload
    return {}


def output_item_types(payload: Any) -> list[str]:
    output = payload.get("output") if isinstance(payload, dict) else None
    if not isinstance(output, list):
        return []
    return [str(item.get("type")) for item in output if isinstance(item, dict) and item.get("type")]


def count_output_type(value: Any, expected_type: str) -> int:
    if isinstance(value, dict):
        count = 1 if value.get("type") == expected_type else 0
        return count + sum(count_output_type(child, expected_type) for child in value.values())
    if isinstance(value, list):
        return sum(count_output_type(item, expected_type) for item in value)
    return 0


def main() -> int:
    base_url = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
    api_key = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
    model = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    response_id = ""
    response_status = ""
    actual_model = ""
    item_types: list[str] = []
    web_search_call_count = 0
    output_text = ""
    status = ""
    observation = ""

    try:
        response = client.responses.create(
            model=model,
            input=PROMPT,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="required",
            max_tool_calls=MAX_TOOL_CALLS,
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
        payload = response_to_dict(response)
        response_id = getattr(response, "id", "") or ""
        response_status = getattr(response, "status", "") or ""
        actual_model = getattr(response, "model", "") or ""
        item_types = output_item_types(payload)
        web_search_call_count = count_output_type(payload, "web_search_call")
        output_text = getattr(response, "output_text", "") or ""
        status = "accepted_without_tool_call" if web_search_call_count == 0 else "accepted_but_tool_was_used"
        observation = f"observed {web_search_call_count} web_search_call item(s)"
    except OpenAIError as error:
        status = "backend_rejected" if getattr(error, "response", None) is not None else "request_failed"
        observation = error_message(error)
    except (TypeError, ValueError) as error:
        status = "client_rejected"
        observation = error_message(error)

    print("case: max_tool_calls_zero")
    print(f"gateway base_url: {base_url}")
    print(f"requested_model: {model}")
    print(f"max_tool_calls: {MAX_TOOL_CALLS}")
    print("tool_choice: required")
    print(f"response.id: {response_id}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"output_item_types: {item_types}")
    print(f"web_search_call_count: {web_search_call_count}")
    print(f"output_text: {output_text!r}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
