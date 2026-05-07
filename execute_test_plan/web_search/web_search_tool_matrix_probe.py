from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openai import APIStatusError, OpenAI, OpenAIError


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

OUTPUT_DIR = Path(__file__).resolve().parent
RESULT_JSON_PATH = OUTPUT_DIR / "web_search_tool_matrix_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "web_search_tool_matrix_results.md"

INCLUDE_FIELDS = ["web_search_call.results", "web_search_call.action.sources"]
BASE_PROMPT = (
    "Use web search to find the current title or headline on openai.com. "
    "Answer in one short sentence and cite the source domain."
)

CASES = [
    (
        "live_external_web_access_true",
        "web_search live search",
        {"type": "web_search", "external_web_access": True},
    ),
    (
        "cached_external_web_access_false",
        "web_search cached/non-live search",
        {"type": "web_search", "external_web_access": False},
    ),
    (
        "context_low",
        "search_context_size=low",
        {"type": "web_search", "external_web_access": True, "search_context_size": "low"},
    ),
    (
        "context_medium",
        "search_context_size=medium",
        {"type": "web_search", "external_web_access": True, "search_context_size": "medium"},
    ),
    (
        "context_high",
        "search_context_size=high",
        {"type": "web_search", "external_web_access": True, "search_context_size": "high"},
    ),
    (
        "allowed_domain_openai",
        "filters.allowed_domains=['openai.com']",
        {
            "type": "web_search",
            "external_web_access": True,
            "filters": {"allowed_domains": ["openai.com"]},
        },
    ),
    (
        "user_location_san_francisco",
        "user_location approximate San Francisco",
        {
            "type": "web_search",
            "external_web_access": True,
            "user_location": {
                "type": "approximate",
                "country": "US",
                "region": "California",
                "city": "San Francisco",
                "timezone": "America/Los_Angeles",
            },
        },
    ),
    (
        "content_types_text",
        "search_content_types=['text']",
        {
            "type": "web_search",
            "external_web_access": True,
            "search_content_types": ["text"],
        },
    ),
    (
        "content_types_text_image",
        "search_content_types=['text','image']",
        {
            "type": "web_search",
            "external_web_access": True,
            "search_content_types": ["text", "image"],
        },
    ),
]


def build_client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY, max_retries=0)


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return json.loads(json.dumps(response, default=str))


def error_message(error: BaseException) -> str:
    if isinstance(error, APIStatusError):
        try:
            payload = error.response.json()
        except Exception:
            return error.response.text
        if isinstance(payload, dict):
            upstream = payload.get("error")
            if isinstance(upstream, dict):
                return str(upstream.get("message") or upstream)
        return json.dumps(payload, ensure_ascii=False)
    return str(error)


