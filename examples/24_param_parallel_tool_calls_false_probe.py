from __future__ import annotations

from openai import OpenAIError

from _common import MODEL, build_client, print_config
from _probe_common import (
    error_message,
    find_objects_by_type,
    output_item_types,
    print_probe_result,
    response_to_dict,
    summarize_object_match,
)


WEB_SEARCH_TOOL = {"type": "web_search", "external_web_access": True}


def main() -> int:
    print_config()
    print("parameter: parallel_tool_calls")
    print("value: false")
    print("tool: web_search with external_web_access=true")
    print("intent: verify whether Codex backend accepts parallel_tool_calls=false with a tool call")
    print("Codex CLI note: public ResponsesApiRequest includes parallel_tool_calls")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="required",
            parallel_tool_calls=False,
            input="Find the current title or headline on openai.com, then answer in one short sentence.",
        )
    except OpenAIError as error:
        print_probe_result("rejected", error_message(error))
        return 0

    payload = response_to_dict(response)
    web_search_matches = find_objects_by_type(payload, "web_search_call")
    status = "supported" if web_search_matches else "accepted_without_observed_tool_call"

    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"status: {getattr(response, 'status', None)}")
    print(f"actual_model: {getattr(response, 'model', None)}")
    print(f"output_text: {getattr(response, 'output_text', None)!r}")
    print(f"output_item_types: {output_item_types(payload)}")
    print(f"web_search_observation: {summarize_object_match(web_search_matches)}")
    print_probe_result(status, "request succeeded with parallel_tool_calls=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
