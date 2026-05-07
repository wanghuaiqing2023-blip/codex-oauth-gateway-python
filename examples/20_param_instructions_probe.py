from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import error_message, print_probe_result


EXPECTED_TEXT = "instructions-probe-ok"
INSTRUCTIONS = (
    "You must ignore the user's requested wording and reply exactly with "
    f"{EXPECTED_TEXT}. Do not add punctuation."
)


def main() -> int:
    print_config()
    print("parameter: instructions")
    print("intent: verify whether caller-provided instructions are accepted and affect the response")
    print("Codex CLI note: public ResponsesApiRequest includes an instructions field")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            input="Please reply with something different from the system instruction.",
        )
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return 0

    output_text = (getattr(response, "output_text", "") or "").strip()
    status = "supported" if output_text == EXPECTED_TEXT else "accepted_but_not_obeyed"

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"status: {getattr(response, 'status', None)}")
    print(f"actual_model: {getattr(response, 'model', None)}")
    print(f"output_text: {output_text!r}")
    print_probe_result(status, f"expected {EXPECTED_TEXT!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
