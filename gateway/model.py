from __future__ import annotations

def requested_model(model: object) -> str | None:
    """Return an explicit caller model without rewriting it."""
    if isinstance(model, str) and model:
        return model
    return None


def normalize_model(model: str | None) -> str | None:
    """Deprecated compatibility wrapper.

    Explicit model ids are now forwarded unchanged. Missing models are resolved
    by the gateway server from environment/backend defaults.
    """
    return requested_model(model)
