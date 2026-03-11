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
src/utils/env_utils.py
Environment file and variable helpers for Always Attend.
"""

import os
from pathlib import Path
from typing import Optional

from always_attend.paths import default_env_template, ensure_parent, env_file as default_env_file, env_template_file


def load_env(path: Optional[str] = None) -> None:
    """Minimal .env loader to populate env defaults (no overrides)."""
    target = path or str(default_env_file())
    try:
        if not os.path.exists(target):
            return
        with open(target, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and (k not in os.environ):
                    os.environ[k] = v
    except Exception:
        pass


def ensure_env_file(env_file: Optional[str] = None, template: Optional[str] = None) -> None:
    """Ensure `.env` exists; copy from example or create minimal fallback."""
    target = Path(env_file).expanduser() if env_file is not None else default_env_file()
    if target.exists():
        return
    try:
        ensure_parent(target)
        template_path = template or (str(env_template_file()) if env_template_file() else None)
        if template_path and os.path.exists(template_path):
            import shutil
            shutil.copy2(template_path, target)
        else:
            with target.open('w', encoding='utf-8') as f:
                f.write(default_env_template())
    except Exception:
        # Last resort minimal file
        try:
            ensure_parent(target)
            with target.open('w', encoding='utf-8') as f:
                f.write(default_env_template())
        except Exception:
            pass


def append_to_env_file(env_file: str, key: str, value: str) -> None:
    """Append or update a KEY="value" entry in `.env`. Best effort, idempotent."""
    try:
        target = Path(env_file).expanduser()
        ensure_parent(target)
        lines = []
        if target.exists():
            with target.open('r', encoding='utf-8') as f:
                lines = f.readlines()

        key_exists = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f'{key}="{value}"\n'
                key_exists = True
                break

        if not key_exists:
            # insert a newline before appending for readability if file isn't empty
            if lines and lines[-1] and not lines[-1].endswith("\n"):
                lines[-1] = lines[-1] + "\n"
            lines.append(f'{key}="{value}"\n')

        with target.open('w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception:
        pass


def save_email_to_env(email: str, env_file: Optional[str] = None) -> None:
    """Convenience wrapper to persist SCHOOL_EMAIL to `.env`."""
    path = env_file or str(default_env_file())
    ensure_env_file(path)
    append_to_env_file(path, 'SCHOOL_EMAIL', email)
