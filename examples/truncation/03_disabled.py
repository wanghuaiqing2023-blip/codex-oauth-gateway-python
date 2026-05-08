from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError


PROMPT = "Reply exactly: truncation-probe-ok"
EXPECTED_OUTPUT = "truncation-probe-ok"
TRUNCATION = "disabled"


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


def main() -> int:
    base_url = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
    api_key = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
    model = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    response_id = ""
    response_status = ""
    actual_model = ""
    response_truncation = ""
    output_text = ""
    status = ""
    observation = ""

    try:
        response = client.responses.create(
            model=model,
            input=PROMPT,
            truncation=TRUNCATION,
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
        payload = response_to_dict(response)
        response_id = getattr(response, "id", "") or ""
        response_status = getattr(response, "status", "") or ""
        actual_model = getattr(response, "model", "") or ""
        response_truncation = str(payload.get("truncation") or "")
        output_text = getattr(response, "output_text", "") or ""
        status = "accepted" if EXPECTED_OUTPUT in output_text else "accepted_unexpected_output"
        observation = "request accepted" if EXPECTED_OUTPUT in output_text else "response text did not match expected output"
    except OpenAIError as error:
        status = "backend_rejected" if getattr(error, "response", None) is not None else "request_failed"
        observation = error_message(error)
    except (TypeError, ValueError) as error:
        status = "client_rejected"
        observation = error_message(error)

    print("case: truncation_disabled")
    print(f"gateway base_url: {base_url}")
    print(f"requested_model: {model}")
    print(f"truncation: {TRUNCATION}")
    print(f"response.id: {response_id}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"response_truncation: {response_truncation}")
    print(f"output_text: {output_text!r}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
