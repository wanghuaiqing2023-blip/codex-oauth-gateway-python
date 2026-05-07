from __future__ import annotations

import json
from typing import Any

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import error_message, print_probe_result, response_to_dict


TEXT_FORMAT: dict[str, Any] = {
    "format": {
        "type": "json_schema",
        "name": "gateway_probe_result",
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


def main() -> int:
    print_config()
    print("parameter: text.format")
    print("intent: verify whether Codex backend accepts official structured output text.format")
    print("Codex CLI note: public ResponsesApiRequest has text: Option<TextControls>, including format")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            text=TEXT_FORMAT,
            input=(
                "Return JSON only. Set status to ok and answer to "
                "structured-output-supported."
            ),
        )
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return 0

    payload = response_to_dict(response)
    output_text = getattr(response, "output_text", "") or ""

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"status: {getattr(response, 'status', None)}")
    print(f"actual_model: {getattr(response, 'model', None)}")
    print(f"output_text: {output_text!r}")
    print(f"text: {json.dumps(payload.get('text'), ensure_ascii=False, indent=2)}")

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as error:
        print_probe_result("accepted_without_valid_json", f"request succeeded but output_text was not valid JSON: {error}")
        return 0

    expected = {"status": "ok", "answer": "structured-output-supported"}
    status = "supported" if parsed == expected else "accepted_with_different_json"
    print_probe_result(status, json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
