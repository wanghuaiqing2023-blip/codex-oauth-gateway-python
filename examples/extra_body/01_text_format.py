from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError


EXPECTED_JSON = {
    "status": "ok",
    "answer": "extra-body-text-format-supported",
}
PROMPT = (
    "Return JSON only. Set status to ok and answer to "
    "extra-body-text-format-supported."
)
EXTRA_BODY = {
    "text": {
        "format": {
            "type": "json_schema",
            "name": "gateway_extra_body_probe",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "status": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["status", "answer"],
            },
        }
    }
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


def main() -> int:
    base_url = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
    api_key = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
    model = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    response_id = ""
    response_status = ""
    actual_model = ""
    output_text = ""
    parsed_json: Any = ""
    status = ""
    observation = ""

    try:
        response = client.responses.create(
            model=model,
            input=PROMPT,
            reasoning={"effort": "low", "summary": "auto"},
            extra_body=EXTRA_BODY,
        )
        response_id = getattr(response, "id", "") or ""
        response_status = getattr(response, "status", "") or ""
        actual_model = getattr(response, "model", "") or ""
        output_text = getattr(response, "output_text", "") or ""
        try:
            parsed_json = json.loads(output_text)
        except json.JSONDecodeError as error:
            parsed_json = ""
            status = "accepted_without_format_effect"
            observation = f"output_text was not valid JSON: {error}"
        else:
            if parsed_json == EXPECTED_JSON:
                status = "supported"
                observation = "extra_body text.format produced the expected structured JSON"
            else:
                status = "accepted_without_format_effect"
                observation = "output_text JSON did not match the expected schema result"
    except OpenAIError as error:
        status = "backend_rejected" if getattr(error, "response", None) is not None else "request_failed"
        observation = error_message(error)
    except (TypeError, ValueError) as error:
        status = "client_rejected"
        observation = error_message(error)

    print("case: extra_body_text_format")
    print(f"gateway base_url: {base_url}")
    print(f"requested_model: {model}")
    print(f"extra_body: {json.dumps(EXTRA_BODY, ensure_ascii=False, separators=(',', ':'))}")
    print(f"response.id: {response_id}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"output_text: {output_text!r}")
    print(f"parsed_json: {json.dumps(parsed_json, ensure_ascii=False, separators=(',', ':')) if parsed_json else ''}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
