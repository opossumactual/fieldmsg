"""Tests for fieldmsg.config module."""

import os
import textwrap
from pathlib import Path

import pytest

from fieldmsg.config import Config, generate_example_config, load_config


class TestConfigDefaults:
    """Default config values are sensible."""

    def test_display_name(self):
        cfg = Config()
        assert cfg.display_name == "fieldmsg"

    def test_propagation_node(self):
        cfg = Config()
        assert cfg.propagation_node == ""

    def test_sync_interval(self):
        cfg = Config()
        assert cfg.sync_interval == 300

    def test_announce_at_start(self):
        cfg = Config()
        assert cfg.announce_at_start is True

    def test_announce_interval(self):
        cfg = Config()
        assert cfg.announce_interval == 600

    def test_db_path(self):
        cfg = Config()
        assert cfg.db_path == "~/.fieldmsg/messages.db"

    def test_max_age_days(self):
        cfg = Config()
        assert cfg.max_age_days == 90

    def test_config_path_is_none(self):
        cfg = Config()
        assert cfg.config_path is None

    def test_rns_config_dir_is_none(self):
        cfg = Config()
        assert cfg.rns_config_dir is None


class TestConfigProperties:
    """Properties expand paths correctly."""

    def test_fieldmsg_dir(self):
        cfg = Config()
        expected = os.path.expanduser("~/.fieldmsg")
        assert cfg.fieldmsg_dir == expected

    def test_identity_path(self):
        cfg = Config()
        expected = os.path.expanduser("~/.fieldmsg/identity")
        assert cfg.identity_path == expected

    def test_storage_path(self):
        cfg = Config()
        expected = os.path.expanduser("~/.fieldmsg/storage")
        assert cfg.storage_path == expected

    def test_resolve_db_path_default(self):
        cfg = Config()
        expected = os.path.expanduser("~/.fieldmsg/messages.db")
        assert cfg.resolve_db_path() == expected

    def test_resolve_db_path_custom(self):
        cfg = Config(db_path="~/custom/path.db")
        expected = os.path.expanduser("~/custom/path.db")
        assert cfg.resolve_db_path() == expected

    def test_resolve_db_path_absolute(self):
        cfg = Config(db_path="/tmp/test.db")
        assert cfg.resolve_db_path() == "/tmp/test.db"


class TestLoadConfig:
    """load_config reads TOML and merges with defaults."""

    def test_missing_file_returns_defaults(self, tmp_path):
        cfg = load_config(str(tmp_path / "nonexistent.toml"))
        assert cfg.display_name == "fieldmsg"
        assert cfg.sync_interval == 300

    def test_load_overrides_specific_values(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(textwrap.dedent("""\
            [identity]
            display_name = "My Node"

            [lxmf]
            sync_interval = 120
        """))
        cfg = load_config(str(config_file))
        # Overridden values
        assert cfg.display_name == "My Node"
        assert cfg.sync_interval == 120
        # Defaults preserved
        assert cfg.propagation_node == ""
        assert cfg.announce_at_start is True
        assert cfg.announce_interval == 600
        assert cfg.db_path == "~/.fieldmsg/messages.db"
        assert cfg.max_age_days == 90

    def test_load_sets_config_path(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("[identity]\n")
        cfg = load_config(str(config_file))
        assert cfg.config_path == str(config_file)

    def test_load_none_path_returns_defaults(self):
        """Passing None returns defaults (no file to load)."""
        cfg = load_config(None)
        assert cfg.display_name == "fieldmsg"

    def test_load_all_sections(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(textwrap.dedent("""\
            [identity]
            display_name = "Test"

            [lxmf]
            propagation_node = "abc123"
            sync_interval = 60
            announce_at_start = false
            announce_interval = 0

            [storage]
            db_path = "/data/msgs.db"
            max_age_days = 30
        """))
        cfg = load_config(str(config_file))
        assert cfg.display_name == "Test"
        assert cfg.propagation_node == "abc123"
        assert cfg.sync_interval == 60
        assert cfg.announce_at_start is False
        assert cfg.announce_interval == 0
        assert cfg.db_path == "/data/msgs.db"
        assert cfg.max_age_days == 30


class TestGenerateExampleConfig:
    """generate_example_config returns valid example text."""

    def test_returns_string(self):
        result = generate_example_config()
        assert isinstance(result, str)

    def test_contains_identity_section(self):
        result = generate_example_config()
        assert "[identity]" in result

    def test_contains_lxmf_section(self):
        result = generate_example_config()
        assert "[lxmf]" in result

    def test_contains_storage_section(self):
        result = generate_example_config()
        assert "[storage]" in result

    def test_contains_display_name(self):
        result = generate_example_config()
        assert "display_name" in result

    def test_contains_propagation_node(self):
        result = generate_example_config()
        assert "propagation_node" in result

    def test_contains_sync_interval(self):
        result = generate_example_config()
        assert "sync_interval" in result

    def test_not_empty(self):
        result = generate_example_config()
        assert len(result.strip()) > 50
