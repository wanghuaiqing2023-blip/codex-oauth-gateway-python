from __future__ import annotations

from tool_search_common import BASE_URL
from tool_search_common import MODEL
from tool_search_common import OUTPUT_DIR
from tool_search_common import build_client
from tool_search_common import print_results
from tool_search_common import request_after_tool_search_output
from tool_search_common import request_tool_search_call
from tool_search_common import write_result_files


RESPONSE1_JSON_PATH = OUTPUT_DIR / "tool_search_empty_result_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "tool_search_empty_result_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "tool_search_empty_result_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "tool_search_empty_result_results.md"

PROMPT_AFTER_EMPTY = (
    "The previous tool_search_output returned no tools. Try another broader "
    "tool_search query for calendar event creation. Do not answer directly."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: tool_search")
    print("execution: client")
    print("intent: verify backend behavior when client returns empty tool_search_output")

    client = build_client()
    results = [request_tool_search_call(client, RESPONSE1_JSON_PATH)]
    tool_search_call = results[0].get("tool_search_call")
    if isinstance(tool_search_call, dict) and results[0].get("status") == "supported":
        phase2 = request_after_tool_search_output(
            client,
            RESPONSE2_JSON_PATH,
            PROMPT_AFTER_EMPTY,
            tool_search_call,
            [],
        )
        phase2["phase"] = "tool_search_output_empty"
        if phase2["call_id"]:
            phase2["status"] = "recovered_with_second_search"
            phase2["observation"] = "backend issued another tool_search_call after empty results"
        else:
            phase2["status"] = "accepted_no_second_search"
            phase2["observation"] = "backend did not retry search"
        results.append(phase2)

    write_result_files("Tool Search Empty Result Probe Results", RESULT_JSON_PATH, RESULT_MD_PATH, results)

    print("\nSummary:")
    print_results(results)
    print("\nFiles:")
    print(f"result_json: {RESULT_JSON_PATH}")
    print(f"result_md: {RESULT_MD_PATH}")
    print(f"response1_json: {RESPONSE1_JSON_PATH}")
    print(f"response2_json: {RESPONSE2_JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
