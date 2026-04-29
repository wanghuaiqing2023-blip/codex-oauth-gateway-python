from __future__ import annotations

import base64
import json
import secrets
import time
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .config import (
    AUTHORIZE_URL,
    CLIENT_ID,
    JWT_CLAIM_PATH,
    REDIRECT_URI,
    SCOPE,
    TOKEN_FILE,
    TOKEN_URL,
)
from .errors import GatewayError


@dataclass
class TokenSet:
    access: str
    refresh: str
    expires: int


@dataclass
class AuthorizationFlow:
    url: str
    verifier: str
    state: str


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


def create_state() -> str:
    return secrets.token_hex(16)


def create_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    challenge = base64.urlsafe_b64encode(sha256(verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
    return verifier, challenge


def create_authorization_flow() -> AuthorizationFlow:
    verifier, challenge = create_pkce_pair()
    state = create_state()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "codex_cli_rs",
        }
    )
    return AuthorizationFlow(url=f"{AUTHORIZE_URL}?{query}", verifier=verifier, state=state)


def parse_authorization_input(value: str) -> tuple[str | None, str | None]:
    raw = value.strip()
    if not raw:
        return None, None

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        query = parse_qs(parsed.query)
        return query.get("code", [None])[0], query.get("state", [None])[0]

    if "code=" in raw:
        query = parse_qs(raw)
        return query.get("code", [None])[0], query.get("state", [None])[0]

    if "#" in raw:
        code, state = raw.split("#", 1)
        return code or None, state or None

    return raw, None


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


def save_tokens(tokens: TokenSet) -> None:
    token_path = Path(TOKEN_FILE)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(
        json.dumps(
            {
                "type": "oauth",
                "access": tokens.access,
                "refresh": tokens.refresh,
                "expires": tokens.expires,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def refresh_access_token(refresh_token: str) -> TokenSet:
    try:
        response = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=30,
        )
    except requests.RequestException as error:
        raise GatewayError(401, "TOKEN_REFRESH_FAILED", f"Token refresh request failed: {error}") from error

    if response.status_code != 200:
        raise GatewayError(
            401,
            "TOKEN_REFRESH_FAILED",
            f"Token refresh failed with status {response.status_code}.",
            response.text,
        )

    try:
        parsed = response.json()
        access = parsed["access_token"]
        refresh = parsed.get("refresh_token", refresh_token)
        expires_in = int(parsed["expires_in"])
    except Exception as error:
        raise GatewayError(401, "TOKEN_REFRESH_FAILED", "Token refresh response missing fields.") from error

    return TokenSet(
        access=access,
        refresh=refresh,
        expires=int(time.time() * 1000) + expires_in * 1000,
    )


def exchange_authorization_code(code: str, verifier: str) -> TokenSet:
    try:
        response = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=30,
        )
    except requests.RequestException as error:
        raise GatewayError(401, "TOKEN_EXCHANGE_FAILED", f"Token exchange request failed: {error}") from error

    if response.status_code != 200:
        raise GatewayError(
            401,
            "TOKEN_EXCHANGE_FAILED",
            f"Token exchange failed with status {response.status_code}.",
            response.text,
        )

    try:
        parsed = response.json()
        access = parsed["access_token"]
        refresh = parsed["refresh_token"]
        expires_in = int(parsed["expires_in"])
    except Exception as error:
        raise GatewayError(401, "TOKEN_EXCHANGE_FAILED", "Token exchange response missing fields.") from error

    return TokenSet(
        access=access,
        refresh=refresh,
        expires=int(time.time() * 1000) + expires_in * 1000,
    )


def get_valid_tokens() -> TokenSet:
    tokens = load_tokens()
    if not tokens:
        raise GatewayError(401, "MISSING_TOKENS", f"No OAuth tokens found at {TOKEN_FILE}")

    if tokens.expires > int(time.time() * 1000) + 60_000:
        return tokens

    refreshed = refresh_access_token(tokens.refresh)
    save_tokens(refreshed)
    return refreshed
