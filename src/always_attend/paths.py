"""Default filesystem locations for Always Attend runtime files."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


APP_DIR_NAME = "always-attend"
CODES_DIR_NAME = "codes"


def _xdg_dir(env_name: str, fallback: Path) -> Path:
    raw = os.getenv(env_name, "").strip()
    if raw:
        return Path(raw).expanduser()
    return fallback


def _looks_absolute(raw: str, candidate: Path) -> bool:
    if candidate.is_absolute():
        return True
    return bool(re.match(r"^(?:[A-Za-z]:[\\/]|\\\\)", raw))


def _path_from_env(env_name: str, *, base_dir: Path | None = None) -> Path | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if base_dir is not None and not _looks_absolute(raw, candidate):
        return base_dir / candidate
    return candidate


def _repo_root_from_cwd() -> Path | None:
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists() and (cwd / "src").is_dir():
        return cwd
    return None


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _windows_roaming_appdata() -> Path:
    return _xdg_dir("APPDATA", Path.home() / "AppData" / "Roaming")


def _windows_local_appdata() -> Path:
    return _xdg_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local")


def _macos_app_support() -> Path:
    return Path.home() / "Library" / "Application Support"


def config_dir() -> Path:
    override = _path_from_env("ALWAYS_ATTEND_CONFIG_DIR")
    if override is not None:
        return override
    if _is_windows():
        return _windows_roaming_appdata() / APP_DIR_NAME / "config"
    if _is_macos():
        return _macos_app_support() / APP_DIR_NAME / "config"
    return _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config") / APP_DIR_NAME


def state_dir() -> Path:
    override = _path_from_env("ALWAYS_ATTEND_STATE_DIR")
    if override is not None:
        return override
    if _is_windows():
        return _windows_local_appdata() / APP_DIR_NAME / "state"
    if _is_macos():
        return _macos_app_support() / APP_DIR_NAME / "state"
    return _xdg_dir("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP_DIR_NAME


def data_dir() -> Path:
    override = _path_from_env("ALWAYS_ATTEND_DATA_DIR")
    if override is not None:
        return override
    if _is_windows():
        return _windows_local_appdata() / APP_DIR_NAME / "data"
    if _is_macos():
        return _macos_app_support() / APP_DIR_NAME / "data"
    return _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_DIR_NAME


def env_file() -> Path:
    explicit = _path_from_env("ENV_FILE")
    if explicit is not None:
        return explicit

    default_path = config_dir() / ".env"
    if default_path.exists():
        return default_path

    repo_root = _repo_root_from_cwd()
    if repo_root is not None:
        legacy_env = repo_root / ".env"
        if legacy_env.exists():
            return legacy_env

    return default_path


def env_template_file() -> Path | None:
    repo_root = _repo_root_from_cwd()
    if repo_root is None:
        return None
    candidate = repo_root / ".env.example"
    if candidate.exists():
        return candidate
    return None


def storage_state_file() -> Path:
    explicit = _path_from_env("STORAGE_STATE", base_dir=env_file().parent)
    if explicit is not None:
        return explicit
    return state_dir() / "storage_state.json"


def stats_file() -> Path:
    explicit = _path_from_env("ATTENDANCE_STATS_FILE", base_dir=env_file().parent)
    if explicit is not None:
        return explicit
    return state_dir() / "attendance_stats.json"


def codes_db_path() -> Path:
    explicit = _path_from_env("CODES_DB_PATH", base_dir=env_file().parent)
    if explicit is not None:
        return explicit
    return data_dir() / CODES_DIR_NAME


def user_data_dir() -> Path | None:
    explicit = _path_from_env("USER_DATA_DIR", base_dir=env_file().parent)
    if explicit is not None:
        return explicit
    return None


def log_file() -> Path | None:
    explicit = _path_from_env("LOG_FILE", base_dir=env_file().parent)
    if explicit is not None:
        return explicit
    return None


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def default_env_template() -> str:
    return """# =============================================================================
#                    Always Attend Configuration Template
# =============================================================================
#
# Default locations:
# - Linux: ~/.config/always-attend/.env, ~/.local/state/always-attend/, ~/.local/share/always-attend/data/
# - macOS: ~/Library/Application Support/always-attend/
# - Windows: %APPDATA%\\always-attend\\config and %LOCALAPPDATA%\\always-attend\\{state,data}
#

# Your university credentials
USERNAME=""
PASSWORD=""

# Portal URL (for example: https://attendance.monash.edu.my)
PORTAL_URL=""

# Optional: TOTP Secret for 2FA (Base32 encoded)
TOTP_SECRET=""

# Optional overrides. Leave blank to use the standard user directories above.
CODES_DB_PATH=""
CODES_DB_REPO=""
CODES_DB_BRANCH="main"
WEEK_NUMBER=""

# Browser settings
BROWSER="chromium"
BROWSER_CHANNEL="chrome"
HEADLESS="0"
STORAGE_STATE=""
USER_DATA_DIR=""
AUTO_LOGIN="1"
IMPORT_BROWSER_SESSION="1"
IMPORT_BROWSER_PROFILE=""

# Logging / behavior
LOG_PROFILE="user"
LOG_FILE=""
ATTENDANCE_STATS_FILE=""
DRY_RUN="0"
SKIP_SESSION_CHECK="0"

"""
