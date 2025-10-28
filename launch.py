#!/usr/bin/env python3
"""One-stop bootstrapper for the always-attend project."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict

REPO_URL = "https://github.com/bunizao/always-attend.git"
REPO_NAME = "always-attend"
BANNER = """\
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
═════════════════════════════════════════════════════
"""


class Palette:
    """ANSI palette for lightweight terminal styling."""

    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"
    blue = "\033[34m"
    cyan = "\033[36m"
    green = "\033[32m"
    magenta = "\033[35m"
    yellow = "\033[33m"
    red = "\033[31m"
    white = "\033[97m"
    monash = "\033[38;2;0;83;159m"

    @property
    def disabled(self) -> bool:
        return bool(os.getenv("NO_COLOR"))

    def apply(self, text: str, *styles: str) -> str:
        if self.disabled or not styles:
            return text
        return f"{''.join(styles)}{text}{self.reset}"


class LauncherConsole:
    """Minimal console helper with banner animation and colored output."""

    def __init__(self) -> None:
        self.palette = Palette()
        self.width = max(72, min(shutil.get_terminal_size((100, 20)).columns, 120))
        self.is_tty = sys.stdout.isatty()

    def clear(self) -> None:
        if self.is_tty and not self.palette.disabled:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
        else:
            print("\n" * 2)

    def _center(self, text: str) -> str:
        stripped = text.rstrip()
        pad = max(self.width - len(stripped), 0)
        left = pad // 2
        return f"{' ' * left}{stripped}"

    def _animate_intro(self) -> None:
        if not self.is_tty or self.palette.disabled:
            return
        frames = ["◐", "◓", "◑", "◒"]
        for _ in range(2):
            for frame in frames:
                line = self._center(f"always-attend {frame}")
                sys.stdout.write(self.palette.apply(line, self.palette.blue, self.palette.bold))
                sys.stdout.flush()
                time.sleep(0.08)
                sys.stdout.write("\r")
        sys.stdout.write(" " * self.width + "\r")
        sys.stdout.flush()

    def _rule(self, label: str = "", *, accent: str = "blue", char: str = "═") -> str:
        text = f" {label} " if label else ""
        pad = max(self.width - len(text), 0)
        left = pad // 2
        right = pad - left
        raw = f"{char * left}{text}{char * right}"
        color = getattr(self.palette, accent, "")
        return self.palette.apply(raw[: self.width], color, self.palette.bold)

    def banner(self, subtitle: str | None = None) -> None:
        self._animate_intro()
        color = getattr(self.palette, "monash", self.palette.blue)
        for line in BANNER.strip("\n").splitlines():
            print(self.palette.apply(self._center(line), color, self.palette.bold))
        if subtitle:
            print(self._rule(subtitle))

    def info(self, message: str) -> None:
        print(self.palette.apply(message, self.palette.white))

    def note(self, message: str) -> None:
        print(self.palette.apply(message, self.palette.cyan))

    def step(self, message: str) -> None:
        bullet = self.palette.apply("•", self.palette.magenta, self.palette.bold)
        print(f"{bullet} {message}")

    def success(self, message: str) -> None:
        print(self.palette.apply(message, self.palette.green, self.palette.bold))

    def warning(self, message: str) -> None:
        print(self.palette.apply(message, self.palette.yellow))

    def error(self, message: str) -> None:
        print(self.palette.apply(message, self.palette.red, self.palette.bold))

    def prompt(self, message: str, *, default: str | None = None) -> str:
        suffix = ""
        if default is not None and default != "":
            suffix = f" [{default}]"
        arrow = self.palette.apply("➜", self.palette.green, self.palette.bold)
        prompt_text = f"{arrow} {message}{suffix}: "
        try:
            response = input(prompt_text)
        except EOFError:
            return default or ""
        response = response.strip()
        if not response and default is not None:
            return default
        return response

    def confirm(self, message: str, *, default: bool = True) -> bool:
        yes_no = "Y/n" if default else "y/N"
        response = self.prompt(f"{message} [{yes_no}]", default="")
        if not response:
            return default
        return response.lower() in ("y", "yes")

    def command(self, cwd: Path, cmd: list[str]) -> None:
        chevron = self.palette.apply("▶", self.palette.blue, self.palette.bold)
        location = self.palette.apply(str(cwd), self.palette.dim)
        command = " ".join(cmd)
        styled = self.palette.apply(command, self.palette.blue)
        print(f"\n{chevron} {location}")
        print(f"   {styled}")


console = LauncherConsole()


def ask_for_directory() -> Path:
    """Ask the user where the repository should be located."""
    cwd = Path.cwd()
    console.info("The repository will be cloned relative to the current directory.")
    console.note(f"Current working directory: {cwd}")
    chosen = console.prompt("Press Enter to use this directory or type another path", default="")
    if not chosen:
        target = cwd
    else:
        target = Path(chosen).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
    console.success(f"Repository destination: {target}")
    return target


def run_command(cmd: list[str], cwd: Path | None = None, env: Dict[str, str] | None = None) -> None:
    """Run a shell command and stream its output."""
    display_path = cwd if cwd else Path.cwd()
    console.command(display_path, cmd)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def git_env() -> Dict[str, str]:
    """Return a Git-safe environment that ignores global overrides."""
    env = os.environ.copy()
    env.setdefault("GIT_CONFIG_GLOBAL", os.devnull)
    return env


def ensure_repo(target_dir: Path) -> Path:
    """Clone the repository or update it if already present."""
    if (target_dir / ".git").is_dir():
        repo_path = target_dir
    else:
        repo_path = target_dir / REPO_NAME

    if repo_path.exists() and (repo_path / ".git").is_dir():
        console.step(f"Detected existing repository at {repo_path}")
        if console.confirm("Pull the latest changes?", default=True):
            run_command(["git", "pull", "--ff-only"], cwd=repo_path, env=git_env())
        else:
            console.warning("Skipping git pull; continuing with local state.")
    elif repo_path.exists():
        console.error(f"Path {repo_path} exists but is not a Git repository.")
        raise SystemExit("Choose another destination and re-run the launcher.")
    else:
        console.step(f"Cloning repository into {target_dir}")
        run_command(["git", "clone", REPO_URL], cwd=target_dir, env=git_env())
    return repo_path


def ensure_virtualenv(repo_path: Path) -> Path:
    """Create the virtual environment and install dependencies."""
    venv_dir = repo_path / ".venv"
    if not venv_dir.exists():
        console.step("Creating virtual environment (.venv)")
        run_command([sys.executable, "-m", "venv", str(venv_dir)], cwd=repo_path)
    else:
        console.note(f"Using existing virtual environment at {venv_dir}")

    python_bin = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    pip_bin = python_bin.with_name("pip.exe" if os.name == "nt" else "pip")

    console.step("Upgrading pip")
    run_command([str(pip_bin), "install", "-U", "pip"], cwd=repo_path)
    console.step("Installing Python requirements")
    run_command([str(pip_bin), "install", "-r", "requirements.txt"], cwd=repo_path)
    console.step("Installing Playwright browser runtime (chromium)")
    run_command([str(python_bin), "-m", "playwright", "install", "chromium"], cwd=repo_path)
    return python_bin


def ensure_env_file(repo_path: Path) -> None:
    """Copy .env.example to .env if needed."""
    env_path = repo_path / ".env"
    example_path = repo_path / ".env.example"
    if env_path.exists():
        console.note(".env already exists; leaving it untouched.")
        return
    if example_path.exists():
        shutil.copy(example_path, env_path)
        console.success("Created .env from template. Update it with your credentials before running main.py.")
    else:
        console.warning("Missing .env.example. Create .env manually before launching the app.")


def choose_launch_mode() -> tuple[Dict[str, str], list[str]]:
    """Ask the user how they want to run main.py."""
    console.step("Select a launch mode:")
    console.info("1. Visible UI for interactive login (HEADLESS=0 INTERACTIVE_LOGIN=1 LOGIN_ONLY=1)")
    console.info("2. Default mode run (headless session check)")
    console.info("3. Dry-run mode (main.py --dry-run)")
    choice = console.prompt("Enter option number", default="1")
    env: Dict[str, str] = {}
    args: list[str] = []
    if choice == "3":
        args.append("--dry-run")
    elif choice != "2":
        env.update({
            "HEADLESS": "0",
            "INTERACTIVE_LOGIN": "1",
            "LOGIN_ONLY": "1",
        })
    return env, args


def confirm_launch() -> bool:
    """Ask whether main.py should be launched immediately."""
    return console.confirm("Run main.py now?", default=True)


def run_main(repo_path: Path, python_bin: Path, extra_env: Dict[str, str], extra_args: list[str]) -> None:
    """Run main.py with the chosen environment."""
    env = os.environ.copy()
    env.update(extra_env)
    console.step("Launching main.py")
    run_command([str(python_bin), "main.py", *extra_args], cwd=repo_path, env=env)


def main() -> None:
    """Entrypoint for the automation script."""
    console.clear()
    console.banner("Setup Helper")
    console.info("Welcome to the always-attend setup helper.")
    console.info("This script clones the repository, prepares the virtual environment,")
    console.info("and optionally launches main.py for you.")

    target_dir = ask_for_directory()
    repo_path = ensure_repo(target_dir)
    python_bin = ensure_virtualenv(repo_path)
    ensure_env_file(repo_path)
    env, args = choose_launch_mode()
    if confirm_launch():
        run_main(repo_path, python_bin, env, args)
    else:
        console.note("Environment ready. Launch manually with the command below when convenient:")
        env_parts = " ".join(f"{key}={value}" for key, value in env.items())
        env_prefix = f"{env_parts} " if env_parts else ""
        extra = " ".join(args)
        arg_suffix = f" {extra}" if extra else ""
        console.success(f"{env_prefix}{python_bin} main.py{arg_suffix}")
        console.note(f"(working directory: {repo_path})")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        console.error(f"Command failed with exit code {exc.returncode}. Check the logs above for details.")
        sys.exit(exc.returncode)
    except KeyboardInterrupt:
        console.warning("Interrupted by user. Goodbye!")
        sys.exit(1)
