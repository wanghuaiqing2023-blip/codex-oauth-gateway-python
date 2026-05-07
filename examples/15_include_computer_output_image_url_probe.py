from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import (
    error_message,
    find_key_values,
    print_probe_result,
    response_to_dict,
    summarize_match,
    value_present,
)


INCLUDE_VALUE = "computer_call_output.output.image_url"
COMPUTER_TOOL = {
    "type": "computer_use_preview",
    "display_width": 1024,
    "display_height": 768,
    "environment": "browser",
}


def run_request(*, label: str, include_truncation: bool) -> bool:
    print(f"\nProbe: {label}")
    client = build_client()
    request = {
        "model": MODEL,
        "include": [INCLUDE_VALUE],
        "tools": [COMPUTER_TOOL],
        "input": (
            "If a computer tool is available, request a harmless screenshot action. "
            "Otherwise reply that no computer action is needed."
        ),
    }
    if include_truncation:
        request["truncation"] = "auto"

    try:
        response = client.responses.create(**request)
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return False

    payload = response_to_dict(response)
    image_url_matches = find_key_values(payload, "image_url")
    computer_call_matches = find_key_values(payload, "computer_call")
    status = "supported" if any(value_present(value) for _, value in image_url_matches) else "no_evidence"

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    print(f"computer_call_observation: {summarize_match(computer_call_matches)}")
    print_probe_result(status, summarize_match(image_url_matches))
    return True


def main() -> int:
    print_config()
    print(f"include: {INCLUDE_VALUE}")
    print("tool: computer_use_preview")
    print("intent: negative probe for whether Codex backend accepts the official Computer Use tool shape")
    print("scope: this does not execute a full computer-use loop or send a computer_call_output screenshot")
    print("phase 1: official shape includes truncation=auto, as required by OpenAI Computer Use docs")
    print("phase 2: omits truncation to isolate whether the backend recognizes the computer_use_preview tool type")

    run_request(label="official computer-use shape", include_truncation=True)
    run_request(label="tool-type isolation without truncation", include_truncation=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
