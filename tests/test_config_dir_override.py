from pathlib import Path

import pytest

from smart_search.config import Config


def _fresh_config_file(monkeypatch):
    config = Config()
    monkeypatch.setattr(config, "_config_file", None)
    monkeypatch.setattr(config, "_config_dir_source", None)
    return config


def test_env_dir_overrides_config_file_path(monkeypatch, tmp_path):
    target = tmp_path / "custom-config-root"
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(target))
    config = _fresh_config_file(monkeypatch)
    assert config.config_file == target / "config.json"
    assert config.config_dir_source == "environment"
    info = config.config_path_info()
    assert info["config_dir_override_value"] == str(target)
    assert info["config_dir_override_matches_default"] is False
    assert target.exists() and target.is_dir()


def test_windows_env_override_matching_default_is_reported(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_local_appdata = tmp_path / "local-appdata"
    default_dir = fake_local_appdata / "smart-search"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr("smart_search.config.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(fake_local_appdata))
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(default_dir))
    config = _fresh_config_file(monkeypatch)
    info = config.config_path_info()
    assert config.config_file == default_dir / "config.json"
    assert config.config_dir_source == "environment"
    assert info["default_config_file"] == str(default_dir / "config.json")
    assert info["config_dir_override_value"] == str(default_dir)
    assert info["config_dir_override_matches_default"] is True


def test_env_dir_pointing_at_unwritable_does_not_crash(monkeypatch, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    bogus = blocker / "child"
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(bogus))
    config = _fresh_config_file(monkeypatch)
    assert config.config_file == bogus / "config.json"
    assert config.config_dir_source == "environment"
    assert config._load_config_file() == {}


def test_no_env_falls_back_to_platform_default(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_local_appdata = tmp_path / "local-appdata"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr("smart_search.config.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(fake_local_appdata))
    config = _fresh_config_file(monkeypatch)
    assert config.config_file == fake_local_appdata / "smart-search" / "config.json"
    assert config.config_dir_source == "default"


def test_windows_uses_legacy_home_config_when_new_default_missing(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_local_appdata = tmp_path / "local-appdata"
    legacy_config = fake_home / ".config" / "smart-search" / "config.json"
    legacy_config.parent.mkdir(parents=True)
    legacy_config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr("smart_search.config.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(fake_local_appdata))
    config = _fresh_config_file(monkeypatch)
    assert config.config_file == legacy_config
    assert config.config_dir_source == "legacy_windows_home"


def test_windows_prefers_new_default_when_both_new_and_legacy_exist(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_local_appdata = tmp_path / "local-appdata"
    legacy_config = fake_home / ".config" / "smart-search" / "config.json"
    new_config = fake_local_appdata / "smart-search" / "config.json"
    legacy_config.parent.mkdir(parents=True)
    legacy_config.write_text("{}", encoding="utf-8")
    new_config.parent.mkdir(parents=True)
    new_config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr("smart_search.config.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(fake_local_appdata))
    config = _fresh_config_file(monkeypatch)
    assert config.config_file == new_config
    assert config.config_dir_source == "default"


def test_no_env_non_windows_falls_back_to_home(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr("smart_search.config.sys.platform", "linux")
    config = _fresh_config_file(monkeypatch)
    assert config.config_file == fake_home / ".config" / "smart-search" / "config.json"
    assert config.config_dir_source == "default"


def test_env_dir_also_governs_log_dir_parent(monkeypatch, tmp_path):
    target = tmp_path / "shared-root"
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(target))
    config = _fresh_config_file(monkeypatch)
    assert config.log_dir == target / "logs"
    assert config.log_dir_config_value == "logs"
    assert not (target / "logs").exists()


def test_env_dir_also_governs_default_evidence_dir_parent(monkeypatch, tmp_path):
    target = tmp_path / "shared-root"
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(target))
    config = _fresh_config_file(monkeypatch)
    assert config.evidence_dir == target / "evidence"
    assert config.evidence_dir_config_value == "evidence"
    assert not (target / "evidence").exists()


def test_absolute_evidence_dir_is_resolved_without_creation(monkeypatch, tmp_path):
    target = tmp_path / "shared-root"
    evidence_dir = tmp_path / "explicit-evidence"
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(target))
    monkeypatch.setenv("SMART_SEARCH_EVIDENCE_DIR", str(evidence_dir))
    config = _fresh_config_file(monkeypatch)
    assert config.evidence_dir == evidence_dir
    assert config.evidence_dir_config_value == str(evidence_dir)
    assert not evidence_dir.exists()


def test_tavily_timeout_defaults_to_sixty_seconds(monkeypatch):
    monkeypatch.delenv("TAVILY_TIMEOUT_SECONDS", raising=False)
    config = _fresh_config_file(monkeypatch)
    assert config.tavily_timeout == 60.0
    info = config.get_config_info()
    assert info["TAVILY_TIMEOUT_SECONDS"] == 60.0
    assert info["config_sources"]["TAVILY_TIMEOUT_SECONDS"] == "default"


def test_tavily_timeout_can_be_configured(monkeypatch):
    monkeypatch.setenv("TAVILY_TIMEOUT_SECONDS", "45")
    config = _fresh_config_file(monkeypatch)
    assert config.tavily_timeout == 45.0
    info = config.get_config_info()
    assert info["TAVILY_TIMEOUT_SECONDS"] == 45.0
    assert info["config_sources"]["TAVILY_TIMEOUT_SECONDS"] == "environment"


def test_absolute_log_dir_is_resolved_without_creation(monkeypatch, tmp_path):
    target = tmp_path / "shared-root"
    log_dir = tmp_path / "explicit-logs"
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(target))
    monkeypatch.setenv("SMART_SEARCH_LOG_DIR", str(log_dir))
    config = _fresh_config_file(monkeypatch)
    assert config.log_dir == log_dir
    assert config.log_dir_config_value == str(log_dir)
    assert not log_dir.exists()


def test_save_unwritable_raises_with_hint(monkeypatch, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file")
    bogus = blocker / "child"
    monkeypatch.setenv("SMART_SEARCH_CONFIG_DIR", str(bogus))
    config = _fresh_config_file(monkeypatch)
    with pytest.raises(ValueError) as exc:
        config._save_config_file({"x": 1})
    assert "无法保存" in str(exc.value)
