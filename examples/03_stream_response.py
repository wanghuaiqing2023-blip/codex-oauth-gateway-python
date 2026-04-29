from __future__ import annotations

import os

from openai import OpenAIError

from _common import MODEL, build_client, print_config, print_openai_error, print_response


def main() -> int:
    print_config()
    prompt = os.getenv("CODEX_GATEWAY_PROMPT", "Count from 1 to 5, one number per line.")
    client = build_client()
    final_response = None
    text_parts: list[str] = []

    try:
        stream = client.responses.create(
            model=MODEL,
            input=[{"role": "user", "content": prompt}],
            stream=True,
        )
        print("\nstreamed text:")
        for event in stream:
            if event.type == "response.output_text.delta":
                text_parts.append(event.delta)
                print(event.delta, end="", flush=True)
            elif event.type in {"response.completed", "response.done"}:
                final_response = getattr(event, "response", None)
            elif event.type in {"response.failed", "response.incomplete"}:
                final_response = getattr(event, "response", None)
                print(f"\nstream ended with event: {event.type}")
    except OpenAIError as error:
        print_openai_error(error)
        return 1

    print("\n\nfinal response:")
    if final_response is not None:
        print_response(final_response)
    else:
        print("No final response event was received.")
    print(f"collected_text: {''.join(text_parts)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
