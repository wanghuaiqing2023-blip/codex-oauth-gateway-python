from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import error_message, response_to_dict


REASONING = {"effort": "medium", "summary": "auto"}
TEXT = {"verbosity": "low"}
PROMPT = "Reply exactly: service-tier-probe-ok"

SERVICE_TIER_CASES: tuple[tuple[str, str | None, str], ...] = (
    ("omitted", None, "backend default standard speed"),
    ("priority", "priority", "Codex backend wire value for fast/priority speed"),
    ("auto", "auto", "official OpenAI API value"),
    ("default", "default", "official OpenAI API value"),
    ("flex", "flex", "official OpenAI API value"),
    ("fast", "fast", "Codex CLI/UI alias, not the backend wire value"),
)


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    values = [[format_value(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in values:
        if len(row) != len(headers):
            raise ValueError(f"table row has {len(row)} columns, but headers have {len(headers)} columns")
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
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def run_probe_case(client: Any, label: str, service_tier: str | None, meaning: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        if service_tier is None:
            response = client.responses.create(
                model=MODEL,
                reasoning=REASONING,
                text=TEXT,
                input=PROMPT,
            )
        else:
            response = client.responses.create(
                model=MODEL,
                service_tier=service_tier,
                reasoning=REASONING,
                text=TEXT,
                input=PROMPT,
            )
    except OpenAIError as error:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "case": label,
            "sent_service_tier": service_tier or "<absent>",
            "meaning": meaning,
            "status": "rejected",
            "actual_model": "",
            "response_status": "",
            "response_service_tier": "",
            "elapsed_ms": elapsed_ms,
            "output_text": "",
            "observation": error_message(error),
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = response_to_dict(response)
    return {
        "case": label,
        "sent_service_tier": service_tier or "<absent>",
        "meaning": meaning,
        "status": "accepted",
        "actual_model": getattr(response, "model", None),
        "response_status": getattr(response, "status", None),
        "response_service_tier": payload.get("service_tier"),
        "elapsed_ms": elapsed_ms,
        "output_text": getattr(response, "output_text", None) or "",
        "observation": "request accepted",
    }


def main() -> int:
    print_config()
    print("parameter: service_tier")
    print("intent: verify which service_tier wire values the Codex backend accepts on /responses")
    print("Codex CLI note: public ResponsesApiRequest includes service_tier")
    print("OpenAI API note: official service_tier values include auto, default, flex, and priority")
    print("Codex alias note: fast is the Codex CLI/UI user-facing alias; priority is the backend wire value")
    print("baseline: omitted means the client call does not include service_tier and uses standard speed")
    print("metadata note: /codex/models tier fields are capability/display metadata, not current speed state")
    print(f"fixed_reasoning: {json.dumps(REASONING, ensure_ascii=False)}")
    print(f"fixed_text: {json.dumps(TEXT, ensure_ascii=False)}")

    client = build_client()
    results = [
        run_probe_case(client, label, service_tier, meaning)
        for label, service_tier, meaning in SERVICE_TIER_CASES
    ]

    observed_actual_models = sorted(
        {
            result["actual_model"]
            for result in results
            if result["actual_model"]
        }
    )

    print("\nProbe scope:")
    print_table(
        [
            "requested_model",
            "observed_actual_models",
            "tested_values",
        ],
        [
            [
                MODEL,
                observed_actual_models,
                [label for label, _, _ in SERVICE_TIER_CASES],
            ]
        ],
    )

    print("\nProbe cases:")
    print_table(
        [
            "case",
            "sent_service_tier",
            "status",
            "actual_model",
            "response_status",
            "response_service_tier",
            "elapsed_ms",
            "output_text",
        ],
        [
            [
                result["case"],
                result["sent_service_tier"],
                result["status"],
                result["actual_model"],
                result["response_status"],
                result["response_service_tier"],
                result["elapsed_ms"],
                result["output_text"],
            ]
            for result in results
        ],
    )

    print("\nInterpretation:")
    print_table(
        [
            "case",
            "meaning",
            "observation",
        ],
        [
            [
                result["case"],
                result["meaning"],
                result["observation"],
            ]
            for result in results
        ],
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
