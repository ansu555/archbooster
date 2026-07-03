"""Tests for config.toml parsing: defaults, and the snapshot/profiles/
automation sections added in Phase 6."""
import archbooster.core.config as cfgmod
from archbooster.core.config import Config, load_config


def _load(monkeypatch, tmp_path, toml_text: str | None = None) -> Config:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr(cfgmod, "CONFIG_FILE", config_file)
    if toml_text is not None:
        config_file.write_text(toml_text)
    return load_config()


def test_default_config_is_written_when_missing(monkeypatch, tmp_path):
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr(cfgmod, "CONFIG_FILE", config_file)
    assert not config_file.exists()
    cfg = load_config()
    assert config_file.exists()
    assert cfg == Config()


def test_default_snapshot_settings():
    cfg = Config()
    assert cfg.snapshot_enabled is True
    assert cfg.snapshot_backend == "auto"


def test_default_automation_settings():
    cfg = Config()
    assert cfg.auto_update is False
    assert cfg.auto_update_profile == ""
    assert cfg.profiles == {}


def test_snapshot_section_parses(monkeypatch, tmp_path):
    cfg = _load(monkeypatch, tmp_path, """
[snapshot]
enabled = false
backend = "timeshift"
""")
    assert cfg.snapshot_enabled is False
    assert cfg.snapshot_backend == "timeshift"


def test_profiles_section_parses_named_pattern_lists(monkeypatch, tmp_path):
    cfg = _load(monkeypatch, tmp_path, """
[profiles]
browsers = ["firefox", "chromium", "*chrome*"]
editors = ["code", "cursor-bin"]
""")
    assert cfg.profiles == {
        "browsers": ["firefox", "chromium", "*chrome*"],
        "editors": ["code", "cursor-bin"],
    }


def test_automation_section_parses(monkeypatch, tmp_path):
    cfg = _load(monkeypatch, tmp_path, """
[automation]
auto_update = true
auto_update_profile = "browsers"
""")
    assert cfg.auto_update is True
    assert cfg.auto_update_profile == "browsers"


def test_missing_sections_fall_back_to_defaults(monkeypatch, tmp_path):
    cfg = _load(monkeypatch, tmp_path, "[general]\naur_helper = \"paru\"\n")
    assert cfg.aur_helper == "paru"
    assert cfg.snapshot_enabled is True
    assert cfg.profiles == {}
    assert cfg.auto_update is False
