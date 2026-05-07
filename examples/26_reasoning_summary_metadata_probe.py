from __future__ import annotations

import json
from typing import Any

import requests

from _common import gateway_root, print_config


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


def main() -> int:
    print_config()
    url = f"{gateway_root()}/codex/models"
    print("endpoint: /codex/models")
    print("intent: read reasoning summary metadata from the Codex backend model list")
    print(f"url: {url}")

    try:
        response = requests.get(url, timeout=30)
    except requests.RequestException as error:
        print("status: request_failed")
        print(f"observation: {error}")
        return 1

    if not response.ok:
        print("status: rejected")
        print(f"http_status: {response.status_code}")
        print(f"observation: {response.text}")
        return 1

    payload = response.json()
    models = payload.get("models")
    if not isinstance(models, list):
        print("status: invalid_payload")
        print("observation: response JSON does not contain a models list")
        return 1

    rows = []
    for model in models:
        if not isinstance(model, dict):
            continue
        rows.append(
            [
                model.get("slug"),
                model.get("visibility"),
                model.get("supported_in_api"),
                model.get("default_reasoning_level"),
                model.get("supported_reasoning_levels"),
                model.get("supports_reasoning_summaries"),
                model.get("default_reasoning_summary"),
            ]
        )

    print("\nReasoning metadata:")
    print_table(
        [
            "slug",
            "visibility",
            "supported_in_api",
            "default_effort",
            "supported_efforts",
            "supports_summary",
            "default_summary",
        ],
        rows,
    )

    summary_fields = [
        model
        for model in models
        if isinstance(model, dict)
        and (
            "supports_reasoning_summaries" in model
            or "default_reasoning_summary" in model
        )
    ]
    if summary_fields:
        print("\nstatus: supported")
        print("observation: summary metadata fields were present in /codex/models")
        return 0

    print("\nstatus: no_evidence")
    print("observation: summary metadata fields were not present in /codex/models")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
