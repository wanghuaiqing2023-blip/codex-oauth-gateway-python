from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import (
    error_message,
    find_key_values,
    find_objects_by_type,
    output_item_types,
    print_probe_result,
    response_to_dict,
    summarize_match,
    summarize_object_match,
)


WEB_SEARCH_TOOL = {"type": "web_search", "external_web_access": True}


def main() -> int:
    print_config()
    print("parameter: tool_choice")
    print("value: auto")
    print("tool: web_search with external_web_access=true")
    print("intent: verify whether Codex backend accepts explicit tool_choice with a Codex-compatible tool")
    print("Codex CLI note: public ResponsesApiRequest includes tool_choice and Codex CLI uses auto")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="auto",
            input=(
                "Use web search if useful. Find the current title or headline on openai.com, "
                "then answer in one short sentence."
            ),
        )
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return 0

    payload = response_to_dict(response)
    web_search_matches = find_objects_by_type(payload, "web_search_call")
    web_results_matches = find_key_values(payload, "results")
    used_tool = bool(web_search_matches or web_results_matches)
    status = "supported" if used_tool else "accepted_without_observed_tool_call"

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"status: {getattr(response, 'status', None)}")
    print(f"actual_model: {getattr(response, 'model', None)}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    print(f"output_item_types: {output_item_types(payload)}")
    print(f"web_search_observation: {summarize_object_match(web_search_matches) if web_search_matches else summarize_match(web_results_matches)}")
    print_probe_result(status, "request succeeded with explicit tool_choice=auto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
