import json


def is_storage_state_effective(path: str) -> bool:
    """Return True if a Playwright storage_state file has cookies/origins."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get('cookies') or []
        origins = data.get('origins') or []
        return bool(cookies or origins)
    except Exception:
        return False

