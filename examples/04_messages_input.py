from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config, print_openai_error, print_response


def main() -> int:
    print_config()
    client = build_client()
    messages = [
        {
            "role": "user",
            "content": "Use exactly one short sentence to describe what this gateway does.",
        },
        {
            "role": "user",
            "content": "Mention OAuth and the OpenAI Responses SDK.",
        },
    ]

    try:
        response = client.responses.create(
            model=MODEL,
            input=messages,
            instructions="Answer in Chinese.",
        )
    except OpenAIError as error:
        print_openai_error(error)
        return 1

    print_response(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
