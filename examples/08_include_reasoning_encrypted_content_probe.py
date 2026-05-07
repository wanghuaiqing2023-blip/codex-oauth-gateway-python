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


INCLUDE_VALUE = "reasoning.encrypted_content"


def main() -> int:
    print_config()
    print(f"include: {INCLUDE_VALUE}")
    print("intent: verify whether Codex backend returns encrypted reasoning state for stateless follow-up support")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            include=[INCLUDE_VALUE],
            reasoning={"summary": "auto"},
            input="What is 17 * 23? Reply with only the number.",
        )
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return 0

    payload = response_to_dict(response)
    matches = find_key_values(payload, "encrypted_content")
    status = "supported" if any(value_present(value) for _, value in matches) else "no_evidence"

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    print_probe_result(status, summarize_match(matches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
