from __future__ import annotations

import requests
from openai import OpenAIError

from _common import build_client, gateway_root, print_config, print_openai_error


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    values = [[str(value) if value is not None else "" for value in row] for row in rows]
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


def print_sdk_models() -> bool:
    client = build_client()
    try:
        models = client.models.list()
    except OpenAIError as error:
        print_openai_error(error)
        return False

    print("\nOpenAI-compatible /v1/models:")
    rows = []
    for model in models.data:
        rows.append([model.id, getattr(model, "owned_by", None)])
    print_table(["id", "owned_by"], rows)
    return True


def print_codex_models() -> bool:
    url = f"{gateway_root()}/codex/models"
    response = requests.get(url, timeout=30)
    print(f"\nCodex backend metadata from {url}:")
    if not response.ok:
        print(f"status: {response.status_code}")
        print(response.text)
        return False

    payload = response.json()
    models = payload.get("models") or []
    rows = []
    for model in models:
        upgrade = model.get("upgrade") or {}
        rows.append(
            [
                model.get("slug"),
                model.get("visibility"),
                model.get("supported_in_api"),
                model.get("context_window"),
                upgrade.get("model", ""),
            ]
        )
    print_table(["slug", "visibility", "supported_in_api", "context_window", "upgrade_to"], rows)
    return True


def main() -> int:
    print_config()
    sdk_ok = print_sdk_models()
    codex_ok = print_codex_models()
    return 0 if sdk_ok and codex_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
