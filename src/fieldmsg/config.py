"""Configuration loading for fieldmsg."""

import os
import sys
from dataclasses import dataclass, field

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class Config:
    """fieldmsg configuration with sensible defaults."""

    display_name: str = "fieldmsg"
    propagation_node: str = ""
    sync_interval: int = 300
    announce_at_start: bool = True
    announce_interval: int = 600
    db_path: str = "~/.fieldmsg/messages.db"
    max_age_days: int = 90

    # Runtime-only fields (not loaded from file)
    config_path: str | None = None
    rns_config_dir: str | None = None

    @property
    def fieldmsg_dir(self) -> str:
        """Return expanded path to ~/.fieldmsg directory."""
        return os.path.expanduser("~/.fieldmsg")

    @property
    def identity_path(self) -> str:
        """Return expanded path to the identity file."""
        return os.path.join(self.fieldmsg_dir, "identity")

    @property
    def storage_path(self) -> str:
        """Return expanded path to the storage directory."""
        return os.path.join(self.fieldmsg_dir, "storage")

    def resolve_db_path(self) -> str:
        """Return the db_path with ~ expanded."""
        return os.path.expanduser(self.db_path)


def load_config(path: str | None = None) -> Config:
    """Load configuration from a TOML file, falling back to defaults.

    If *path* is None or the file does not exist, a default Config is
    returned.  Any keys present in the TOML override the corresponding
    defaults; missing keys keep their default values.
    """
    if path is None:
        return Config()

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return Config()

    identity = data.get("identity", {})
    lxmf = data.get("lxmf", {})
    storage = data.get("storage", {})

    kwargs: dict = {}

    if "display_name" in identity:
        kwargs["display_name"] = identity["display_name"]
    if "propagation_node" in lxmf:
        kwargs["propagation_node"] = lxmf["propagation_node"]
    if "sync_interval" in lxmf:
        kwargs["sync_interval"] = lxmf["sync_interval"]
    if "announce_at_start" in lxmf:
        kwargs["announce_at_start"] = lxmf["announce_at_start"]
    if "announce_interval" in lxmf:
        kwargs["announce_interval"] = lxmf["announce_interval"]
    if "db_path" in storage:
        kwargs["db_path"] = storage["db_path"]
    if "max_age_days" in storage:
        kwargs["max_age_days"] = storage["max_age_days"]

    kwargs["config_path"] = path

    return Config(**kwargs)


def generate_example_config() -> str:
    """Return an example TOML configuration as a string."""
    return """\
[identity]
display_name = "Field Unit Alpha"
# identity is auto-generated on first run and stored at ~/.fieldmsg/identity

[lxmf]
propagation_node = ""       # destination hash of preferred propagation node
sync_interval = 300         # seconds between propagation syncs
announce_at_start = true    # announce on startup
announce_interval = 600     # periodic re-announce interval, 0 to disable

[storage]
db_path = "~/.fieldmsg/messages.db"
max_age_days = 90           # auto-cleanup old messages, 0 to disable
"""
