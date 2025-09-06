import os
from typing import Optional

def load_env(path: str = ".env") -> None:
    """Minimal .env loader to populate env defaults (no overrides)."""
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
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


def ensure_env_file(env_file: str = ".env", template: str = ".env.example") -> None:
    """Ensure `.env` exists; copy from example or create minimal fallback."""
    if os.path.exists(env_file):
        return
    try:
        if template and os.path.exists(template):
            import shutil
            shutil.copy2(template, env_file)
        else:
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write("# Always Attend Configuration\n")
    except Exception:
        # Last resort minimal file
        try:
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write("# Always Attend Configuration\n")
        except Exception:
            pass


def append_to_env_file(env_file: str, key: str, value: str) -> None:
    """Append or update a KEY="value" entry in `.env`. Best effort, idempotent."""
    try:
        lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
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

        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception:
        pass


def save_email_to_env(email: str, env_file: Optional[str] = None) -> None:
    """Convenience wrapper to persist SCHOOL_EMAIL to `.env`."""
    path = env_file or os.getenv('ENV_FILE', '.env')
    ensure_env_file(path)
    append_to_env_file(path, 'SCHOOL_EMAIL', email)
