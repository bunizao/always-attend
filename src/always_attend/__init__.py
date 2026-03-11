"""Always Attend package entrypoints."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("always-attend")
except PackageNotFoundError:
    __version__ = "0.1.0"
