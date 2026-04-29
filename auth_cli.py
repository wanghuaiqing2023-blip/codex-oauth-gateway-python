from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from gateway.auth import (
    create_authorization_flow,
    exchange_authorization_code,
    parse_authorization_input,
    save_tokens,
)


def _wait_for_callback(expected_state: str, timeout_seconds: int = 180) -> tuple[str | None, str | None]:
    result = {"code": None, "state": None}
    done = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
                return

            query = parse_qs(parsed.query)
            result["code"] = query.get("code", [None])[0]
            result["state"] = query.get("state", [None])[0]
            done.set()

            self.send_response(200)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OAuth callback received. You can return to terminal.")

        def log_message(self, format, *args):  # noqa: A003
            return

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 1455), CallbackHandler)
    except OSError:
        return None, None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        done.wait(timeout_seconds)
        return result["code"], result["state"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def main() -> int:
    flow = create_authorization_flow()
    print("Open this URL in your browser and complete login (trying auto-open):\n")
    print(flow.url)
    try:
        webbrowser.open(flow.url)
    except Exception:
        pass

    print("\nWaiting for callback on http://localhost:1455/auth/callback ...")
    code, state = _wait_for_callback(flow.state)

    if not code:
        print("No callback captured. Paste callback URL, 'code=...&state=...', or 'code#state':")
        raw = input("> ")
        code, state = parse_authorization_input(raw)

    if not code:
        print("No authorization code found.")
        return 1
    if state and state != flow.state:
        print("State mismatch. Aborting.")
        return 1

    tokens = exchange_authorization_code(code, flow.verifier)
    save_tokens(tokens)
    print("OAuth tokens saved successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
