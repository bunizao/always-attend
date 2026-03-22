"""Export bundled skills and sync them into agent skill directories via symlinks."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BundledSkill:
    """Static metadata for a bundled skill."""

    name: str
    description: str
    resource_path: tuple[str, ...]


BUNDLED_SKILLS: tuple[BundledSkill, ...] = (
    BundledSkill(
        name="attend-agent-workflow",
        description=(
            "Use attend as the execution tool and the model as the multimodal analyst "
            "for attendance handoff and submission."
        ),
        resource_path=("skills", "SKILL.md"),
    ),
)

KNOWN_AGENT_SKILL_DIRS: tuple[tuple[str, str], ...] = (
    ("agents", "~/.agents/skills"),
    ("claude", "~/.claude/skills"),
    ("codex", "~/.codex/skills"),
    ("copilot", "~/.copilot/skills"),
    ("cursor", "~/.cursor/skills"),
    ("gemini", "~/.gemini/skills"),
    ("gemini-antigravity", "~/.gemini/antigravity/skills"),
    ("qwen", "~/.qwen/skills"),
)


class SkillInstallError(RuntimeError):
    """Raised when a bundled skill cannot be installed."""


def default_skills_dir() -> Path:
    """Return the neutral default directory for exported skills."""
    override = os.environ.get("ATTEND_SKILLS_DIR")
    if override:
        return Path(override).expanduser()

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "always-attend" / "skills"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "always-attend" / "skills"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata).expanduser() if appdata else (Path.home() / "AppData" / "Roaming")
        return base / "always-attend" / "skills"
    return Path.home() / ".local" / "share" / "always-attend" / "skills"


def discover_agent_skill_dirs() -> list[dict[str, str]]:
    """Return known agent skill directories that already exist on disk."""
    discovered: list[dict[str, str]] = []
    for agent, raw_path in KNOWN_AGENT_SKILL_DIRS:
        path = Path(raw_path).expanduser()
        if path.is_dir():
            discovered.append({"agent": agent, "path": str(path)})
    return discovered


def list_bundled_skills(*, skills_dir: Path | None = None) -> list[dict[str, str | bool]]:
    """List bundled skills and whether they are already installed."""
    root = (skills_dir or default_skills_dir()).expanduser()
    items: list[dict[str, str | bool]] = []
    for skill in BUNDLED_SKILLS:
        destination = root / skill.name
        items.append(
            {
                "name": skill.name,
                "description": skill.description,
                "installed": destination.exists(),
                "destination": str(destination),
            }
        )
    return items


def install_bundled_skills(
    *,
    requested_names: Iterable[str] | None = None,
    skills_dir: Path | None = None,
    force: bool = False,
) -> list[Path]:
    """Install one or more bundled skills into the export directory."""
    requested = [name.strip() for name in (requested_names or []) if name and name.strip()]
    selected = requested or [skill.name for skill in BUNDLED_SKILLS]
    known = {skill.name for skill in BUNDLED_SKILLS}
    unknown = [name for name in selected if name not in known]
    if unknown:
        raise SkillInstallError(f"Unknown bundled skill(s): {', '.join(sorted(unknown))}")

    destination_root = (skills_dir or default_skills_dir()).expanduser()
    destination_root.mkdir(parents=True, exist_ok=True)

    installed_paths: list[Path] = []
    bundled_by_name = {skill.name: skill for skill in BUNDLED_SKILLS}
    for name in selected:
        bundled_skill = bundled_by_name[name]
        source_root = resources.files("always_attend")
        for part in bundled_skill.resource_path:
            source_root = source_root.joinpath(part)
        if not source_root.exists():
            raise SkillInstallError(f"Bundled skill payload is missing: {name}")

        destination = destination_root / name
        if destination.exists():
            if not force:
                raise SkillInstallError(
                    f"Skill already exists at {destination}. Use --force to overwrite."
                )
            _remove_path(destination)

        _copy_skill_payload(source_root, destination)
        installed_paths.append(destination)

    return installed_paths


def sync_skill_symlinks(
    installed_paths: Iterable[Path],
    *,
    agent_skill_dirs: Iterable[Path] | None = None,
    force: bool = False,
) -> list[dict[str, str]]:
    """Sync installed skills into agent skill directories via symlinks."""
    if agent_skill_dirs is None:
        targets = [Path(item["path"]) for item in discover_agent_skill_dirs()]
    else:
        targets = [Path(path).expanduser() for path in agent_skill_dirs]

    results: list[dict[str, str]] = []
    for installed_path in installed_paths:
        source = installed_path.resolve()
        for skills_dir in targets:
            skills_dir = skills_dir.expanduser()
            destination = skills_dir / installed_path.name

            if destination == installed_path:
                results.append(
                    {
                        "agent": _agent_name_for_dir(skills_dir),
                        "path": str(destination),
                        "status": "source",
                    }
                )
                continue

            skills_dir.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                if destination.is_symlink() and destination.resolve() == source:
                    results.append(
                        {
                            "agent": _agent_name_for_dir(skills_dir),
                            "path": str(destination),
                            "status": "already_linked",
                        }
                    )
                    continue
                if not force:
                    results.append(
                        {
                            "agent": _agent_name_for_dir(skills_dir),
                            "path": str(destination),
                            "status": "skipped_conflict",
                        }
                    )
                    continue
                _remove_path(destination)

            destination.symlink_to(source, target_is_directory=True)
            results.append(
                {
                    "agent": _agent_name_for_dir(skills_dir),
                    "path": str(destination),
                    "status": "linked",
                }
            )

    return results


def _copy_traversable_tree(source, destination: Path) -> None:
    """Copy an importlib Traversable directory tree into a filesystem path."""
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return

    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        _copy_traversable_tree(child, destination / child.name)


def _copy_skill_payload(source, destination: Path) -> None:
    """Copy a bundled skill file or directory into the installed skill directory."""
    if source.is_file():
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "SKILL.md").write_bytes(source.read_bytes())
        return
    _copy_traversable_tree(source, destination)


def _remove_path(path: Path) -> None:
    """Remove an existing file or directory."""
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def _agent_name_for_dir(path: Path) -> str:
    """Return a stable label for a discovered agent skills directory."""
    normalized = str(path.expanduser())
    for agent, raw_path in KNOWN_AGENT_SKILL_DIRS:
        if normalized == str(Path(raw_path).expanduser()):
            return agent
    return normalized
