from __future__ import annotations

import base64
import json
import os
import struct
import time
from pathlib import Path
from typing import Any

from openai import APIStatusError, OpenAI, OpenAIError


BASE_URL = os.getenv("CODEX_GATEWAY_BASE_URL", "http://127.0.0.1:8787/v1")
API_KEY = os.getenv("CODEX_GATEWAY_API_KEY", "local-dummy-key")
MODEL = os.getenv("CODEX_GATEWAY_MODEL", "gpt-5.2")

OUTPUT_DIR = Path(__file__).resolve().parent
IMAGE_DIR = OUTPUT_DIR / "image_generation_matrix_images"
RESPONSE_DIR = OUTPUT_DIR / "image_generation_matrix_responses"
RESULT_JSON_PATH = OUTPUT_DIR / "image_generation_tool_matrix_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "image_generation_tool_matrix_results.md"

BASE_PROMPT = (
    "Use the image_generation tool to generate a simple test image: "
    "a centered blue circle on a plain background. "
    "After generating the image, reply with exactly: image-generation-matrix-ok"
)
TRANSPARENT_PROMPT = (
    "Use the image_generation tool to generate a simple blue circle icon with a transparent background. "
    "After generating the image, reply with exactly: image-generation-matrix-ok"
)

CASES = [
    (
        "default_tool",
        "baseline with only type=image_generation",
        {"type": "image_generation"},
        BASE_PROMPT,
    ),
    (
        "output_format_png",
        "explicit output_format=png",
        {"type": "image_generation", "output_format": "png", "quality": "low"},
        BASE_PROMPT,
    ),
    (
        "output_format_jpeg_compression_50",
        "output_format=jpeg with output_compression=50",
        {
            "type": "image_generation",
            "output_format": "jpeg",
            "output_compression": 50,
            "quality": "low",
        },
        BASE_PROMPT,
    ),
    (
        "output_format_webp_compression_50",
        "output_format=webp with output_compression=50",
        {
            "type": "image_generation",
            "output_format": "webp",
            "output_compression": 50,
            "quality": "low",
        },
        BASE_PROMPT,
    ),
    (
        "size_1024x1024_quality_low",
        "explicit size=1024x1024",
        {"type": "image_generation", "size": "1024x1024", "quality": "low"},
        BASE_PROMPT,
    ),
    (
        "quality_low",
        "explicit quality=low",
        {"type": "image_generation", "quality": "low"},
        BASE_PROMPT,
    ),
    (
        "background_transparent_png",
        "background=transparent with png",
        {
            "type": "image_generation",
            "background": "transparent",
            "output_format": "png",
            "quality": "low",
        },
        TRANSPARENT_PROMPT,
    ),
    (
        "action_generate",
        "explicit action=generate",
        {"type": "image_generation", "action": "generate", "quality": "low"},
        BASE_PROMPT,
    ),
    (
        "moderation_low",
        "explicit moderation=low",
        {"type": "image_generation", "moderation": "low", "quality": "low"},
        BASE_PROMPT,
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


def image_format(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def png_info(image_bytes: bytes) -> tuple[int | None, int | None, bool | None]:
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n") or len(image_bytes) < 26:
        return None, None, None
    width, height = struct.unpack(">II", image_bytes[16:24])
    color_type = image_bytes[25]
    has_alpha = color_type in {4, 6}
    return width, height, has_alpha


def jpeg_info(image_bytes: bytes) -> tuple[int | None, int | None]:
    if not image_bytes.startswith(b"\xff\xd8"):
        return None, None
    index = 2
    while index + 9 < len(image_bytes):
        if image_bytes[index] != 0xFF:
            index += 1
            continue
        marker = image_bytes[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(image_bytes):
            break
        segment_length = struct.unpack(">H", image_bytes[index : index + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 <= len(image_bytes):
                height = struct.unpack(">H", image_bytes[index + 3 : index + 5])[0]
                width = struct.unpack(">H", image_bytes[index + 5 : index + 7])[0]
                return width, height
        index += segment_length
    return None, None


def webp_info(image_bytes: bytes) -> tuple[int | None, int | None, bool | None]:
    if not (image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP"):
        return None, None, None
    chunk = image_bytes[12:16]
    if chunk == b"VP8X" and len(image_bytes) >= 30:
        flags = image_bytes[20]
        width = 1 + int.from_bytes(image_bytes[24:27], "little")
        height = 1 + int.from_bytes(image_bytes[27:30], "little")
        has_alpha = bool(flags & 0x10)
        return width, height, has_alpha
    if chunk == b"VP8 " and len(image_bytes) >= 30:
        width = struct.unpack("<H", image_bytes[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", image_bytes[28:30])[0] & 0x3FFF
        return width, height, False
    if chunk == b"VP8L" and len(image_bytes) >= 25:
        bits = int.from_bytes(image_bytes[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height, True
    return None, None, None


def image_info(image_bytes: bytes) -> tuple[str, int | None, int | None, bool | None]:
    detected_format = image_format(image_bytes)
    if detected_format == "png":
        width, height, has_alpha = png_info(image_bytes)
        return detected_format, width, height, has_alpha
    if detected_format == "jpeg":
        width, height = jpeg_info(image_bytes)
        return detected_format, width, height, False
    if detected_format == "webp":
        width, height, has_alpha = webp_info(image_bytes)
        return detected_format, width, height, has_alpha
    return detected_format, None, None, None


def image_extension(detected_format: str) -> str:
    if detected_format in {"png", "jpeg", "webp"}:
        return "jpg" if detected_format == "jpeg" else detected_format
    return "bin"


def scrub_result_base64(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, child_value in value.items():
            if key == "result" and isinstance(child_value, str) and len(child_value) > 120:
                scrubbed[key] = f"<base64 omitted; chars={len(child_value)}>"
            else:
                scrubbed[key] = scrub_result_base64(child_value)
        return scrubbed
    if isinstance(value, list):
        return [scrub_result_base64(item) for item in value]
    return value


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


def run_case(client: OpenAI, case_id: str, intent: str, tool_shape: dict[str, Any], prompt: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=MODEL,
            input=prompt,
            tools=[tool_shape],
            tool_choice="required",
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
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "image_generation_calls": 0,
            "call_status": "",
            "call_action": "",
            "call_output_format": "",
            "call_size": "",
            "call_quality": "",
            "call_background": "",
            "requested_format": tool_shape.get("output_format", "<default>"),
            "format_matches": None,
            "detected_format": "",
            "image_bytes": 0,
            "width": None,
            "height": None,
            "has_alpha": None,
            "saved_image": "",
            "response_json": "",
            "output_text": "",
            "revised_prompt_present": False,
            "observation": error_message(error),
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    RESPONSE_DIR.mkdir(parents=True, exist_ok=True)
    response_path = RESPONSE_DIR / f"{case_id}.json"
    response_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    matches = find_objects_by_type(payload, "image_generation_call")
    result: dict[str, Any] = {
        "case": case_id,
        "intent": intent,
        "tool_shape": tool_shape,
        "status": "accepted_no_evidence",
        "actual_model": getattr(response, "model", None) or payload.get("model") or "",
        "response_status": getattr(response, "status", None) or payload.get("status") or "",
        "output_item_types": output_item_types(payload),
        "elapsed_ms": elapsed_ms,
        "image_generation_calls": len(matches),
        "call_status": "",
        "call_action": "",
        "call_output_format": "",
        "call_size": "",
        "call_quality": "",
        "call_background": "",
        "requested_format": tool_shape.get("output_format", "<default>"),
        "format_matches": None,
        "detected_format": "",
        "image_bytes": 0,
        "width": None,
        "height": None,
        "has_alpha": None,
        "saved_image": "",
        "response_json": str(response_path),
        "output_text": output_text(response, payload),
        "revised_prompt_present": False,
        "observation": "image_generation_call not found",
    }

    if not matches:
        return result

    call_path, call = matches[0]
    result["call_status"] = str(call.get("status") or "")
    result["call_action"] = str(call.get("action") or "")
    result["call_output_format"] = str(call.get("output_format") or "")
    result["call_size"] = str(call.get("size") or "")
    result["call_quality"] = str(call.get("quality") or "")
    result["call_background"] = str(call.get("background") or "")
    result["revised_prompt_present"] = isinstance(call.get("revised_prompt"), str) and bool(call.get("revised_prompt"))

    encoded = call.get("result")
    if not isinstance(encoded, str) or not encoded:
        result["status"] = "no_image_result"
        result["observation"] = f"{call_path} exists but result is missing"
        return result

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception as error:  # noqa: BLE001 - report malformed tool payload.
        result["status"] = "malformed_result"
        result["observation"] = f"{type(error).__name__}: {error}"
        return result

    detected_format, width, height, has_alpha = image_info(image_bytes)
    requested_format = tool_shape.get("output_format")
    format_matches = requested_format in {None, detected_format}
    status = "supported" if format_matches else "accepted_format_mismatch"
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = IMAGE_DIR / f"{case_id}.{image_extension(detected_format)}"
    image_path.write_bytes(image_bytes)

    result.update(
        {
            "status": status,
            "detected_format": detected_format,
            "format_matches": format_matches,
            "image_bytes": len(image_bytes),
            "width": width,
            "height": height,
            "has_alpha": has_alpha,
            "saved_image": str(image_path),
            "observation": f"{call_path}.result decoded and saved",
        }
    )
    return result


def write_results(results: list[dict[str, Any]]) -> None:
    summary_payload = {
        "base_url": BASE_URL,
        "requested_model": MODEL,
        "prompt": BASE_PROMPT,
        "transparent_prompt": TRANSPARENT_PROMPT,
        "results": [scrub_result_base64(result) for result in results],
    }
    RESULT_JSON_PATH.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = [
        [
            result["case"],
            result["status"],
            result["actual_model"],
            result["requested_format"],
            result["format_matches"],
            result["detected_format"],
            result["call_output_format"],
            result["call_size"],
            result["call_quality"],
            result["call_background"],
            result["width"],
            result["height"],
            result["has_alpha"],
            result["image_bytes"],
            result["call_action"],
            result["revised_prompt_present"],
            result["elapsed_ms"],
            result["observation"],
        ]
        for result in results
    ]
    details_rows = [
        [
            result["case"],
            result["intent"],
            result["tool_shape"],
            result["saved_image"],
            result["response_json"],
            result["output_text"],
        ]
        for result in results
    ]
    md = "\n\n".join(
        [
            "# Image Generation Tool Matrix Results",
            f"- gateway base_url: `{BASE_URL}`",
            f"- requested_model: `{MODEL}`",
            "",
            "## Summary",
            markdown_table(
                [
                    "case",
                    "status",
                    "actual_model",
                    "requested_format",
                    "format_matches",
                    "detected_format",
                    "call_output_format",
                    "call_size",
                    "call_quality",
                    "call_background",
                    "width",
                    "height",
                    "has_alpha",
                    "image_bytes",
                    "call_action",
                    "revised_prompt",
                    "elapsed_ms",
                    "observation",
                ],
                rows,
            ),
            "## Details",
            markdown_table(
                ["case", "intent", "tool_shape", "saved_image", "response_json", "output_text"],
                details_rows,
            ),
        ]
    )
    RESULT_MD_PATH.write_text(md, encoding="utf-8")


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: image_generation")
    print("intent: verify image_generation generation-parameter matrix")
    print(f"cases: {len(CASES)}")

    client = build_client()
    results = []
    for case_id, intent, tool_shape, prompt in CASES:
        print(f"\nrunning: {case_id} ({intent})")
        result = run_case(client, case_id, intent, tool_shape, prompt)
        results.append(result)
        print(f"status: {result['status']}")
        print(f"observation: {result['observation']}")

    write_results(results)

    print("\nSummary:")
    print_table(
        [
            "case",
            "status",
            "actual_model",
            "requested_format",
            "format_matches",
            "detected_format",
            "call_output_format",
            "call_size",
            "call_quality",
            "call_background",
            "width",
            "height",
            "has_alpha",
            "image_bytes",
            "elapsed_ms",
        ],
        [
            [
                result["case"],
                result["status"],
                result["actual_model"],
                result["requested_format"],
                result["format_matches"],
                result["detected_format"],
                result["call_output_format"],
                result["call_size"],
                result["call_quality"],
                result["call_background"],
                result["width"],
                result["height"],
                result["has_alpha"],
                result["image_bytes"],
                result["elapsed_ms"],
            ]
            for result in results
        ],
    )

    print("\nFiles:")
    print(f"result_json: {RESULT_JSON_PATH}")
    print(f"result_md: {RESULT_MD_PATH}")
    print(f"image_dir: {IMAGE_DIR}")
    print(f"response_dir: {RESPONSE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
