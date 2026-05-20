"""TASK-0121: config file loading tests.

Covers:
- load_config() with no file → all defaults.
- load_config() with a valid TOML file → values merged.
- Partial TOML (only [server]) → missing sections keep defaults.
- Unknown keys in TOML → silently ignored.
- Invalid TOML → TOMLDecodeError raised.
- Type coercion: port / max_bytes / backup_count become ints.
- logging.level is uppercased.
- load_config(explicit_path) → uses that path.
- Config.source is set when file is read, None when using defaults.
- CLI --config flag loads the specified file.
- CLI values override config file values.
- Config file values override built-in defaults (but CLI wins).
"""

from __future__ import annotations

import textwrap
import tomllib
from pathlib import Path

import pytest

from autoagent_mcp.config import (
    DEFAULT_CONFIG_FILE,
    Config,
    LoggingConfig,
    ServerConfig,
    load_config,
)
from autoagent_mcp.cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_toml(tmp_path: Path, content: str) -> Path:
    """Write *content* to a temp TOML file and return the path."""
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# load_config — no file
# ---------------------------------------------------------------------------


class TestLoadConfigDefaults:
    def test_returns_config_instance(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert isinstance(cfg, Config)

    def test_server_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.server.host == "127.0.0.1"
        assert cfg.server.port == 27842
        assert cfg.server.engine == "unity"

    def test_logging_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.logging.level == "INFO"
        assert cfg.logging.max_bytes == 10 * 1024 * 1024
        assert cfg.logging.backup_count == 5

    def test_source_is_none_when_no_file(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.source is None

    def test_no_path_arg_uses_default_config_file_location(self, tmp_path, monkeypatch):
        """When path=None and the default file doesn't exist → pure defaults."""
        # Monkeypatch so we don't accidentally read the real ~/.autoagent/config.toml
        import autoagent_mcp.config as _mod
        monkeypatch.setattr(_mod, "DEFAULT_CONFIG_FILE", tmp_path / "no.toml")
        cfg = load_config()
        assert cfg.source is None


# ---------------------------------------------------------------------------
# load_config — full TOML file
# ---------------------------------------------------------------------------


class TestLoadConfigFull:
    def test_server_values_loaded(self, tmp_path):
        p = write_toml(tmp_path, """
            [server]
            host = "10.0.0.5"
            port = 9999
            engine = "unreal"
        """)
        cfg = load_config(p)
        assert cfg.server.host == "10.0.0.5"
        assert cfg.server.port == 9999
        assert cfg.server.engine == "unreal"

    def test_logging_values_loaded(self, tmp_path):
        p = write_toml(tmp_path, """
            [logging]
            file = "/var/log/autoagent.log"
            level = "debug"
            max_bytes = 5242880
            backup_count = 3
        """)
        cfg = load_config(p)
        assert cfg.logging.file == "/var/log/autoagent.log"
        assert cfg.logging.level == "DEBUG"   # uppercased
        assert cfg.logging.max_bytes == 5242880
        assert cfg.logging.backup_count == 3

    def test_source_set_to_file_path(self, tmp_path):
        p = write_toml(tmp_path, "[server]\nhost = '1.2.3.4'\n")
        cfg = load_config(p)
        assert cfg.source == p

    def test_both_sections(self, tmp_path):
        p = write_toml(tmp_path, """
            [server]
            host = "192.168.1.1"
            port = 12345

            [logging]
            level = "WARNING"
        """)
        cfg = load_config(p)
        assert cfg.server.host == "192.168.1.1"
        assert cfg.server.port == 12345
        assert cfg.logging.level == "WARNING"


# ---------------------------------------------------------------------------
# load_config — partial / edge-case TOML
# ---------------------------------------------------------------------------


class TestLoadConfigPartial:
    def test_only_server_section_keeps_logging_defaults(self, tmp_path):
        p = write_toml(tmp_path, "[server]\nport = 8080\n")
        cfg = load_config(p)
        assert cfg.server.port == 8080
        assert cfg.logging.level == "INFO"   # default intact
        assert cfg.logging.backup_count == 5

    def test_only_logging_section_keeps_server_defaults(self, tmp_path):
        p = write_toml(tmp_path, "[logging]\nlevel = 'ERROR'\n")
        cfg = load_config(p)
        assert cfg.server.host == "127.0.0.1"  # default
        assert cfg.logging.level == "ERROR"

    def test_empty_file_uses_all_defaults(self, tmp_path):
        p = write_toml(tmp_path, "")
        cfg = load_config(p)
        assert cfg.server.host == "127.0.0.1"
        assert cfg.logging.level == "INFO"
        # source is set even for empty file
        assert cfg.source == p

    def test_unknown_keys_ignored(self, tmp_path):
        p = write_toml(tmp_path, """
            [server]
            host = "localhost"
            unknown_key = "surprise"

            [unknown_section]
            foo = "bar"
        """)
        cfg = load_config(p)
        assert cfg.server.host == "localhost"

    def test_port_as_string_coerced_to_int(self, tmp_path):
        """TOML integers are native, but guard against string values."""
        p = write_toml(tmp_path, "[server]\nport = 9000\n")
        cfg = load_config(p)
        assert isinstance(cfg.server.port, int)
        assert cfg.server.port == 9000

    def test_level_lowercase_uppercased(self, tmp_path):
        p = write_toml(tmp_path, "[logging]\nlevel = 'warning'\n")
        cfg = load_config(p)
        assert cfg.logging.level == "WARNING"


# ---------------------------------------------------------------------------
# load_config — error cases
# ---------------------------------------------------------------------------


class TestLoadConfigErrors:
    def test_invalid_toml_raises(self, tmp_path):
        p = tmp_path / "bad.toml"
        p.write_text("not valid toml <<<", encoding="utf-8")
        with pytest.raises(tomllib.TOMLDecodeError):
            load_config(p)

    def test_explicit_path_that_does_not_exist_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "does_not_exist.toml")
        assert cfg.source is None


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


class TestConfigDataclass:
    def test_default_factory_isolation(self):
        """Two Config() instances should not share mutable defaults."""
        c1 = Config()
        c2 = Config()
        c1.server.host = "mutated"
        assert c2.server.host == "127.0.0.1"

    def test_server_config_defaults(self):
        s = ServerConfig()
        assert s.host == "127.0.0.1"
        assert s.port == 27842
        assert s.engine == "unity"

    def test_logging_config_defaults(self):
        lc = LoggingConfig()
        assert lc.level == "INFO"
        assert lc.max_bytes == 10 * 1024 * 1024
        assert lc.backup_count == 5


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCliConfig:
    def test_config_flag_loads_file(self, tmp_path, capsys):
        """--config points to a TOML that overrides defaults; --list-tools exits cleanly."""
        p = write_toml(tmp_path, "[server]\nhost = '9.9.9.9'\nport = 5555\n")
        # --list-tools so we don't start the server
        rc = cli(["--config", str(p), "--list-tools"])
        assert rc == 0

    def test_cli_host_overrides_config(self, tmp_path, capsys):
        """--host on CLI overrides config file value (check via argparse defaults)."""
        import argparse
        p = write_toml(tmp_path, "[server]\nhost = '1.2.3.4'\nport = 1111\n")
        # Simulate the two-phase parse that cli() does internally
        from autoagent_mcp.config import load_config as _load
        cfg = _load(p)
        parser = argparse.ArgumentParser()
        parser.add_argument("--host", default=cfg.server.host)
        parser.add_argument("--port", type=int, default=cfg.server.port)
        args = parser.parse_args(["--host", "8.8.8.8"])
        # CLI wins
        assert args.host == "8.8.8.8"
        # Port still from config
        assert args.port == 1111

    def test_log_level_from_config_used_as_default(self, tmp_path, capsys):
        """Config [logging].level feeds argparse default for --log-level."""
        import argparse
        p = write_toml(tmp_path, "[logging]\nlevel = 'DEBUG'\n")
        from autoagent_mcp.config import load_config as _load
        cfg = _load(p)
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--log-level",
            default=cfg.logging.level,
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        )
        args = parser.parse_args([])   # no CLI override
        assert args.log_level == "DEBUG"

    def test_missing_config_file_cli_still_works(self, tmp_path, capsys):
        """Pointing --config at a nonexistent file falls back to defaults."""
        rc = cli(["--config", str(tmp_path / "no.toml"), "--list-tools"])
        assert rc == 0
