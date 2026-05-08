from __future__ import annotations

import argparse
import json
import os
import urllib.request
from typing import Any
from urllib.parse import urlsplit, urlunsplit


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")


def gateway_root(base_url: str) -> str:
    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def fetch_codex_models(base_url: str) -> dict[str, Any]:
    url = f"{gateway_root(base_url)}/codex/models"
    with urllib.request.urlopen(url) as response:  # noqa: S310 - local configured gateway URL.
        return json.loads(response.read().decode("utf-8"))


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict, tuple)):
        return compact_json(value)
    return str(value)


def print_table(headers: list[str], rows: list[list[Any]]) -> None:
    values = [[format_value(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        if len(row) != len(headers):
            raise ValueError(f"row has {len(row)} columns, expected {len(headers)}")
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()

    print(format_row(headers))
    print(format_row(["-" * width for width in widths]))
    for row in values:
        print(format_row(row))


def models_from_payload(payload: dict[str, Any], *, api_visible_only: bool) -> list[dict[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list):
        return []

    result = [model for model in models if isinstance(model, dict)]
    if api_visible_only:
        result = [
            model
            for model in result
            if model.get("visibility") == "list" and model.get("supported_in_api") is True
        ]
    return result


def reasoning_efforts(model: dict[str, Any]) -> list[str]:
    values = []
    for item in model.get("supported_reasoning_levels") or []:
        if isinstance(item, dict) and item.get("effort"):
            values.append(str(item["effort"]))
    return values


def service_tier_ids(model: dict[str, Any]) -> list[str]:
    values = []
    for item in model.get("service_tiers") or []:
        if isinstance(item, dict) and item.get("id"):
            values.append(str(item["id"]))
    return values


def derived_tools(model: dict[str, Any]) -> list[str]:
    tools = []
    if model.get("supports_search_tool") is True:
        tools.append("web_search")
    if model.get("apply_patch_tool_type"):
        tools.append("apply_patch")
    for tool in model.get("experimental_supported_tools") or []:
        tools.append(str(tool))
    if "image" in (model.get("input_modalities") or []):
        tools.append("image_input")
    return tools


def print_capability_tables(models: list[dict[str, Any]]) -> None:
    print("\nCore model capabilities:")
    print_table(
        [
            "slug",
            "visibility",
            "api",
            "context",
            "modalities",
            "parallel",
            "verbosity",
            "default_verbosity",
            "summary",
            "default_summary",
            "reasoning_efforts",
        ],
        [
            [
                model.get("slug"),
                model.get("visibility"),
                model.get("supported_in_api"),
                model.get("context_window") or model.get("max_context_window"),
                model.get("input_modalities") or [],
                model.get("supports_parallel_tool_calls"),
                model.get("support_verbosity"),
                model.get("default_verbosity"),
                model.get("supports_reasoning_summaries"),
                model.get("default_reasoning_summary"),
                reasoning_efforts(model),
            ]
            for model in models
        ],
    )

    print("\nTool-related capabilities:")
    print_table(
        [
            "slug",
            "search",
            "search_type",
            "apply_patch",
            "experimental_tools",
            "image_detail_original",
            "service_tiers",
            "speed_aliases",
            "derived_tools",
        ],
        [
            [
                model.get("slug"),
                model.get("supports_search_tool"),
                model.get("web_search_tool_type"),
                model.get("apply_patch_tool_type"),
                model.get("experimental_supported_tools") or [],
                model.get("supports_image_detail_original"),
                service_tier_ids(model),
                model.get("additional_speed_tiers") or [],
                derived_tools(model),
            ]
            for model in models
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Print /codex/models capability tables.")
    parser.add_argument(
        "--api-visible-only",
        action="store_true",
        help="Only show models where visibility=list and supported_in_api=true.",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Gateway base URL. Default: {BASE_URL}",
    )
    args = parser.parse_args()

    payload = fetch_codex_models(args.base_url)
    models = models_from_payload(payload, api_visible_only=args.api_visible_only)

    print(f"gateway base_url: {args.base_url}")
    print(f"codex_models_url: {gateway_root(args.base_url)}/codex/models")
    print(f"model_count: {len(models)}")
    print(f"api_visible_only: {str(args.api_visible_only).lower()}")

    print_capability_tables(models)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
