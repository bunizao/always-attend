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
src/utils/bootstrap.py
Environment bootstrap helpers for Always Attend.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from utils.browser_detection import is_browser_channel_available


class BootstrapError(RuntimeError):
    pass


def _venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _in_target_venv(venv_path: Path) -> bool:
    if not venv_path.exists():
        return False
    current_prefix = Path(sys.prefix).resolve()
    target_prefix = venv_path.resolve()
    if current_prefix == target_prefix:
        return True
    venv_env = os.environ.get("VIRTUAL_ENV")
    if venv_env and Path(venv_env).resolve() == target_prefix:
        return True
    return False


def _run(cmd: Iterable[str], cwd: Path) -> None:
    result = subprocess.run(list(cmd), cwd=str(cwd))
    if result.returncode != 0:
        raise BootstrapError("Command failed: {}".format(" ".join(map(str, cmd))))


def _ensure_venv(project_root: Path) -> None:
    venv_path = project_root / ".venv"
    if venv_path.exists():
        return
    _run([sys.executable, "-m", "venv", str(venv_path)], project_root)


def _ensure_dependencies(project_root: Path) -> None:
    venv_path = project_root / ".venv"
    python_exe = _venv_python(venv_path)
    if not python_exe.exists():
        raise BootstrapError("Virtual environment interpreter missing at {}".format(python_exe))

    required_modules = ("playwright", "pyotp", "aiohttp", "rich")
    flag_path = venv_path / "requirements_installed.flag"

    missing_modules = [mod for mod in required_modules if importlib.util.find_spec(mod) is None]

    if missing_modules or not flag_path.exists():
        if missing_modules:
            _run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], project_root)
            req_file = project_root / "requirements.txt"
            _run([str(python_exe), "-m", "pip", "install", "-r", str(req_file)], project_root)
        flag_path.touch()


def _ensure_playwright_assets(project_root: Path) -> None:
    venv_path = project_root / ".venv"
    python_exe = _venv_python(venv_path)
    if not python_exe.exists():
        raise BootstrapError("Virtual environment interpreter missing at {}".format(python_exe))

    flag_path = venv_path / "playwright_chromium_installed.flag"
    if flag_path.exists():
        return
    preferred_channel = os.getenv("BROWSER_CHANNEL", "chrome").lower()
    if preferred_channel in {"chrome", "chrome-beta", "chrome-canary", "msedge", "msedge-beta"}:
        if is_browser_channel_available(preferred_channel):
            return
    _run([str(python_exe), "-m", "playwright", "install", "chromium"], project_root)
    flag_path.touch()


def ensure_runtime_ready(project_root: Path) -> None:
    project_root = project_root.resolve()
    _ensure_venv(project_root)

    venv_path = project_root / ".venv"
    if not _in_target_venv(venv_path):
        python_exe = _venv_python(venv_path)
        if not python_exe.exists():
            raise BootstrapError("Virtual environment interpreter missing at {}".format(python_exe))
        os.execv(str(python_exe), [str(python_exe), str(project_root / "main.py"), *sys.argv[1:]])

    _ensure_dependencies(project_root)
    _ensure_playwright_assets(project_root)
