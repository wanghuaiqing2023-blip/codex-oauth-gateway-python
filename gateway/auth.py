import base64
import json
import time
from dataclasses import dataclass

from .config import JWT_CLAIM_PATH, TOKEN_FILE
from .errors import GatewayError


@dataclass
class TokenSet:
    access: str
    refresh: str
    expires: int


def _pad_base64url(value: str) -> str:
    return value + "=" * ((4 - len(value) % 4) % 4)


def decode_jwt(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        data = base64.urlsafe_b64decode(_pad_base64url(payload)).decode("utf-8")
        return json.loads(data)
    except Exception:
        return None


def get_chatgpt_account_id(access_token: str) -> str | None:
    decoded = decode_jwt(access_token)
    if not decoded:
        return None
    claim = decoded.get(JWT_CLAIM_PATH, {})
    return claim.get("chatgpt_account_id")


def load_tokens() -> TokenSet | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        parsed = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        if parsed.get("type") != "oauth":
            return None
        return TokenSet(
            access=parsed["access"],
            refresh=parsed["refresh"],
            expires=int(parsed["expires"]),
        )
    except Exception:
        return None


def get_valid_tokens() -> TokenSet:
    tokens = load_tokens()
    if not tokens:
        raise GatewayError(401, "MISSING_TOKENS", f"No OAuth tokens found at {TOKEN_FILE}")

    # Python migration v0: no refresh flow yet (will be added in next iteration).
    if tokens.expires <= int(time.time() * 1000) + 60_000:
        raise GatewayError(401, "TOKEN_EXPIRED", "Token expired. Re-run auth flow.")

    return tokens
