from __future__ import annotations

import os
from typing import Any

from openai import OpenAI, OpenAIError


CASE = "scale"
SERVICE_TIER = "scale"
PROMPT = "Reply exactly: service-tier-probe-ok"
EXPECTED_OUTPUT = "service-tier-probe-ok"


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


def get_response_service_tier(response: Any) -> str:
    service_tier = getattr(response, "service_tier", None)
    if service_tier:
        return str(service_tier)
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
        if isinstance(payload, dict) and payload.get("service_tier") is not None:
            return str(payload["service_tier"])
    return ""


def main() -> int:
    base_url = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
    api_key = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
    model = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

    client = OpenAI(api_key=api_key, base_url=base_url)

    response_id = ""
    response_status = ""
    actual_model = ""
    response_service_tier = ""
    output_text = ""
    status = ""
    observation = ""

    try:
        response = client.responses.create(
            model=model,
            input=PROMPT,
            service_tier=SERVICE_TIER,
            reasoning={"effort": "medium", "summary": "auto"},
            text={"verbosity": "low"},
        )
        response_id = getattr(response, "id", "") or ""
        response_status = getattr(response, "status", "") or ""
        actual_model = getattr(response, "model", "") or ""
        response_service_tier = get_response_service_tier(response)
        output_text = getattr(response, "output_text", "") or ""
        status = "accepted" if EXPECTED_OUTPUT in output_text else "accepted_unexpected_output"
        observation = "request accepted" if EXPECTED_OUTPUT in output_text else "response text did not match expected output"
    except OpenAIError as error:
        status = "backend_rejected" if getattr(error, "response", None) is not None else "request_failed"
        observation = error_message(error)
    except (TypeError, ValueError) as error:
        status = "client_rejected"
        observation = error_message(error)

    print(f"case: {CASE}")
    print(f"gateway base_url: {base_url}")
    print(f"requested_model: {model}")
    print(f"service_tier: {SERVICE_TIER}")
    print(f"response.id: {response_id}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"response_service_tier: {response_service_tier}")
    print(f"output_text: {output_text!r}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
