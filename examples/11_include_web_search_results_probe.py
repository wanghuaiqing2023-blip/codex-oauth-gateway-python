from __future__ import annotations

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


INCLUDE_VALUE = "web_search_call.results"
WEB_SEARCH_TOOL = {"type": "web_search", "external_web_access": True}


def main() -> int:
    print_config()
    print(f"include: {INCLUDE_VALUE}")
    print("tool: web_search with external_web_access=true")
    print("intent: verify whether Codex backend returns web search result objects with the Codex CLI web_search tool shape")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            include=[INCLUDE_VALUE],
            tools=[WEB_SEARCH_TOOL],
            input=(
                "Use web search to find the current headline or title on openai.com. "
                "Reply with one short sentence and cite what you searched for."
            ),
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
