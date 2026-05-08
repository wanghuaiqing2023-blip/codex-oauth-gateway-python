from __future__ import annotations

import base64
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
IMAGE_PATH = OUTPUT_DIR / "image_generation_result.png"
RESPONSE_JSON_PATH = OUTPUT_DIR / "image_generation_response.json"

PROMPT = (
    "Use the image_generation tool to create a small, simple PNG image: "
    "a red square centered on a white background. "
    "After generating the image, reply with exactly: image-generation-probe-ok"
)


def build_client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY, max_retries=0)


def response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return json.loads(json.dumps(response, default=str))


def error_message(error: OpenAIError) -> str:
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


def output_item_types(payload: dict[str, Any]) -> list[str]:
    output = payload.get("output")
    if not isinstance(output, list):
        return []
    return [str(item.get("type", "<missing>")) for item in output if isinstance(item, dict)]


def image_format(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    return "unknown"


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


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: image_generation")
    print("tool_shape: {\"type\":\"image_generation\",\"output_format\":\"png\"}")
    print(f"prompt: {PROMPT!r}")

    client = build_client()
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=PROMPT,
            tools=[{"type": "image_generation", "output_format": "png"}],
            tool_choice="required",
        )
    except OpenAIError as error:
        print("\nProbe result:")
        print_table(
            ["status", "actual_model", "output_item_types", "elapsed_ms", "observation"],
            [["rejected", "", [], int((time.perf_counter() - started) * 1000), error_message(error)]],
        )
        return 0

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    RESPONSE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    matches = find_objects_by_type(payload, "image_generation_call")
    status = "accepted_no_evidence"
    observation = "image_generation_call not found"
    saved_image = ""
    byte_count = 0
    detected_format = ""

    if matches:
        call = matches[0][1]
        result = call.get("result")
        if isinstance(result, str) and result:
            try:
                image_bytes = base64.b64decode(result, validate=True)
                byte_count = len(image_bytes)
                detected_format = image_format(image_bytes)
                IMAGE_PATH.write_bytes(image_bytes)
                saved_image = str(IMAGE_PATH)
                status = "supported"
                observation = f"{matches[0][0]}.result saved"
            except Exception as error:  # noqa: BLE001 - report malformed tool payload.
                status = "malformed_result"
                observation = f"{type(error).__name__}: {error}"
        else:
            status = "no_image_result"
            observation = f"{matches[0][0]} exists but result is missing"

    print("\nProbe result:")
    print_table(
        [
            "status",
            "actual_model",
            "response_status",
            "output_item_types",
            "elapsed_ms",
            "image_format",
            "image_bytes",
            "saved_image",
        ],
        [
            [
                status,
                getattr(response, "model", None),
                getattr(response, "status", None),
                output_item_types(payload),
                elapsed_ms,
                detected_format,
                byte_count,
                saved_image,
            ]
        ],
    )

    print("\nObservation:")
    print(observation)
    print(f"response_json: {RESPONSE_JSON_PATH}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
