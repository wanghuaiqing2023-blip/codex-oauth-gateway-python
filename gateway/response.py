from __future__ import annotations

import json


def parse_final_response(sse_text: str):
    text_deltas: list[str] = []
    output_items: list[dict] = []
    output_text_done: str | None = None
    final_response = None

    for line in sse_text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:])
        except Exception:
            continue

        if event.get("type") in {"response.output_text.delta", "output_text.delta"}:
            delta = event.get("delta")
            if isinstance(delta, str):
                text_deltas.append(delta)
            continue

        if event.get("type") == "response.output_text.done":
            done_text = event.get("text")
            if isinstance(done_text, str):
                output_text_done = done_text
            continue

        if event.get("type") == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict):
                output_items.append(item)
            continue

        if event.get("type") in {"response.done", "response.completed"}:
            final_response = event.get("response")

    if not final_response:
        return None

    if not isinstance(final_response, dict):
        return final_response

    output = final_response.get("output")
    has_output = isinstance(output, list) and len(output) > 0
    if has_output:
        return final_response

    if output_items:
        final_response["output"] = output_items
        if not final_response.get("output_text"):
            text_parts: list[str] = []
            for item in output_items:
                if item.get("type") != "message":
                    continue
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
            if text_parts:
                final_response["output_text"] = "".join(text_parts)
        return final_response

    combined_text = output_text_done if output_text_done is not None else "".join(text_deltas)
    if combined_text:
        final_response["output_text"] = combined_text
        final_response["output"] = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": combined_text}],
            }
        ]

    return final_response


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
