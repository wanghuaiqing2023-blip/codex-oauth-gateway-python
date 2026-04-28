# codex-oauth-gateway-python

This directory is an **isolated Python migration workspace** for `experiments/codex-oauth-gateway`.

## Scope
- Build a Python implementation of the gateway incrementally.
- Keep `experiments/codex-oauth-gateway` unchanged during migration.

## Current status (v0 scaffold)
- Basic Python HTTP server with `GET /health` and `POST /responses`.
- Model normalization and SSE final-event parsing helpers.
- Structured gateway errors (`status` + `code`).
- Minimal unit tests for normalization/response helpers.

## Run locally
```bash
cd codex-oauth-gateway-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m unittest discover -s tests
python main.py
```

Then check:
```bash
curl -s http://127.0.0.1:8787/health
```

## Notes
- This is migration work-in-progress and not feature-parity yet.
- OAuth token refresh flow is intentionally deferred to the next iteration.
