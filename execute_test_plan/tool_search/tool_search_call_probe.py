from __future__ import annotations

from tool_search_common import BASE_URL
from tool_search_common import MODEL
from tool_search_common import OUTPUT_DIR
from tool_search_common import build_client
from tool_search_common import print_results
from tool_search_common import request_tool_search_call
from tool_search_common import write_result_files


RESPONSE_JSON_PATH = OUTPUT_DIR / "tool_search_call_probe_response.json"
RESULT_JSON_PATH = OUTPUT_DIR / "tool_search_call_probe_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "tool_search_call_probe_results.md"


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: tool_search")
    print("execution: client")
    print("intent: verify backend can emit tool_search_call from the tool_search schema")

    result = request_tool_search_call(build_client(), RESPONSE_JSON_PATH)
    write_result_files("Tool Search Call Probe Results", RESULT_JSON_PATH, RESULT_MD_PATH, [result])

    print("\nSummary:")
    print_results([result])
    print("\nFiles:")
    print(f"result_json: {RESULT_JSON_PATH}")
    print(f"result_md: {RESULT_MD_PATH}")
    print(f"response_json: {RESPONSE_JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
