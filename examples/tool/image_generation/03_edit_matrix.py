from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

from openai import OpenAI, OpenAIError

from image_generation_tool_matrix_probe import (
    BASE_URL,
    MODEL,
    build_client,
    error_message,
    find_objects_by_type,
    image_extension,
    image_info,
    markdown_table,
    output_item_types,
    output_text,
    print_table,
    response_to_dict,
    scrub_result_base64,
)


OUTPUT_DIR = Path(__file__).resolve().parent
IMAGE_DIR = OUTPUT_DIR / "image_generation_edit_matrix_images"
RESPONSE_DIR = OUTPUT_DIR / "image_generation_edit_matrix_responses"
RESULT_JSON_PATH = OUTPUT_DIR / "image_generation_edit_matrix_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "image_generation_edit_matrix_results.md"

DEFAULT_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/8/8b/Dog_04343.jpg"
EDIT_PROMPT = (
    "Edit the input image by adding a small red party hat to the main animal. "
    "Keep the original animal and scene recognizable. "
    "After editing the image, reply with exactly: image-edit-matrix-ok"
)
EDIT_WITHOUT_IMAGE_PROMPT = (
    "Edit the image by adding a small red party hat. "
    "After editing the image, reply with exactly: image-edit-matrix-ok"
)

CASES = [
    {
        "case": "action_edit_with_image",
        "intent": "force image editing with action=edit and an input image",
        "tool_shape": {"type": "image_generation", "action": "edit", "quality": "low"},
        "input_mode": "with_image",
        "tool_choice": None,
        "expected_call_action": "edit",
        "expect_rejection": False,
    },
    {
        "case": "action_auto_with_edit_prompt_and_image",
        "intent": "let backend choose action=auto for an edit-style prompt with an input image",
        "tool_shape": {"type": "image_generation", "action": "auto", "quality": "low"},
        "input_mode": "with_image",
        "tool_choice": None,
        "expected_call_action": "edit",
        "expect_rejection": False,
    },
    {
        "case": "tool_choice_force_image_generation_with_image",
        "intent": "force the image_generation tool with tool_choice while providing an edit-style prompt and image",
        "tool_shape": {"type": "image_generation", "quality": "low"},
        "input_mode": "with_image",
        "tool_choice": {"type": "image_generation"},
        "expected_call_action": "edit",
        "expect_rejection": False,
    },
    {
        "case": "action_edit_without_image",
        "intent": "negative probe: action=edit should require an input image",
        "tool_shape": {"type": "image_generation", "action": "edit", "quality": "low"},
        "input_mode": "without_image",
        "tool_choice": None,
        "expected_call_action": "",
        "expect_rejection": True,
    },
]


def build_input(input_mode: str, image_url: str) -> Any:
    if input_mode == "with_image":
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": EDIT_PROMPT},
                    {"type": "input_image", "image_url": image_url, "detail": "low"},
                ],
            }
        ]
    if input_mode == "without_image":
        return EDIT_WITHOUT_IMAGE_PROMPT
    raise ValueError(f"unsupported input_mode: {input_mode}")


def call_responses_create(client: OpenAI, case: dict[str, Any], image_url: str) -> Any:
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "input": build_input(str(case["input_mode"]), image_url),
        "tools": [case["tool_shape"]],
    }
    if case.get("tool_choice") is not None:
        kwargs["tool_choice"] = case["tool_choice"]
    return client.responses.create(**kwargs)


