import os
import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


@dataclass
class CacheEntry:
    data: Dict[str, Any]
    created_at: datetime


class GmailCache:
    """Simple file-based cache for Gmail code extraction results.

    Keys are derived from a stable string (e.g., the Gmail search query + target email).
    Entries are stored in a single JSON file under `GMAIL_CACHE_DIR` (default: .cache).
    """

    def __init__(self,
                 cache_dir: Optional[str] = None,
                 filename: str = "gmail_codes_cache.json",
                 ttl_minutes: Optional[int] = None,
                 enabled: Optional[bool] = None) -> None:
        self.cache_dir = cache_dir or os.getenv("GMAIL_CACHE_DIR", ".cache")
        self.filename = filename
        self.path = os.path.join(self.cache_dir, self.filename)
        self.ttl_minutes = ttl_minutes if ttl_minutes is not None else int(os.getenv("GMAIL_CACHE_TTL_MINUTES", "10"))
        self.enabled = enabled if enabled is not None else os.getenv("GMAIL_CACHE_ENABLED", "1") in ("1", "true", "True")

        # Ensure directory exists (best-effort)
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass

    def _now(self) -> datetime:
        return datetime.utcnow()

    def _hash_key(self, key: str) -> str:
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def _load_all(self) -> Dict[str, Any]:
        try:
            if not os.path.exists(self.path):
                return {}
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _save_all(self, data: Dict[str, Any]) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _is_fresh(self, created_at_iso: str) -> bool:
        try:
            created = datetime.fromisoformat(created_at_iso)
        except Exception:
            return False
        if self.ttl_minutes <= 0:
            return True
        return self._now() - created <= timedelta(minutes=self.ttl_minutes)

    def make_key(self, *, search_query: str, target_email: Optional[str]) -> str:
        base = f"q={search_query.strip()}|e={(target_email or '').strip().lower()}"
        return self._hash_key(base)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        data = self._load_all()
        entry = data.get(key)
        if not entry:
            return None
        created_at = entry.get("created_at")
        if not created_at or not self._is_fresh(created_at):
            return None
        return entry.get("payload")

    def set(self, key: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        data = self._load_all()
        data[key] = {
            "created_at": self._now().isoformat(),
            "payload": payload,
        }
        self._save_all(data)

    def purge(self) -> None:
        """Delete the entire Gmail cache file."""
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass
