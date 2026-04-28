import os
from pathlib import Path

DEFAULT_GATEWAY_PORT = int(os.getenv("CODEX_GATEWAY_PORT", "8787"))
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = int(os.getenv("CODEX_UPSTREAM_TIMEOUT_SECONDS", "60"))
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
TOKEN_FILE = Path(os.getenv("CODEX_GATEWAY_TOKEN_FILE", ".tokens/openai.json"))
JWT_CLAIM_PATH = "https://api.openai.com/auth"

OPENAI_HEADERS = {
    "account_id": "chatgpt-account-id",
    "beta": "OpenAI-Beta",
    "originator": "originator",
    "conversation_id": "conversation_id",
    "session_id": "session_id",
}

OPENAI_HEADER_VALUES = {
    "beta": "responses=experimental",
    "originator": "codex_cli_rs",
}
