from __future__ import annotations

import os
from typing import Any

from openai import OpenAI, OpenAIError


WEB_SEARCH_TOOL = {"type": "web_search", "external_web_access": True}


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
            return str(payload)
    return str(error)


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
        if isinstance(payload, dict):
            return payload
    return {}


def output_item_types(payload: Any) -> list[str]:
    output = payload.get("output") if isinstance(payload, dict) else None
    if not isinstance(output, list):
        return []
    return [str(item.get("type")) for item in output if isinstance(item, dict) and item.get("type")]


def contains_output_type(payload: Any, expected_type: str) -> bool:
    if isinstance(payload, dict):
        if payload.get("type") == expected_type:
            return True
        return any(contains_output_type(value, expected_type) for value in payload.values())
    if isinstance(payload, list):
        return any(contains_output_type(item, expected_type) for item in payload)
    return False


def main() -> int:
    base_url = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
    api_key = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
    model = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

    client = OpenAI(api_key=api_key, base_url=base_url)

    response_id = ""
    response_status = ""
    actual_model = ""
    output_text = ""
    item_types: list[str] = []
    status = ""
    observation = ""

    try:
        response = client.responses.create(
            model=model,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="none",
            input=(
                "Do not use prior knowledge. Find the current title or headline on openai.com, "
                "then answer in one short sentence."
            ),
        )
        payload = response_to_dict(response)
        response_id = getattr(response, "id", "") or ""
        response_status = getattr(response, "status", "") or ""
        actual_model = getattr(response, "model", "") or ""
        output_text = getattr(response, "output_text", "") or ""
        item_types = output_item_types(payload)
        used_web_search = contains_output_type(payload, "web_search_call")
        status = "accepted_but_tool_was_used" if used_web_search else "accepted_without_tool_call"
        observation = "found web_search_call" if used_web_search else "request accepted; no web_search_call observed"
    except OpenAIError as error:
        status = "backend_rejected" if getattr(error, "response", None) is not None else "request_failed"
        observation = error_message(error)
    except (TypeError, ValueError) as error:
        status = "client_rejected"
        observation = error_message(error)

    print("case: tool_choice_none")
    print(f"gateway base_url: {base_url}")
    print(f"requested_model: {model}")
    print("parameter: tool_choice")
    print("value: none")
    print("tool: web_search with external_web_access=true")
    print("intent: verify whether tool_choice=none suppresses tool calls")
    print(f"response.id: {response_id}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"output_text: {output_text!r}")
    print(f"output_item_types: {item_types}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
