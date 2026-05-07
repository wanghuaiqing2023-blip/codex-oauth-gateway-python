from __future__ import annotations

from tool_search_common import BASE_URL
from tool_search_common import MODEL
from tool_search_common import OUTPUT_DIR
from tool_search_common import SIMULATED_CALENDAR_NAMESPACE_TOOL
from tool_search_common import build_client
from tool_search_common import print_results
from tool_search_common import request_after_tool_search_output
from tool_search_common import request_tool_search_call
from tool_search_common import write_result_files


RESPONSE1_JSON_PATH = OUTPUT_DIR / "tool_search_hit_roundtrip_response1.json"
RESPONSE2_JSON_PATH = OUTPUT_DIR / "tool_search_hit_roundtrip_response2.json"
RESULT_JSON_PATH = OUTPUT_DIR / "tool_search_hit_roundtrip_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "tool_search_hit_roundtrip_results.md"

PROMPT_AFTER_HIT = (
    "Use the supplied tool_search_output. If it exposes a calendar event creation "
    "tool, reply exactly: tool-search-roundtrip-ok"
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("tool_type: tool_search")
    print("execution: client")
    print("intent: verify backend can consume a non-empty tool_search_output")

    client = build_client()
    results = [request_tool_search_call(client, RESPONSE1_JSON_PATH)]
    tool_search_call = results[0].get("tool_search_call")
    if isinstance(tool_search_call, dict) and results[0].get("status") == "supported":
        phase2 = request_after_tool_search_output(
            client,
            RESPONSE2_JSON_PATH,
            PROMPT_AFTER_HIT,
            tool_search_call,
            [SIMULATED_CALENDAR_NAMESPACE_TOOL],
        )
        phase2["phase"] = "tool_search_output_hit"
        if "tool-search-roundtrip-ok" in phase2["output_text"]:
            phase2["status"] = "supported"
            phase2["observation"] = "model consumed non-empty tool_search_output"
        else:
            phase2["status"] = "accepted_unexpected_answer"
            phase2["observation"] = "response did not contain expected marker"
        results.append(phase2)

    write_result_files(
        "Tool Search Hit Roundtrip Results",
        RESULT_JSON_PATH,
        RESULT_MD_PATH,
        results,
        {"simulated_tool_search_output_tool": SIMULATED_CALENDAR_NAMESPACE_TOOL},
    )

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
