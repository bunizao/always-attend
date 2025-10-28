"""
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝

 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
src/utils/browser_detection.py
Helper utilities to locate system browser executables.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional


_CHANNEL_KEY_OVERRIDES = {
    "chrome": ("BROWSER_EXECUTABLE", "CHROME_PATH", "GOOGLE_CHROME_SHIM"),
    "chrome-beta": ("BROWSER_EXECUTABLE", "CHROME_BETA_PATH"),
    "chrome-canary": ("BROWSER_EXECUTABLE", "CHROME_CANARY_PATH"),
    "msedge": ("BROWSER_EXECUTABLE", "EDGE_PATH", "MSEDGE_PATH"),
    "msedge-beta": ("BROWSER_EXECUTABLE", "MSEDGE_BETA_PATH"),
}


def _resolve_env_override(channel: str) -> Optional[Path]:
    keys: Iterable[str] = _CHANNEL_KEY_OVERRIDES.get(channel, ("BROWSER_EXECUTABLE",))
    for key in keys:
        value = os.getenv(key)
        if value:
            candidate = Path(value).expanduser()
            if candidate.exists():
                return candidate
    return None


def _mac_bundle_candidates(channel: str) -> List[Path]:
    bundle_map = {
        "chrome": ("Google Chrome",),
        "chrome-beta": ("Google Chrome Beta",),
        "chrome-canary": ("Google Chrome Canary",),
        "msedge": ("Microsoft Edge",),
        "msedge-beta": ("Microsoft Edge Beta",),
    }
    bundles = bundle_map.get(channel, ())
    candidates: List[Path] = []
    for bundle in bundles:
        bundle_path = f"{bundle}.app/Contents/MacOS/{bundle}"
        candidates.append(Path("/Applications") / bundle_path)
        candidates.append(Path.home() / "Applications" / bundle_path)
    return candidates


def _windows_candidates(channel: str) -> List[Path]:
    suffix_map = {
        "chrome": ("Google/Chrome/Application/chrome.exe",),
        "chrome-beta": ("Google/Chrome Beta/Application/chrome.exe",),
        "chrome-canary": ("Google/Chrome SxS/Application/chrome.exe",),
        "msedge": ("Microsoft/Edge/Application/msedge.exe",),
        "msedge-beta": ("Microsoft/Edge Beta/Application/msedge.exe",),
    }
    suffixes = suffix_map.get(channel, ())
    roots: List[Path] = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        value = os.getenv(key)
        if value:
            roots.append(Path(value))
    candidates: List[Path] = []
    for root in roots:
        for suffix in suffixes:
            candidates.append(root / suffix)
    return candidates


def _linux_candidates(channel: str) -> List[Path]:
    bin_map = {
        "chrome": (
            "google-chrome",
            "google-chrome-stable",
            "chromium-browser",
            "chromium",
        ),
        "chrome-beta": ("google-chrome-beta",),
        "chrome-canary": ("google-chrome-unstable", "google-chrome-dev"),
        "msedge": ("microsoft-edge", "microsoft-edge-stable"),
        "msedge-beta": ("microsoft-edge-beta",),
    }
    bins = bin_map.get(channel, ())
    candidates: List[Path] = []
    for binary in bins:
        resolved = shutil.which(binary)
        if resolved:
            candidates.append(Path(resolved))
    return candidates


def _collect_candidates(channel: str) -> List[Path]:
    system = platform.system().lower()
    if system == "darwin":
        return _mac_bundle_candidates(channel)
    if system == "windows":
        return _windows_candidates(channel)
    return _linux_candidates(channel)


def _is_executable(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        return False
    if os.access(path, os.X_OK):
        return True
    # On Windows os.X_OK may be False for .exe even when runnable; rely on suffix.
    return path.suffix.lower() in (".exe", ".bat", ".cmd")


def _verify_launch(executable: Path) -> bool:
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception:
        return False
    return result.returncode == 0


@lru_cache(maxsize=None)
def find_system_browser(channel: str = "chrome") -> Optional[Path]:
    """Return the executable path for the requested browser channel if available."""
    normalized = (channel or "").strip().lower()
    if not normalized:
        return None

    override = _resolve_env_override(normalized)
    if override and _is_executable(override):
        return override

    for candidate in _collect_candidates(normalized):
        if _is_executable(candidate):
            return candidate
    return None


@lru_cache(maxsize=None)
def is_browser_channel_available(channel: str = "chrome") -> bool:
    """Check whether a system browser for the given channel can be launched."""
    executable = find_system_browser(channel)
    if not executable:
        return False
    return _verify_launch(executable)
