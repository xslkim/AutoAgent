"""Config file loader — ``~/.autoagent/config.toml``.

The config file is optional.  When absent, every setting falls back to its
built-in default.  Keys present in the file override defaults; CLI flags
override the file.

TOML layout::

    [server]
    host = "127.0.0.1"
    port = 27842
    engine = "unity"          # hint only, no wire effect

    [logging]
    file = "~/.autoagent/logs/mcp-server.log"
    level = "INFO"
    max_bytes = 10485760      # 10 MB
    backup_count = 5

Python 3.11+ ships ``tomllib`` in the standard library, so no third-party
dependency is required.

Usage::

    from autoagent_mcp.config import load_config
    cfg = load_config()               # reads DEFAULT_CONFIG_FILE if it exists
    cfg = load_config("/custom.toml") # explicit path
    print(cfg.server.host)            # "127.0.0.1"
    print(cfg.logging.level)          # "INFO"
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_DIR: Path = Path.home() / ".autoagent"
DEFAULT_CONFIG_FILE: Path = DEFAULT_CONFIG_DIR / "config.toml"


# ---------------------------------------------------------------------------
# Typed config sections
# ---------------------------------------------------------------------------


@dataclass
class ServerConfig:
    """``[server]`` section defaults."""

    host: str = "127.0.0.1"
    port: int = 27842
    engine: str = "unity"


@dataclass
class LoggingConfig:
    """``[logging]`` section defaults."""

    file: str = str(Path.home() / ".autoagent" / "logs" / "mcp-server.log")
    level: str = "INFO"
    max_bytes: int = 10 * 1024 * 1024   # 10 MB
    backup_count: int = 5


@dataclass
class Config:
    """Top-level configuration object returned by :func:`load_config`."""

    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    #: Path the config was loaded from (``None`` when using pure defaults).
    source: Path | None = field(default=None, compare=False, repr=False)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load configuration from a TOML file, falling back to built-in defaults.

    Args:
        path: Explicit path to a ``.toml`` file.  When ``None`` (default)
              ``~/.autoagent/config.toml`` is used if it exists; if the
              file is absent the function returns a :class:`Config` with
              all defaults.

    Returns:
        A fully-populated :class:`Config` instance.  Fields not present in
        the file retain their default values.

    Raises:
        tomllib.TOMLDecodeError: The file exists but contains invalid TOML.
        PermissionError: The file exists but cannot be read.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_FILE

    if not config_path.exists():
        return Config()

    with open(config_path, "rb") as fh:
        raw: dict = tomllib.load(fh)

    server_section = raw.get("server", {})
    logging_section = raw.get("logging", {})

    server = ServerConfig(
        host=server_section.get("host", ServerConfig.host),
        port=int(server_section.get("port", ServerConfig.port)),
        engine=server_section.get("engine", ServerConfig.engine),
    )

    default_log = LoggingConfig()
    logging_cfg = LoggingConfig(
        file=str(logging_section.get("file", default_log.file)),
        level=str(logging_section.get("level", default_log.level)).upper(),
        max_bytes=int(logging_section.get("max_bytes", default_log.max_bytes)),
        backup_count=int(logging_section.get("backup_count", default_log.backup_count)),
    )

    return Config(server=server, logging=logging_cfg, source=config_path)
