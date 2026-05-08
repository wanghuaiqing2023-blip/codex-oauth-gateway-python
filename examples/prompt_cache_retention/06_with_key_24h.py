import os

from openai import OpenAI, OpenAIError


CASE = "with_key_24h"
EXPECTED_TEXT = "prompt-cache-retention-probe-ok"
BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")
PROMPT_CACHE_KEY = "gateway-prompt-cache-retention-probe"
PROMPT_CACHE_RETENTION = "24h"


def main() -> int:
    print(f"case: {CASE}")
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print(f"prompt_cache_key: {PROMPT_CACHE_KEY}")
    print(f"prompt_cache_retention: {PROMPT_CACHE_RETENTION}")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    try:
        response = client.responses.create(
            model=MODEL,
            input=f"Reply exactly: {EXPECTED_TEXT}",
            reasoning={"effort": "medium", "summary": "auto"},
            text={"verbosity": "low"},
            prompt_cache_key=PROMPT_CACHE_KEY,
            prompt_cache_retention=PROMPT_CACHE_RETENTION,
        )
    except OpenAIError as error:
        status_code = getattr(error, "status_code", None)
        error_body = getattr(error, "body", None)
        message = str(error)
        if isinstance(error_body, dict):
            upstream_error = error_body.get("error")
            if isinstance(upstream_error, dict):
                message = upstream_error.get("message") or message
        response_obj = getattr(error, "response", None)
        if response_obj is not None:
            try:
                response_payload = response_obj.json()
                upstream_error = response_payload.get("error") if isinstance(response_payload, dict) else None
                if isinstance(upstream_error, dict):
                    message = upstream_error.get("message") or message
            except Exception:
                pass
        status = "backend_rejected" if status_code is not None else "client_rejected"
        print(f"response.id: <none>")
        print(f"response.status: <none>")
        print(f"actual_model: <none>")
        print(f"output_text: <none>")
        print(f"cached_tokens: <none>")
        print(f"status: {status}")
        print(f"observation: {message}")
        return 0

    response_dict = response.model_dump() if hasattr(response, "model_dump") else {}
    usage = response_dict.get("usage") or {}
    input_details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    cached_tokens = input_details.get("cached_tokens")
    output_text = getattr(response, "output_text", "") or response_dict.get("output_text", "")
    actual_model = getattr(response, "model", None) or response_dict.get("model") or "<none>"
    response_status = getattr(response, "status", None) or response_dict.get("status") or "<none>"

    if EXPECTED_TEXT not in output_text:
        status = "accepted_unexpected_output"
        observation = "request accepted but expected output text was not observed"
    elif cached_tokens in (None, 0):
        status = "accepted_without_cache_evidence"
        observation = "request accepted; no cache evidence observed"
    else:
        status = "supported"
        observation = "request accepted and cached_tokens was reported"

    print(f"response.id: {getattr(response, 'id', '<none>')}")
    print(f"response.status: {response_status}")
    print(f"actual_model: {actual_model}")
    print(f"output_text: {output_text!r}")
    print(f"cached_tokens: {cached_tokens if cached_tokens is not None else '<none>'}")
    print(f"status: {status}")
    print(f"observation: {observation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
