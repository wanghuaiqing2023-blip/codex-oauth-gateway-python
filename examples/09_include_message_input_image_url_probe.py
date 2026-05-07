from __future__ import annotations

import os
from typing import Any

from openai import OpenAIError

from _common import MODEL, build_client, print_config, print_openai_error
from _probe_common import find_key_values, response_to_dict, summarize_match


DEFAULT_DOG_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/8/8b/Dog_04343.jpg"
DOG_KEYWORDS = ("dog", "canine", "puppy")
IMAGE_QUESTION = (
    "Answer only based on the image content. "
    "What is the main animal? What is its approximate color? "
    "What posture or scene is it in? "
    "If you cannot see the image, say that clearly."
)


def format_matches(matches: list[tuple[str, Any]], expected_url: str) -> str:
    if not matches:
        return "no image_url fields found in response"

    exact_matches = [path for path, value in matches if value == expected_url]
    if exact_matches:
        return "matched at " + ", ".join(exact_matches)

    return "image_url fields found, but none matched input: " + summarize_match(matches)


def main() -> int:
    print_config()
    image_url = os.getenv("CODEX_GATEWAY_IMAGE_URL", DEFAULT_DOG_IMAGE_URL)
    print(f"image_url_source: {'CODEX_GATEWAY_IMAGE_URL' if image_url != DEFAULT_DOG_IMAGE_URL else 'built-in Wikimedia dog image'}")
    print(f"image_url: {image_url}")

    client = build_client()
    try:
        response = client.responses.create(
            model=MODEL,
            include=["message.input_image.image_url"],
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": IMAGE_QUESTION,
                        },
                        {"type": "input_image", "image_url": image_url, "detail": "low"},
                    ],
                }
            ],
        )
    except OpenAIError as error:
        print_openai_error(error)
        return 1

    output_text = getattr(response, "output_text", "") or ""
    payload = response_to_dict(response)
    image_url_matches = find_key_values(payload, "image_url")
    include_echoed = any(value == image_url for _, value in image_url_matches)
    mentions_dog = any(keyword in output_text.lower() for keyword in DOG_KEYWORDS)

    print("\nImage input probe result:")
    print(f"response.id: {getattr(response, 'id', None)}")
    print(f"actual_model: {getattr(response, 'model', None)}")
    print(f"output_text: {output_text!r}")
    print(f"mentions_dog_like_term: {'yes' if mentions_dog else 'no'}")
    print(f"include_image_url_echoed: {'yes' if include_echoed else 'no'}")
    print(f"image_url_observation: {format_matches(image_url_matches, image_url)}")

    print("\nInterpretation:")
    print("- If output_text describes the animal and visual details, image input likely reached the backend model.")
    print("- If include_image_url_echoed is no, this path did not implement the official include echo for message.input_image.image_url.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
