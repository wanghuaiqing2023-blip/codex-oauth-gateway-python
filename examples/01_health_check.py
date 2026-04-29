from __future__ import annotations

import datetime as dt

import requests

from _common import MODEL, gateway_root


def main() -> int:
    url = f"{gateway_root()}/health"
    response = requests.get(url, timeout=10)
    print(f"GET {url}")
    print(f"requested_model_for_response_examples: {MODEL}")
    print(f"status: {response.status_code}")
    payload = response.json()
    print(f"ok: {payload.get('ok')}")
    print(f"authenticated: {payload.get('authenticated')}")
    print(f"tokenFile: {payload.get('tokenFile')}")
    expires = payload.get("expires")
    if expires:
        expires_at = dt.datetime.fromtimestamp(expires / 1000, tz=dt.timezone.utc)
        print(f"expires_utc: {expires_at.isoformat()}")
    return 0 if response.ok and payload.get("authenticated") else 1


if __name__ == "__main__":
    raise SystemExit(main())
