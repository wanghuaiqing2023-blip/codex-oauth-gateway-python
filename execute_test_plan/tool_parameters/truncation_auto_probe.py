from __future__ import annotations

from truncation_common import BASE_URL
from truncation_common import MODEL
from truncation_common import OUTPUT_DIR
from truncation_common import print_result
from truncation_common import run_truncation_case
from truncation_common import write_result_files


RESPONSE_JSON_PATH = OUTPUT_DIR / "truncation_auto_response.json"
RESULT_JSON_PATH = OUTPUT_DIR / "truncation_auto_results.json"
RESULT_MD_PATH = OUTPUT_DIR / "truncation_auto_results.md"


def main() -> int:
    print(f"gateway base_url: {BASE_URL}")
    print(f"requested_model: {MODEL}")
    print("parameter: truncation")
    print("value: auto")
    print("intent: verify whether Codex backend accepts the official truncation=auto value")

    result = run_truncation_case(
        case_id="truncation_auto",
        intent="explicit official truncation=auto",
        truncation_value="auto",
        response_json_path=RESPONSE_JSON_PATH,
    )
    write_result_files("Truncation Auto Results", RESULT_JSON_PATH, RESULT_MD_PATH, result)

    print("\nSummary:")
    print_result(result)
    print("\nFiles:")
    print(f"result_json: {RESULT_JSON_PATH}")
    print(f"result_md: {RESULT_MD_PATH}")
    if result.get("response_json"):
        print(f"response_json: {result['response_json']}")
    else:
        print("response_json: <not generated because request was rejected>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
