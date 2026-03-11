"""System browser session import helpers for Always Attend."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserSessionSource:
    """Resolved browser profile metadata for session import."""

    channel: str
    user_data_dir: Path
    profile_name: str


_CHANNEL_USER_DATA_DIRS = {
    "darwin": {
        "chrome": "~/Library/Application Support/Google/Chrome",
        "chrome-beta": "~/Library/Application Support/Google/Chrome Beta",
        "chrome-canary": "~/Library/Application Support/Google/Chrome Canary",
        "msedge": "~/Library/Application Support/Microsoft Edge",
        "msedge-beta": "~/Library/Application Support/Microsoft Edge Beta",
    },
    "linux": {
        "chrome": "~/.config/google-chrome",
        "chrome-beta": "~/.config/google-chrome-beta",
        "chrome-canary": "~/.config/google-chrome-unstable",
        "msedge": "~/.config/microsoft-edge",
        "msedge-beta": "~/.config/microsoft-edge-beta",
    },
    "win32": {
        "chrome": "%LOCALAPPDATA%/Google/Chrome/User Data",
        "chrome-beta": "%LOCALAPPDATA%/Google/Chrome Beta/User Data",
        "chrome-canary": "%LOCALAPPDATA%/Google/Chrome SxS/User Data",
        "msedge": "%LOCALAPPDATA%/Microsoft/Edge/User Data",
        "msedge-beta": "%LOCALAPPDATA%/Microsoft/Edge Beta/User Data",
    },
}

_PROFILE_COPY_IGNORE = (
    "Cache",
    "Code Cache",
    "GPUCache",
    "GrShaderCache",
    "ShaderCache",
    "DawnCache",
    "Crashpad",
    "VideoDecodeStats",
)


def _platform_key() -> str:
    platform_name = os.sys.platform
    if platform_name.startswith("linux"):
        return "linux"
    if platform_name.startswith("win"):
        return "win32"
    return platform_name


def default_browser_user_data_dir(channel: str | None = None) -> Path | None:
    """Return the default user-data directory for the requested browser channel."""
    requested_channel = (channel or os.getenv("BROWSER_CHANNEL") or "chrome").strip().lower() or "chrome"
    override = os.getenv("IMPORT_BROWSER_USER_DATA_DIR")
    if override:
        return Path(os.path.expandvars(os.path.expanduser(override))).resolve()

    platform_dirs = _CHANNEL_USER_DATA_DIRS.get(_platform_key(), {})
    candidate = platform_dirs.get(requested_channel)
    if not candidate:
        return None
    return Path(os.path.expandvars(os.path.expanduser(candidate))).resolve()


def read_last_used_profile(user_data_dir: Path) -> str | None:
    """Read the last selected Chromium profile name from Local State."""
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        return None

    try:
        with local_state_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None

    profile = payload.get("profile") or {}
    last_used = profile.get("last_used")
    if isinstance(last_used, str) and last_used.strip():
        return last_used.strip()
    return None


def resolve_browser_session_source(channel: str | None = None) -> BrowserSessionSource | None:
    """Resolve a system browser profile that can be used for session import."""
    requested_channel = (channel or os.getenv("BROWSER_CHANNEL") or "chrome").strip().lower() or "chrome"
    user_data_dir = default_browser_user_data_dir(requested_channel)
    if user_data_dir is None or not user_data_dir.exists():
        return None

    profile_name = os.getenv("IMPORT_BROWSER_PROFILE") or read_last_used_profile(user_data_dir) or "Default"
    profile_name = profile_name.strip() or "Default"

    profile_dir = user_data_dir / profile_name
    if not profile_dir.exists():
        fallback_profile = user_data_dir / "Default"
        if not fallback_profile.exists():
            return None
        profile_name = "Default"

    return BrowserSessionSource(
        channel=requested_channel,
        user_data_dir=user_data_dir,
        profile_name=profile_name,
    )


def clone_browser_session_source(source: BrowserSessionSource, destination_root: Path) -> Path:
    """Copy the browser profile into a temporary directory for safe Playwright use."""
    destination_root.mkdir(parents=True, exist_ok=True)

    local_state = source.user_data_dir / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, destination_root / "Local State")

    shutil.copytree(
        source.user_data_dir / source.profile_name,
        destination_root / source.profile_name,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(*_PROFILE_COPY_IGNORE),
    )
    return destination_root
