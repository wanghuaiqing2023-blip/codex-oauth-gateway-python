from __future__ import annotations

def normalize_model(model: str | None) -> str:
    if not model:
        return "gpt-5.1"

    model_id = model.split("/")[-1].lower()

    if "gpt-5.2-codex" in model_id:
        return "gpt-5.2-codex"
    if "gpt-5.2" in model_id:
        return "gpt-5.2"
    if "gpt-5.1-codex-max" in model_id:
        return "gpt-5.1-codex-max"
    if "gpt-5.1-codex-mini" in model_id or model_id == "codex-mini-latest":
        return "gpt-5.1-codex-mini"
    if "gpt-5-codex-mini" in model_id:
        return "gpt-5.1-codex-mini"
    if "gpt-5.1-codex" in model_id or "gpt-5-codex" in model_id or "codex" in model_id:
        return "gpt-5.1-codex"
    if "gpt-5.1" in model_id or "gpt-5" in model_id:
        return "gpt-5.1"

    return "gpt-5.1"
