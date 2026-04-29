import os
from pathlib import Path

DEFAULT_GATEWAY_PORT = int(os.getenv("CODEX_GATEWAY_PORT", "8787"))
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = int(os.getenv("CODEX_UPSTREAM_TIMEOUT_SECONDS", "60"))
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
TOKEN_URL = "https://auth.openai.com/oauth/token"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REDIRECT_URI = "http://localhost:1455/auth/callback"
SCOPE = "openid profile email offline_access"
DEFAULT_TOKEN_FILE = Path.home() / ".codex-oauth-gateway-python" / "openai.json"
TOKEN_FILE = Path(os.getenv("CODEX_GATEWAY_TOKEN_FILE") or DEFAULT_TOKEN_FILE).expanduser()
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


DEFAULT_INSTRUCTIONS = "You are a helpful coding assistant. Answer clearly and directly."
