import json
import os

from openai import OpenAI, OpenAIError


CASE = "stream_include_obfuscation_true"
EXPECTED_TEXT = "stream-options-probe-ok"
BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")
STREAM = True
STREAM_OPTIONS = {"include_obfuscation": True}


def event_to_dict(event):
    if hasattr(event, "model_dump"):
        return event.model_dump()
    if isinstance(event, dict):
        return event
    return {"type": getattr(event, "type", type(event).__name__)}


def has_obfuscation(value):
    if isinstance(value, dict):
        if "obfuscation" in value:
            return True
        return any(has_obfuscation(item) for item in value.values())
    if isinstance(value, list):
        return any(has_obfuscation(item) for item in value)
    return False


def error_message(error):
    message = str(error)
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
            upstream_error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(upstream_error, dict):
                message = upstream_error.get("message") or message
            elif isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                message = payload["detail"]
        except Exception:
            pass
    return message


def main() -> int:
    print(f"case: {CASE}")
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print(f"stream: {STREAM}")
    print(f"stream_options: {json.dumps(STREAM_OPTIONS, separators=(',', ':'))}")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    event_count = 0
    event_types = []
    obfuscation_event_count = 0
    text_parts = []
    final_response = None

    try:
        stream = client.responses.create(
            model=MODEL,
            input=f"Reply exactly: {EXPECTED_TEXT}",
            reasoning={"effort": "medium", "summary": "auto"},
            text={"verbosity": "low"},
            stream=True,
            stream_options=STREAM_OPTIONS,
        )
        for event in stream:
            event_count += 1
            payload = event_to_dict(event)
            event_type = getattr(event, "type", None) or payload.get("type") or type(event).__name__
            if event_type not in event_types:
                event_types.append(event_type)
            if has_obfuscation(payload):
                obfuscation_event_count += 1
            if event_type == "response.output_text.delta":
                text_parts.append(getattr(event, "delta", None) or payload.get("delta") or "")
            if event_type in {"response.completed", "response.done", "response.failed", "response.incomplete"}:
                final_response = getattr(event, "response", None) or payload.get("response")
    except OpenAIError as error:
        status_code = getattr(error, "status_code", None)
        status = "backend_rejected" if status_code is not None else "client_rejected"
        print("event_count: 0")
        print("event_types: []")
        print("obfuscation_event_count: 0")
        print("response.id: <none>")
        print("response.status: <none>")
        print("actual_model: <none>")
        print("collected_text: <none>")
        print(f"status: {status}")
        print(f"observation: {error_message(error)}")
        return 0

    final_payload = final_response.model_dump() if hasattr(final_response, "model_dump") else final_response or {}
    collected_text = "".join(text_parts)
    response_id = getattr(final_response, "id", None) or final_payload.get("id") or "<none>"
    response_status = getattr(final_response, "status", None) or final_payload.get("status") or "<none>"
    actual_model = getattr(final_response, "model", None) or final_payload.get("model") or "<none>"

    has_stream_evidence = any(
        event_type in event_types
        for event_type in ["response.output_text.delta", "response.completed", "response.done"]
    )
    if not has_stream_evidence or EXPECTED_TEXT not in collected_text:
        status = "accepted_no_stream_evidence"
        observation = "request accepted but expected stream text was not observed"
    elif obfuscation_event_count:
        status = "supported_with_obfuscation"
        observation = "request streamed successfully and obfuscation fields were observed"
    else:
        status = "supported_without_obfuscation"
        observation = "request streamed successfully and no obfuscation fields were observed"

    print(f"event_count: {event_count}")
    print(f"event_types: {json.dumps(event_types, ensure_ascii=False)}")
    print(f"obfuscation_event_count: {obfuscation_event_count}")
    print(f"response.id: {response_id}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"collected_text: {collected_text!r}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
