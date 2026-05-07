from __future__ import annotations

import os

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import (
    error_message,
    find_key_values,
    print_probe_result,
    response_to_dict,
    summarize_match,
    value_present,
)


INCLUDE_VALUE = "file_search_call.results"
VECTOR_STORE_ENV = "CODEX_GATEWAY_VECTOR_STORE_ID"


def parse_vector_store_ids(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def main() -> int:
    print_config()
    print(f"include: {INCLUDE_VALUE}")
    print("intent: verify whether file search result objects are returned when an existing vector store is supplied")

    vector_store_ids = parse_vector_store_ids(os.getenv(VECTOR_STORE_ENV, ""))
    if not vector_store_ids:
        print_probe_result(
            "skipped",
            f"set {VECTOR_STORE_ENV} to one or more comma-separated vector store ids before running this probe",
        )
        return 0

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            include=[INCLUDE_VALUE],
            tools=[{"type": "file_search", "vector_store_ids": vector_store_ids}],
            input="Search the provided files for information about the gateway and summarize one relevant result.",
        )
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return 0

    payload = response_to_dict(response)
    matches = find_key_values(payload, "results")
    status = "supported" if any(value_present(value) for _, value in matches) else "no_evidence"

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    print_probe_result(status, summarize_match(matches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
