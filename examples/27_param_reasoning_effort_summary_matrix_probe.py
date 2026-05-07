from __future__ import annotations

import json
from typing import Any

import requests
from openai import OpenAIError

from _common import MODEL, build_client, gateway_root, print_config
from _probe_common import error_message, output_item_types, response_to_dict


SUMMARY_VALUES = ("auto", "concise", "detailed")
FALLBACK_EFFORTS = ("low", "medium", "high", "xhigh")
PROMPT = (
    "Analyze this Python snippet and reply with only the final printed value:\n\n"
    "items = [3, 5, 8, 13]\n"
    "total = 0\n"
    "for index, value in enumerate(items):\n"
    "    if index % 2 == 0:\n"
    "        total += value * 2\n"
    "    else:\n"
    "        total -= value\n"
    "print(total)\n"
)


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    values = [[format_value(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()

    print(format_row(headers))
    print(format_row(["-" * width for width in widths]))
    for row in values:
        print(format_row(row))


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def codex_models_payload() -> dict[str, Any] | None:
    response = requests.get(f"{gateway_root()}/codex/models", timeout=30)
    if not response.ok:
        print(f"metadata_status: rejected http_status={response.status_code}")
        print(f"metadata_observation: {response.text}")
        return None
    payload = response.json()
    if not isinstance(payload, dict):
        print("metadata_status: invalid_payload")
        print("metadata_observation: /codex/models did not return a JSON object")
        return None
    return payload


def model_metadata(payload: dict[str, Any], model_slug: str) -> dict[str, Any] | None:
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    for model in models:
        if isinstance(model, dict) and model.get("slug") == model_slug:
            return model
    return None


def supported_efforts(metadata: dict[str, Any] | None) -> list[str]:
    if not metadata:
        return list(FALLBACK_EFFORTS)

    levels = metadata.get("supported_reasoning_levels")
    efforts = []
    if isinstance(levels, list):
        for level in levels:
            if isinstance(level, dict) and isinstance(level.get("effort"), str):
                efforts.append(level["effort"])
            elif isinstance(level, str):
                efforts.append(level)

    return efforts or list(FALLBACK_EFFORTS)


def extract_reasoning_summaries(payload: dict[str, Any]) -> list[str]:
    summaries: list[str] = []
    output = payload.get("output")
    if not isinstance(output, list):
        return summaries

    for item in output:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        summary = item.get("summary")
        if isinstance(summary, str):
            summaries.append(summary)
            continue
        if isinstance(summary, list):
            for part in summary:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        summaries.append(text)
                    else:
                        summaries.append(json.dumps(part, ensure_ascii=False, default=str))
                elif isinstance(part, str):
                    summaries.append(part)
                elif part is not None:
                    summaries.append(json.dumps(part, ensure_ascii=False, default=str))

    return [summary for summary in summaries if summary]


def run_probe_case(client: Any, effort: str, summary: str) -> dict[str, Any]:
    try:
        response = client.responses.create(
            model=MODEL,
            reasoning={"effort": effort, "summary": summary},
            input=PROMPT,
        )
    except OpenAIError as error:
        return {
            "effort": effort,
            "summary": summary,
            "status": "rejected",
            "actual_model": "",
            "response_status": "",
            "output_text": "",
            "output_types": [],
            "reasoning_items": 0,
            "summary_items": 0,
            "summary_chars": 0,
            "summaries": [],
            "observation": error_message(error),
        }

    payload = response_to_dict(response)
    summaries = extract_reasoning_summaries(payload)
    output_types = output_item_types(payload)
    summary_chars = sum(len(summary_text) for summary_text in summaries)
    status = "supported_with_summary" if summary_chars else "accepted_no_visible_summary"

    return {
        "effort": effort,
        "summary": summary,
        "status": status,
        "actual_model": getattr(response, "model", None),
        "response_status": getattr(response, "status", None),
        "output_text": getattr(response, "output_text", None) or "",
        "output_types": output_types,
        "reasoning_items": output_types.count("reasoning"),
        "summary_items": len(summaries),
        "summary_chars": summary_chars,
        "summaries": summaries,
        "observation": "request accepted",
    }


def main() -> int:
    print_config()
    print("parameter: reasoning.effort x reasoning.summary")
    print("intent: verify accepted effort/summary combinations and observe reasoning summary effects")
    print("Codex CLI note: public ResponsesApiRequest includes reasoning.effort and reasoning.summary")

    payload = codex_models_payload()
    metadata = model_metadata(payload, MODEL) if payload else None
    efforts = supported_efforts(metadata)
    supports_summary = metadata.get("supports_reasoning_summaries") if metadata else None
    default_summary = metadata.get("default_reasoning_summary") if metadata else None

    print("\nModel reasoning metadata:")
    print_table(
        ["requested_model", "supports_summary", "default_summary", "efforts"],
        [[MODEL, supports_summary, default_summary, efforts]],
    )

    print("\nProbe cases:")
    client = build_client()
    rows = []
    details = []
    for effort in efforts:
        for summary in SUMMARY_VALUES:
            result = run_probe_case(client, effort, summary)
            rows.append(
                [
                    result["effort"],
                    result["summary"],
                    result["status"],
                    result["actual_model"],
                    result["response_status"],
                    result["reasoning_items"],
                    result["summary_items"],
                    result["summary_chars"],
                    result["output_text"],
                ]
            )
            details.append(result)

    print_table(
        [
            "effort",
            "summary",
            "status",
            "actual_model",
            "response_status",
            "reasoning_items",
            "summary_items",
            "summary_chars",
            "output_text",
        ],
        rows,
    )

    print("\nReasoning summary details:")
    for result in details:
        label = f"[effort={result['effort']} summary={result['summary']}]"
        print(label)
        if result["summaries"]:
            for index, summary_text in enumerate(result["summaries"], start=1):
                print(f"summary[{index}]: {summary_text}")
        else:
            print(f"observation: {result['observation']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
