from __future__ import annotations

import os
import uuid

from openai import APIStatusError, OpenAIError

from _common import MODEL, build_client, print_config, print_openai_error


def _contains_token(text: str | None, token: str) -> bool:
    return token in (text or "")


def _is_unsupported_previous_response_id(error: OpenAIError) -> bool:
    if not isinstance(error, APIStatusError):
        return False
    try:
        payload = error.response.json()
    except Exception:
        return False
    message = ((payload.get("error") or {}).get("message") or "").lower()
    return "unsupported parameter" in message and "previous_response_id" in message


def main() -> int:
    print_config()
    token = os.getenv("CODEX_GATEWAY_STATE_PROBE_TOKEN") or f"probe-{uuid.uuid4().hex[:12]}"
    client = build_client()

    try:
        first = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": (
                        f"Remember this one-time token for this conversation: {token}. "
                        "Reply exactly: OK"
                    ),
                }
            ],
            instructions="Follow exact-output instructions from the user.",
        )
    except OpenAIError as error:
        print("first request failed")
        print_openai_error(error)
        return 1

    first_id = getattr(first, "id", None)
    print()
    print("First response:")
    print(f"probe_token: {token}")
    print(f"response1.id: {first_id}")
    print(f"response1.output_text: {getattr(first, 'output_text', None)!r}")

    if not first_id:
        print("Cannot run previous_response_id probe because the first response did not include an id.")
        return 1

    try:
        second = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": (
                        "What one-time token did I ask you to remember in the previous response? "
                        "If you cannot recover it from conversation state, reply exactly: UNKNOWN"
                    ),
                }
            ],
            previous_response_id=first_id,
            instructions="Follow exact-output instructions from the user.",
        )
    except OpenAIError as error:
        print()
        print("Second request with previous_response_id failed.")
        print("This means previous_response_id is not usable as a conversation-state mechanism in this path.")
        print_openai_error(error)
        if _is_unsupported_previous_response_id(error):
            print()
            print("probe_result: BACKEND_UNSUPPORTED_PREVIOUS_RESPONSE_ID")
            print("The probe succeeded: this Codex backend path explicitly rejects previous_response_id.")
            return 0
        return 1

    second_id = getattr(second, "id", None)
    second_previous_id = getattr(second, "previous_response_id", None)
    second_text = getattr(second, "output_text", None)

    print()
    print("Second response:")
    print(f"sent_previous_response_id: {first_id}")
    print(f"response2.id: {second_id}")
    print(f"response2.previous_response_id: {second_previous_id}")
    print(f"response2.output_text: {second_text!r}")

    print()
    print("Observed behavior:")
    if second_id and second_id != first_id:
        print("id_check: PASS - the second request returned a new response id.")
    else:
        print("id_check: CHECK MANUALLY - the second response id was missing or matched the first id.")

    if _contains_token(second_text, token):
        print("state_probe: TOKEN_FOUND - previous_response_id appeared to recover prior context in this run.")
    else:
        print("state_probe: TOKEN_NOT_FOUND - previous_response_id alone did not recover prior context in this run.")

    print()
    print("Note: this is an observed-behavior probe, not proof of backend internals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
