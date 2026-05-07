from __future__ import annotations

import json
import re
from typing import Any

import requests
from openai import OpenAIError

from _common import MODEL, build_client, gateway_root, print_config
from _probe_common import error_message


VERBOSITY_VALUES = ("low", "medium", "high")
REASONING = {"effort": "medium", "summary": "auto"}
PROMPT = (
    "Explain this Python snippet for a new developer, including how total changes "
    "during the loop:\n\n"
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


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def line_count(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def run_probe_case(client: Any, verbosity: str) -> dict[str, Any]:
    try:
        response = client.responses.create(
            model=MODEL,
            reasoning=REASONING,
            text={"verbosity": verbosity},
            input=PROMPT,
        )
    except OpenAIError as error:
        return {
            "verbosity": verbosity,
            "reasoning": REASONING,
            "status": "rejected",
            "actual_model": "",
            "response_status": "",
            "chars": 0,
            "words": 0,
            "lines": 0,
            "output_text": "",
            "observation": error_message(error),
        }

    output_text = getattr(response, "output_text", None) or ""
    return {
        "verbosity": verbosity,
        "reasoning": REASONING,
        "status": "supported",
        "actual_model": getattr(response, "model", None),
        "response_status": getattr(response, "status", None),
        "chars": len(output_text),
        "words": word_count(output_text),
        "lines": line_count(output_text),
        "output_text": output_text,
        "observation": "request accepted",
    }


def main() -> int:
    print_config()
    print("parameter: text.verbosity")
    print("intent: verify accepted verbosity values and observe output detail differences")
    print("Codex CLI note: public TextControls includes verbosity values low, medium, and high")
    print(f"fixed_reasoning: {json.dumps(REASONING, ensure_ascii=False)}")

    payload = codex_models_payload()
    metadata = model_metadata(payload, MODEL) if payload else None
    support_verbosity = metadata.get("support_verbosity") if metadata else None
    default_verbosity = metadata.get("default_verbosity") if metadata else None

    client = build_client()
    results = [run_probe_case(client, verbosity) for verbosity in VERBOSITY_VALUES]
    observed_actual_models = sorted(
        {
            result["actual_model"]
            for result in results
            if result["actual_model"]
        }
    )

    print("\nModel text metadata:")
    print_table(
        [
            "requested_model",
            "observed_actual_models",
            "support_verbosity",
            "default_verbosity",
            "tested_values",
        ],
        [[MODEL, observed_actual_models, support_verbosity, default_verbosity, VERBOSITY_VALUES]],
    )

    print("\nProbe cases:")
    print_table(
        [
            "verbosity",
            "reasoning",
            "status",
            "actual_model",
            "response_status",
            "chars",
            "words",
            "lines",
        ],
        [
            [
                result["verbosity"],
                result["reasoning"],
                result["status"],
                result["actual_model"],
                result["response_status"],
                result["chars"],
                result["words"],
                result["lines"],
            ]
            for result in results
        ],
    )

    print("\nOutput details:")
    for result in results:
        print(f"[verbosity={result['verbosity']}]")
        print(f"reasoning: {json.dumps(result['reasoning'], ensure_ascii=False)}")
        print(f"actual_model: {result['actual_model']}")
        if result["output_text"]:
            print(result["output_text"])
        else:
            print(f"observation: {result['observation']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
