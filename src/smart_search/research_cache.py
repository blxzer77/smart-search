import os
import random
import time
from typing import Any, Awaitable, Callable

CACHE_TTL_BY_CAPABILITY = {
    "web_fetch": 7 * 24 * 3600,
    "docs_search": 3600,
    "web_search": 600,
}
_JITTER = 0.1
_DISABLED_FLAG: bool | None = None


def _cache_disabled() -> bool:
    global _DISABLED_FLAG
    if _DISABLED_FLAG is None:
        _DISABLED_FLAG = (os.getenv("SMART_SEARCH_CACHE", "on").strip().lower() in {"off", "0", "false", "no"})
    return _DISABLED_FLAG


def reset_cache_disabled_flag() -> None:
    global _DISABLED_FLAG
    _DISABLED_FLAG = None


def is_time_sensitive(query: str) -> bool:
    from .research_keywords import DEEP_CURRENT_KEYWORDS, DEEP_RECENT_KEYWORDS

    q = (query or "").lower()
    return any(kw in q for kw in DEEP_CURRENT_KEYWORDS) or any(kw in q for kw in DEEP_RECENT_KEYWORDS)


class _TTLCache:
    def __init__(self) -> None:
        self._store: dict[tuple, tuple[float, Any]] = {}

    def get(self, key: tuple) -> Any:
        now = time.time()
        entry = self._store.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if now > expiry:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: tuple, value: Any, ttl: int) -> None:
        jitter = random.uniform(-_JITTER, _JITTER) * ttl
        self._store[key] = (time.time() + ttl + jitter, value)

    def clear(self) -> None:
        self._store.clear()


_REGISTRY = _TTLCache()


def make_key(capability: str, *parts: Any) -> tuple:
    return (capability, *(str(p) for p in parts))


async def cached_call(
    capability: str,
    key: tuple,
    ttl: int | None,
    func: Callable[..., Awaitable[Any]],
    *args: Any,
    cache_only_success: bool = False,
    **kwargs: Any,
) -> tuple[Any, bool]:
    if _cache_disabled() or ttl is None or ttl <= 0:
        return await func(*args, **kwargs), False
    full_key = (capability,) + key
    cached = _REGISTRY.get(full_key)
    if cached is not None:
        return cached, True
    result = await func(*args, **kwargs)
    if cache_only_success and not _is_success_result(result):
        return result, False
    _REGISTRY.set(full_key, result, ttl)
    return result, False


def _is_success_result(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, tuple) and result:
        fetch_result = result[0]
        if fetch_result is None:
            return False
        if isinstance(fetch_result, dict) and fetch_result.get("ok") is False:
            return False
    if isinstance(result, dict) and result.get("ok") is False:
        return False
    return True


def clear() -> None:
    _REGISTRY.clear()
