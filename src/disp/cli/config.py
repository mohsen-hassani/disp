import stat
import tomllib
from pathlib import Path
from typing import Any

import platformdirs
import tomli_w

from disp.cli.client import ConfigCliError

CONFIG_DIR_NAME = "disp"
CONFIG_FILE_NAME = "config.toml"
DEFAULT_PROFILE = "default"


def config_path() -> Path:
    return Path(platformdirs.user_config_dir(CONFIG_DIR_NAME)) / CONFIG_FILE_NAME


def _check_permissions(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigCliError(
            f"Config file {path} is group- or world-readable. Run: chmod 600 {path}"
        )


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {"default_profile": DEFAULT_PROFILE, "profiles": {}}
    _check_permissions(path)
    with path.open("rb") as f:
        data = tomllib.load(f)
    data.setdefault("default_profile", DEFAULT_PROFILE)
    data.setdefault("profiles", {})
    return data


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump(data, f)
    path.chmod(0o600)


def default_profile_name() -> str:
    return str(load_config().get("default_profile", DEFAULT_PROFILE))


def get_profile(profile_name: str) -> dict[str, Any] | None:
    profile = load_config().get("profiles", {}).get(profile_name)
    return dict(profile) if profile else None


def set_profile(profile_name: str, *, server: str, token: str, email: str) -> None:
    data = load_config()
    data["profiles"][profile_name] = {"server": server, "token": token, "email": email}
    save_config(data)


def remove_profile(profile_name: str) -> None:
    data = load_config()
    data.get("profiles", {}).pop(profile_name, None)
    save_config(data)
