"""Always Attend package entrypoints."""

from pathlib import Path
import tomllib
from importlib.metadata import PackageNotFoundError, version


def _version_from_repo_pyproject() -> str | None:
    """Return the source-tree version when running directly from the repo."""
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    try:
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return None
    package_version = project.get("version")
    return str(package_version).strip() if package_version else None


_repo_version = _version_from_repo_pyproject()
if _repo_version:
    __version__ = _repo_version
else:
    try:
        __version__ = version("always-attend")
    except PackageNotFoundError:
        __version__ = "0.2.0a0"

from always_attend.runtime_contract import (  # noqa: E402
    RUNTIME_CONTRACT_VERSION,
    RuntimePaths,
    get_runtime_paths,
    get_runtime_paths_dict,
    get_runtime_paths_json,
)

__all__ = [
    "__version__",
    "RUNTIME_CONTRACT_VERSION",
    "RuntimePaths",
    "get_runtime_paths",
    "get_runtime_paths_dict",
    "get_runtime_paths_json",
]
