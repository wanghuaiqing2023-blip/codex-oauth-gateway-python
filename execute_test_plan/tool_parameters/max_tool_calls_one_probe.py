from __future__ import annotations

from max_tool_calls_common import BASE_URL
from max_tool_calls_common import MODEL
from max_tool_calls_common import OUTPUT_DIR
from max_tool_calls_common import print_result
from max_tool_calls_common import run_max_tool_calls_case
from max_tool_calls_common import write_result_files


RESPONSE_JSON_PATH = OUTPUT_DIR / "max_tool_calls_one_response.json"
RESULT_JSON_PATH = OUTPUT_DIR / "max_tool_calls_one_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "max_tool_calls_one_results.md"

PROMPT = (
    "Use web search to find the current headline on openai.com. "
    "Answer in one short sentence and cite the source domain."
)


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("parameter: max_tool_calls")
    print("value: 1")
    print("intent: verify whether backend accepts max_tool_calls=1 and uses at most one web_search call")

    result = run_max_tool_calls_case(
        case_id="max_tool_calls_one",
        intent="max_tool_calls=1 with required web_search",
        max_tool_calls=1,
        prompt=PROMPT,
        response_json_path=RESPONSE_JSON_PATH,
        tool_choice="required",
    )
    write_result_files("Max Tool Calls One Results", RESULT_JSON_PATH, RESULT_MD_PATH, result)

    print("\nSummary:")
    print_result(result)
    print("\nFiles:")
    print(f"result_json: {RESULT_JSON_PATH}")
    print(f"result_md: {RESULT_MD_PATH}")
    print(f"response_json: {RESPONSE_JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
