from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError


TOOL_NAME = "code_exec"
EXPECTED_INPUT = "print('tool-choice-custom-ok')"
CUSTOM_TOOL = {
    "type": "custom",
    "name": TOOL_NAME,
    "description": "Accepts a raw Python code string. This probe does not execute it.",
    "format": {"type": "text"},
}


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


def find_objects_by_type(value: Any, object_type: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        matches = [value] if value.get("type") == object_type else []
        for child in value.values():
            matches.extend(find_objects_by_type(child, object_type))
        return matches
    if isinstance(value, list):
        matches: list[dict[str, Any]] = []
        for item in value:
            matches.extend(find_objects_by_type(item, object_type))
        return matches
    return []


def main() -> int:
    base_url = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
    api_key = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
    model = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")
    tool_choice = {"type": "custom", "name": TOOL_NAME}

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

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
            tools=[CUSTOM_TOOL],
            tool_choice=tool_choice,
            input=(
                "Call the code_exec custom tool. The tool input must be exactly this text, "
                f"with no markdown and no extra characters: {EXPECTED_INPUT}"
            ),
        )
        payload = response_to_dict(response)
        custom_calls = find_objects_by_type(payload, "custom_tool_call")
        response_id = getattr(response, "id", "") or ""
        response_status = getattr(response, "status", "") or ""
        actual_model = getattr(response, "model", "") or ""
        output_text = getattr(response, "output_text", "") or ""
        item_types = output_item_types(payload)
        status = "supported" if custom_calls else "accepted_without_observed_tool_call"
        observation = "found custom_tool_call" if custom_calls else "request accepted; no custom_tool_call observed"
    except OpenAIError as error:
        status = "backend_rejected" if getattr(error, "response", None) is not None else "request_failed"
        observation = error_message(error)
    except (TypeError, ValueError) as error:
        status = "client_rejected"
        observation = error_message(error)

    print("case: tool_choice_custom_object")
    print(f"gateway base_url: {base_url}")
    print(f"requested_model: {model}")
    print("parameter: tool_choice")
    print(f"value: {json.dumps(tool_choice, ensure_ascii=False)}")
    print("tool: custom code_exec")
    print("intent: verify whether tool_choice can force a named custom tool call")
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
