from __future__ import annotations

import os
import uuid

from openai import APIStatusError, OpenAIError

from _common import MODEL, build_client, print_config, print_openai_error


def _contains_token(text: str | None, token: str) -> bool:
    return token in (text or "")


def _error_message(error: OpenAIError) -> str:
    if not isinstance(error, APIStatusError):
        return str(error)
    try:
        payload = error.response.json()
    except Exception:
        return error.response.text
    return ((payload.get("error") or {}).get("message") or str(payload))


def _is_conversation_rejection(error: OpenAIError) -> bool:
    message = _error_message(error).lower()
    return "conversation" in message or "unsupported parameter" in message


def _is_missing_conversations_api(error: OpenAIError) -> bool:
    if not isinstance(error, APIStatusError):
        return False
    message = _error_message(error).lower()
    return error.status_code == 404 or "not found" in message


def main() -> int:
    print_config()
    token = os.getenv("CODEX_GATEWAY_STATE_PROBE_TOKEN") or f"probe-{uuid.uuid4().hex[:12]}"
    client = build_client()

    print(f"probe_token: {token}")

    try:
        conversation = client.conversations.create(
            metadata={"probe": "conversation-state"},
        )
    except OpenAIError as error:
        print()
        print("Conversation creation failed.")
        print("Official usage starts with client.conversations.create(), but this gateway path may not expose /v1/conversations.")
        print_openai_error(error)
        if _is_missing_conversations_api(error):
            print()
            print("probe_result: GATEWAY_DOES_NOT_SUPPORT_CONVERSATIONS_API")
            print("The probe succeeded: this gateway currently does not implement the official Conversations API.")
            return 0
        return 1

    conversation_id = getattr(conversation, "id", None)
    print()
    print("Conversation:")
    print(f"conversation.id: {conversation_id}")
    print(f"conversation.object: {getattr(conversation, 'object', None)}")

    if not conversation_id:
        print()
        print("probe_result: CONVERSATION_CREATE_RETURNED_NO_ID")
        print("The probe stopped because the conversation object did not include an id.")
        return 1

    try:
        first = client.responses.create(
            model=MODEL,
            conversation=conversation_id,
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
        print()
        print("First response request with conversation failed.")
        print("This means conversation is not usable as a server-side conversation-state mechanism in this path.")
        print_openai_error(error)
        if _is_conversation_rejection(error):
            print()
            print("probe_result: BACKEND_REJECTED_CONVERSATION")
            print("The probe succeeded: this Codex backend path rejected the conversation parameter.")
            return 0
        return 1

    print()
    print("First response:")
    print(f"response1.id: {getattr(first, 'id', None)}")
    print(f"response1.conversation: {getattr(first, 'conversation', None)}")
    print(f"response1.output_text: {getattr(first, 'output_text', None)!r}")

    try:
        second = client.responses.create(
            model=MODEL,
            conversation=conversation_id,
            input=[
                {
                    "role": "user",
                    "content": (
                        "What one-time token did I ask you to remember in this conversation? "
                        "If you cannot recover it from conversation state, reply exactly: UNKNOWN"
                    ),
                }
            ],
            instructions="Follow exact-output instructions from the user.",
        )
    except OpenAIError as error:
        print()
        print("Second request with the same conversation failed.")
        print_openai_error(error)
        if _is_conversation_rejection(error):
            print()
            print("probe_result: BACKEND_REJECTED_CONVERSATION")
            print("The probe succeeded: this Codex backend path rejected or could not use conversation state.")
            return 0
        return 1

    second_text = getattr(second, "output_text", None)

    print()
    print("Second response:")
    print(f"sent_conversation_id: {conversation_id}")
    print(f"response2.id: {getattr(second, 'id', None)}")
    print(f"response2.output_text: {second_text!r}")

    print()
    print("Observed behavior:")
    if _contains_token(second_text, token):
        print("state_probe: TOKEN_FOUND - conversation appeared to recover prior context in this run.")
    else:
        print("state_probe: TOKEN_NOT_FOUND - conversation alone did not recover prior context in this run.")

    print()
    print("Note: this is an observed-behavior probe, not proof of backend internals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
