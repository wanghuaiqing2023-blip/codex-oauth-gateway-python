import json


def parse_final_response(sse_text: str):
    for line in sse_text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:])
        except Exception:
            continue
        if event.get("type") in {"response.done", "response.completed"}:
            return event.get("response")
    return None


def map_usage_limit_404(status_code: int, body_text: str) -> tuple[int, str]:
    if status_code != 404:
        return status_code, body_text
    try:
        parsed = json.loads(body_text)
        code = (parsed.get("error") or {}).get("code") or (parsed.get("error") or {}).get("type")
        if code == "usage_limit_exceeded":
            return 429, body_text
    except Exception:
        pass
    return status_code, body_text
