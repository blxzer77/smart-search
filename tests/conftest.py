import sys
from pathlib import Path

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(autouse=True)
def isolate_smart_search_config(monkeypatch, tmp_path):
    from smart_search.config import Config

    config = Config()
    monkeypatch.setattr(config, "_config_file", tmp_path / "config.json")
    monkeypatch.setattr(config, "_config_dir_source", "override")
    monkeypatch.setattr(config, "_cached_model", None)
    for key in config._CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("SMART_SEARCH_CONFIG_DIR", raising=False)
    monkeypatch.setenv("SMART_SEARCH_MINIMUM_PROFILE", "off")


@pytest.fixture(autouse=True)
def _reset_research_cache(monkeypatch):
    """Per-test isolation: clear the process-wide provider cache and re-read env."""
    from smart_search import research_cache
    from smart_search.research_cache import _TTLCache, reset_cache_disabled_flag

    monkeypatch.delenv("SMART_SEARCH_CACHE", raising=False)
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()
    yield
    reset_cache_disabled_flag()
    research_cache._REGISTRY = _TTLCache()
