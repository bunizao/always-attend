"""Stable runtime contract for downstream integrations."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass

from always_attend import __version__
from always_attend.paths import (
    APP_DIR_NAME,
    codes_db_path,
    config_dir,
    data_dir,
    env_file,
    log_file,
    portal_state_file,
    setup_sentinel_file,
    state_dir,
    stats_file,
    storage_state_file,
    user_data_dir,
)
from utils.env_utils import load_env


RUNTIME_CONTRACT_VERSION = "2"


@dataclass(frozen=True)
class RuntimePaths:
    contract_version: str
    app_name: str
    package_version: str
    platform: str
    config_dir: str
    state_dir: str
    app_data_dir: str
    data_dir: str
    env_file: str
    setup_sentinel_file: str
    storage_state_file: str
    portal_state_file: str
    stats_file: str
    codes_db_path: str
    user_data_dir: str | None
    log_file: str | None


def get_runtime_paths() -> RuntimePaths:
    """Return the stable runtime file contract for this installation."""
    load_env(str(env_file()))

    resolved_user_data_dir = user_data_dir()
    resolved_log_file = log_file()

    return RuntimePaths(
        contract_version=RUNTIME_CONTRACT_VERSION,
        app_name=APP_DIR_NAME,
        package_version=__version__,
        platform=sys.platform,
        config_dir=str(config_dir()),
        state_dir=str(state_dir()),
        app_data_dir=str(data_dir()),
        data_dir=str(data_dir()),
        env_file=str(env_file()),
        setup_sentinel_file=str(setup_sentinel_file()),
        storage_state_file=str(storage_state_file()),
        portal_state_file=str(portal_state_file()),
        stats_file=str(stats_file()),
        codes_db_path=str(codes_db_path()),
        user_data_dir=(str(resolved_user_data_dir) if resolved_user_data_dir is not None else None),
        log_file=(str(resolved_log_file) if resolved_log_file is not None else None),
    )


def get_runtime_paths_dict() -> dict[str, str | None]:
    """Return the runtime contract as a plain dictionary."""
    return asdict(get_runtime_paths())


def get_runtime_paths_json() -> str:
    """Return the runtime contract as stable JSON."""
    return json.dumps(get_runtime_paths_dict(), indent=2, sort_keys=True)
