import os

from openai import OpenAI, OpenAIError


CASE = "background_omitted"
EXPECTED_TEXT = "background-probe-ok"
BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")


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
    print("background: <absent>")
    print("stream: <absent>")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    try:
        response = client.responses.create(
            model=MODEL,
            input=f"Reply exactly: {EXPECTED_TEXT}",
            reasoning={"effort": "medium", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        status_code = getattr(error, "status_code", None)
        status = "backend_rejected" if status_code is not None else "client_rejected"
        print("response.id: <none>")
        print("response.status: <none>")
        print("actual_model: <none>")
        print("output_text: <none>")
        print(f"status: {status}")
        print(f"observation: {error_message(error)}")
        return 0
    except Exception as error:
        print("response.id: <none>")
        print("response.status: <none>")
        print("actual_model: <none>")
        print("output_text: <none>")
        print("status: client_rejected")
        print(f"observation: {type(error).__name__}: {error}")
        return 0

    response_dict = response.model_dump() if hasattr(response, "model_dump") else {}
    output_text = getattr(response, "output_text", None) or response_dict.get("output_text") or ""
    response_status = getattr(response, "status", None) or response_dict.get("status") or "<none>"
    actual_model = getattr(response, "model", None) or response_dict.get("model") or "<none>"

    if EXPECTED_TEXT in output_text:
        status = "supported"
        observation = "baseline request succeeded"
    else:
        status = "accepted_unexpected_output"
        observation = "request accepted but expected output text was not observed"

    print(f"response.id: {getattr(response, 'id', '<none>')}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"output_text: {output_text!r}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
