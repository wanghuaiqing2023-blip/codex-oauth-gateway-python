from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import error_message, print_probe_result


TEMPERATURE = 0.2


def main() -> int:
    print_config()
    print("parameter: temperature")
    print(f"value: {TEMPERATURE}")
    print("intent: verify whether Codex backend accepts the official temperature sampling parameter")
    print("Codex CLI note: this field was not found in the public ResponsesApiRequest shape")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            temperature=TEMPERATURE,
            input="Reply with exactly five words about transparent proxy design.",
        )
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return 0

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"status: {getattr(response, 'status', None)}")
    print(f"actual_model: {getattr(response, 'model', None)}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    print_probe_result("accepted", "request succeeded; sampling effect is not asserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
