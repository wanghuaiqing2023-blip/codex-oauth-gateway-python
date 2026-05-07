from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import error_message, print_probe_result, response_to_dict


MAX_OUTPUT_TOKENS = 8


def main() -> int:
    print_config()
    print("parameter: max_output_tokens")
    print(f"value: {MAX_OUTPUT_TOKENS}")
    print("intent: verify whether Codex backend accepts max_output_tokens and exposes length-limit semantics")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            input=(
                "Write a detailed five-sentence explanation of why transparent proxy semantics "
                "matter in an API gateway."
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
    print(f"output_text_chars: {len(output_text)}")
    print(f"incomplete_details: {payload.get('incomplete_details')}")
    print(f"usage: {payload.get('usage')}")
    print_probe_result("accepted", "request succeeded; inspect output length, status, incomplete_details, and usage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
