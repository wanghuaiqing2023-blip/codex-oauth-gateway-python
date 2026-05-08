from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError


SHELL_TOOL = {"type": "shell", "environment": {"type": "local"}}
TOOL_CHOICE = {"type": "shell"}


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


def contains_output_type(value: Any, expected_type: str) -> bool:
    if isinstance(value, dict):
        if value.get("type") == expected_type:
            return True
        return any(contains_output_type(child, expected_type) for child in value.values())
    if isinstance(value, list):
        return any(contains_output_type(item, expected_type) for item in value)
    return False


def main() -> int:
    base_url = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
    api_key = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
    model = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

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
            input=(
                "Use the local shell tool to request exactly one safe command: "
                "python --version. Do not answer directly."
            ),
            tools=[SHELL_TOOL],
            tool_choice=TOOL_CHOICE,
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
        payload = response_to_dict(response)
        response_id = getattr(response, "id", "") or ""
        response_status = getattr(response, "status", "") or ""
        actual_model = getattr(response, "model", "") or ""
        output_text = getattr(response, "output_text", "") or ""
        item_types = output_item_types(payload)
        found_call = contains_output_type(payload, "shell_call")
        status = "supported" if found_call else "accepted_without_observed_tool_call"
        observation = "found shell_call" if found_call else "request accepted; no shell_call observed"
    except OpenAIError as error:
        status = "backend_rejected" if getattr(error, "response", None) is not None else "request_failed"
        observation = error_message(error)
    except (TypeError, ValueError) as error:
        status = "client_rejected"
        observation = error_message(error)

    print("case: tool_choice_shell_object")
    print(f"gateway base_url: {base_url}")
    print(f"requested_model: {model}")
    print("parameter: tool_choice")
    print(f"value: {json.dumps(TOOL_CHOICE, ensure_ascii=False)}")
    print("tool: official shell with local environment")
    print("intent: verify whether tool_choice can force the official shell tool")
    print("scope: this probe does not execute shell_call output")
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
