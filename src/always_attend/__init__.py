"""Always Attend package entrypoints."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("always-attend")
except PackageNotFoundError:
    __version__ = "0.1.2"

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
