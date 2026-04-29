from __future__ import annotations

import os

from openai import OpenAIError

from _common import MODEL, build_client, print_config, print_openai_error, print_response


def main() -> int:
    print_config()
    prompt = os.getenv("CODEX_GATEWAY_PROMPT", "Reply exactly: gateway-example-ok")
    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            input=[{"role": "user", "content": prompt}],
        )
    except OpenAIError as error:
        print_openai_error(error)
        return 1

    print_response(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