def find_objects_by_type(value: Any, object_type: str, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        matches: list[tuple[str, dict[str, Any]]] = []
        if value.get("type") == object_type:
            matches.append((path, value))
        for child_key, child_value in value.items():
            matches.extend(find_objects_by_type(child_value, object_type, f"{path}.{child_key}"))
        return matches
    if isinstance(value, list):
        matches = []
        for index, child_value in enumerate(value):
            matches.extend(find_objects_by_type(child_value, object_type, f"{path}[{index}]"))
        return matches
    return []


def find_key_values(value: Any, key: str, path: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        matches: list[tuple[str, Any]] = []
        for child_key, child_value in value.items():
            child_path = f"{path}.{child_key}"
            if child_key == key:
                matches.append((child_path, child_value))
            matches.extend(find_key_values(child_value, key, child_path))
        return matches
    if isinstance(value, list):
        matches = []
        for index, child_value in enumerate(value):
            matches.extend(find_key_values(child_value, key, f"{path}[{index}]"))
        return matches
    return []


def output_item_types(payload: dict[str, Any]) -> list[str]:
    output = payload.get("output")
    if not isinstance(output, list):
        return []
    return [str(item.get("type", "<missing>")) for item in output if isinstance(item, dict)]


def output_text(response: Any, payload: dict[str, Any]) -> str:
    sdk_output_text = getattr(response, "output_text", None)
    if isinstance(sdk_output_text, str):
        return sdk_output_text

    texts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "".join(texts)


def value_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value:
        return 1
    return 0


def collect_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        raw_url = value.get("url")
        if isinstance(raw_url, str):
            urls.append(raw_url)
        for child_value in value.values():
            urls.extend(collect_urls(child_value))
    elif isinstance(value, list):
        for child_value in value:
            urls.extend(collect_urls(child_value))
    return urls


def compact_urls(urls: list[str], limit: int = 3) -> list[str]:
    seen: list[str] = []
    for url in urls:
        if url not in seen:
            seen.append(url)
        if len(seen) >= limit:
            break
    return seen


def compact_text(value: Any, limit: int = 180) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    text = text.replace("\r\n", "\n").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def summarize_web_search_actions(calls: list[tuple[str, dict[str, Any]]]) -> tuple[list[str], list[str]]:
    action_types: list[str] = []
    action_urls: list[str] = []
    for _path, call in calls:
        action = call.get("action")
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if isinstance(action_type, str) and action_type not in action_types:
            action_types.append(action_type)
        action_url = action.get("url")
        if isinstance(action_url, str) and action_url not in action_urls:
            action_urls.append(action_url)
    return action_types, action_urls


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
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


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [format_value(value).replace("|", "\\|").replace("\n", " ") for value in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run_case(client: OpenAI, case_id: str, intent: str, tool_shape: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=BASE_PROMPT,
            tools=[tool_shape],
            tool_choice="required",
            include=INCLUDE_FIELDS,
            reasoning={"effort": "low", "summary": "auto"},
            text={"verbosity": "low"},
        )
    except OpenAIError as error:
        return {
            "case": case_id,
            "intent": intent,
            "tool_shape": tool_shape,
            "status": "rejected",
            "actual_model": "",
            "response_status": "",
            "output_item_types": [],
            "web_search_calls": 0,
            "results_count": 0,
            "sources_count": 0,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "output_text": "",
            "sample_urls": [],
            "observation": error_message(error),
            "response_payload": None,
        }
    except Exception as error:  # noqa: BLE001 - probes should report unexpected client/runtime errors.
        return {
            "case": case_id,
            "intent": intent,
            "tool_shape": tool_shape,
            "status": "client_error",
            "actual_model": "",
            "response_status": "",
            "output_item_types": [],
            "web_search_calls": 0,
            "results_count": 0,
            "sources_count": 0,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "output_text": "",
            "sample_urls": [],
            "observation": f"{type(error).__name__}: {error}",
            "response_payload": None,
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    web_search_calls = find_objects_by_type(payload, "web_search_call")
    action_types, action_urls = summarize_web_search_actions(web_search_calls)
    result_matches = find_key_values(payload, "results")
    source_matches = find_key_values(payload, "sources")
    results_count = sum(value_count(value) for _path, value in result_matches)
    sources_count = sum(value_count(value) for _path, value in source_matches)
    urls = compact_urls(collect_urls([value for _path, value in result_matches] + [value for _path, value in source_matches]))
    status = "supported" if web_search_calls else "accepted_no_web_search_call"

    observation_parts = []
    if action_types:
        observation_parts.append(f"action_types={json.dumps(action_types, ensure_ascii=False, separators=(',', ':'))}")
    if action_urls:
        observation_parts.append(f"action_urls={json.dumps(action_urls, ensure_ascii=False, separators=(',', ':'))}")
    if result_matches:
        observation_parts.append(f"results={compact_text(result_matches[0][1])}")
    if source_matches:
        observation_parts.append(f"sources={compact_text(source_matches[0][1])}")
    if not observation_parts:
        observation_parts.append("no included results or sources found")

    return {
        "case": case_id,
        "intent": intent,
        "tool_shape": tool_shape,
        "status": status,
        "actual_model": getattr(response, "model", None) or payload.get("model") or "",
        "response_status": getattr(response, "status", None) or payload.get("status") or "",
        "output_item_types": output_item_types(payload),
        "web_search_calls": len(web_search_calls),
        "action_types": action_types,
        "action_urls": action_urls,
        "results_count": results_count,
        "sources_count": sources_count,
        "elapsed_ms": elapsed_ms,
        "output_text": output_text(response, payload),
        "sample_urls": urls,
        "observation": "; ".join(observation_parts),
        "response_payload": payload,
    }


def write_results(results: list[dict[str, Any]]) -> None:
    payload = {
        "base_url": BASE_URL,
        "requested_model": MODEL,
        "include": INCLUDE_FIELDS,
        "prompt": BASE_PROMPT,
        "results": results,
    }
    RESULT_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_rows = [
        [
            result["case"],
            result["status"],
            result["actual_model"],
            result["web_search_calls"],
            result.get("action_types", []),
            result["results_count"],
            result["sources_count"],
            result.get("action_urls", []),
            result["elapsed_ms"],
            result["sample_urls"],
            result["output_text"],
        ]
        for result in results
    ]
    details_rows = [
        [
            result["case"],
            result["intent"],
            result["tool_shape"],
            result["observation"],
        ]
        for result in results
    ]
    md = "\n\n".join(
        [
            "# Web Search Tool Matrix Results",
            f"- gateway base_url: `{BASE_URL}`",
            f"- requested_model: `{MODEL}`",
            f"- include: `{json.dumps(INCLUDE_FIELDS)}`",
            "",
            "## Interpretation",
            (
                "`web_search_call.action.sources` is expected on `action.type=\"search\"`. "
                "`action.type=\"open_page\"` uses `action.url` instead, so a zero `sources_count` "
                "is not a missing-source failure when `action_urls` is populated."
            ),
            "",
            "## Summary",
            markdown_table(
                [
                    "case",
                    "status",
                    "actual_model",
                    "web_search_calls",
                    "action_types",
                    "results_count",
                    "sources_count",
                    "action_urls",
                    "elapsed_ms",
                    "sample_urls",
                    "output_text",
                ],
                summary_rows,
            ),
            "## Details",
            markdown_table(["case", "intent", "tool_shape", "observation"], details_rows),
        ]
    )
    RESULT_MD_PATH.write_text(md, encoding="utf-8")


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: web_search")
    print(f"include: {json.dumps(INCLUDE_FIELDS)}")
    print("intent: verify web_search parameter matrix and included result/source objects")

    client = build_client()
    results = []
    for case_id, intent, tool_shape in CASES:
        print(f"\nrunning: {case_id} ({intent})")
        result = run_case(client, case_id, intent, tool_shape)
        results.append(result)
        print(f"status: {result['status']}")
        if result["observation"]:
            print(f"observation: {result['observation']}")

    write_results(results)

    print("\nSummary:")
    print_table(
        [
            "case",
            "status",
             "actual_model",
             "calls",
             "action_types",
             "results",
             "sources",
             "action_urls",
             "elapsed_ms",
             "sample_urls",
         ],
        [
            [
                result["case"],
                result["status"],
                result["actual_model"],
                result["web_search_calls"],
                result.get("action_types", []),
                result["results_count"],
                result["sources_count"],
                result.get("action_urls", []),
                result["elapsed_ms"],
                result["sample_urls"],
            ]
            for result in results
        ],
    )

    print("\nOutput text:")
    for result in results:
        print(f"[{result['case']}] {result['output_text']!r}")

    print("\nFiles:")
    print(f"result_json: {RESULT_JSON_PATH}")
    print(f"result_md: {RESULT_MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
