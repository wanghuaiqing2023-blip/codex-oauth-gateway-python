from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import error_message, print_probe_result


TOP_P = 0.8


def main() -> int:
    print_config()
    print("parameter: top_p")
    print(f"value: {TOP_P}")
    print("intent: verify whether Codex backend accepts the official top_p sampling parameter")
    print("Codex CLI note: this field was not found in the public ResponsesApiRequest shape")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            top_p=TOP_P,
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