def run_case(client: OpenAI, case: dict[str, Any], image_url: str) -> dict[str, Any]:
    case_id = str(case["case"])
    started = time.perf_counter()
    try:
        response = call_responses_create(client, case, image_url)
    except OpenAIError as error:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "case": case_id,
            "intent": case["intent"],
            "tool_shape": case["tool_shape"],
            "tool_choice": case["tool_choice"] or "",
            "input_mode": case["input_mode"],
            "status": "expected_rejection" if case["expect_rejection"] else "rejected",
            "actual_model": "",
            "response_status": "",
            "output_item_types": [],
            "elapsed_ms": elapsed_ms,
            "image_generation_calls": 0,
            "call_status": "",
            "call_action": "",
            "expected_call_action": case["expected_call_action"],
            "action_matches": None,
            "call_output_format": "",
            "call_size": "",
            "call_quality": "",
            "call_background": "",
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
        "intent": case["intent"],
        "tool_shape": case["tool_shape"],
        "tool_choice": case["tool_choice"] or "",
        "input_mode": case["input_mode"],
        "status": "accepted_no_evidence",
        "actual_model": getattr(response, "model", None) or payload.get("model") or "",
        "response_status": getattr(response, "status", None) or payload.get("status") or "",
        "output_item_types": output_item_types(payload),
        "elapsed_ms": elapsed_ms,
        "image_generation_calls": len(matches),
        "call_status": "",
        "call_action": "",
        "expected_call_action": case["expected_call_action"],
        "action_matches": None,
        "call_output_format": "",
        "call_size": "",
        "call_quality": "",
        "call_background": "",
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
        if case["expect_rejection"]:
            result["status"] = "accepted_without_tool_call"
            result["observation"] = "request was accepted, but image_generation was not called"
        return result

    if case["expect_rejection"]:
        result["status"] = "unexpected_image_generation"
        result["observation"] = "request generated an image even though the case expected no image"

    call_path, call = matches[0]
    call_action = str(call.get("action") or "")
    expected_call_action = str(case["expected_call_action"] or "")
    action_matches = not expected_call_action or call_action == expected_call_action

    result["call_status"] = str(call.get("status") or "")
    result["call_action"] = call_action
    result["action_matches"] = action_matches
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
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = IMAGE_DIR / f"{case_id}.{image_extension(detected_format)}"
    image_path.write_bytes(image_bytes)

    status = "supported" if action_matches else "supported_action_mismatch"
    if case["expect_rejection"]:
        status = "unexpected_image_generation"

    result.update(
        {
            "status": status,
            "detected_format": detected_format,
            "image_bytes": len(image_bytes),
            "width": width,
            "height": height,
            "has_alpha": has_alpha,
            "saved_image": str(image_path),
            "observation": f"{call_path}.result decoded and saved",
        }
    )
    return result


def write_results(results: list[dict[str, Any]], image_url: str) -> None:
    summary_payload = {
        "base_url": BASE_URL,
        "requested_model": MODEL,
        "image_url": image_url,
        "edit_prompt": EDIT_PROMPT,
        "edit_without_image_prompt": EDIT_WITHOUT_IMAGE_PROMPT,
        "results": [scrub_result_base64(result) for result in results],
    }
    RESULT_JSON_PATH.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_rows = [
        [
            result["case"],
            result["status"],
            result["actual_model"],
            result["input_mode"],
            result["tool_choice"],
            result["call_action"],
            result["expected_call_action"],
            result["action_matches"],
            result["detected_format"],
            result["call_size"],
            result["call_quality"],
            result["width"],
            result["height"],
            result["image_bytes"],
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
            "# Image Generation Edit Matrix Results",
            f"- gateway base_url: `{BASE_URL}`",
            f"- requested_model: `{MODEL}`",
            f"- input_image_url: `{image_url}`",
            "",
            "## Summary",
            markdown_table(
                [
                    "case",
                    "status",
                    "actual_model",
                    "input_mode",
                    "tool_choice",
                    "call_action",
                    "expected_action",
                    "action_matches",
                    "detected_format",
                    "call_size",
                    "call_quality",
                    "width",
                    "height",
                    "image_bytes",
                    "elapsed_ms",
                    "observation",
                ],
                summary_rows,
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
    image_url = os.getenv("CODEX_GATEWAY_IMAGE_URL", DEFAULT_IMAGE_URL)
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool: image_generation")
    print("intent: verify image_generation edit behavior")
    print(f"image_url: {image_url}")
    print(f"cases: {len(CASES)}")

    client = build_client()
    results = []
    for case in CASES:
        print(f"\nrunning: {case['case']} ({case['intent']})")
        result = run_case(client, case, image_url)
        results.append(result)
        print(f"status: {result['status']}")
        print(f"observation: {result['observation']}")

    write_results(results, image_url)

    print("\nSummary:")
    print_table(
        [
            "case",
            "status",
            "actual_model",
            "input_mode",
            "call_action",
            "expected_action",
            "action_matches",
            "detected_format",
            "call_size",
            "call_quality",
            "width",
            "height",
            "image_bytes",
            "elapsed_ms",
        ],
        [
            [
                result["case"],
                result["status"],
                result["actual_model"],
                result["input_mode"],
                result["call_action"],
                result["expected_call_action"],
                result["action_matches"],
                result["detected_format"],
                result["call_size"],
                result["call_quality"],
                result["width"],
                result["height"],
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
