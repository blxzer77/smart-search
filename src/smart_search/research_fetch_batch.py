import asyncio
from typing import Any, Awaitable, Callable

from .research_cache import CACHE_TTL_BY_CAPABILITY, cached_call, make_keyed

DEFAULT_CANDIDATE_FETCH_CONCURRENCY = 3


async def fetch_research_candidates_concurrent(
    candidates: list[dict[str, Any]],
    *,
    question: str,
    fallback_mode: str,
    fetched_urls: set[str],
    run_web_fetch_fallback: Callable[..., Awaitable[tuple[dict[str, Any] | None, list[dict]]]],
    research_fetch_order: Callable[..., list[str]],
    concurrency: int = DEFAULT_CANDIDATE_FETCH_CONCURRENCY,
) -> list[dict[str, Any]]:
    """Fetch discovery candidates with bounded concurrency; preserves candidate order in results.

    Per-URL exceptions are isolated: one failure becomes an empty fetch_result entry
    instead of aborting the whole batch.
    """
    work: list[tuple[int, dict[str, Any], str]] = []
    for index, candidate in enumerate(candidates, 1):
        url = candidate.get("url", "")
        if not url or url in fetched_urls:
            continue
        work.append((index, candidate, url))

    if not work:
        return []

    limit = max(1, int(concurrency))
    sem = asyncio.Semaphore(limit)

    async def run_one(index: int, candidate: dict[str, Any], url: str) -> dict[str, Any]:
        try:
            async with sem:
                order = research_fetch_order(question, url)
                cache_key = make_keyed("web_fetch", url, fallback_mode, "|".join(order))
                cached_result, cache_hit = await cached_call(
                    "web_fetch",
                    cache_key,
                    CACHE_TTL_BY_CAPABILITY["web_fetch"],
                    run_web_fetch_fallback,
                    url,
                    fallback=fallback_mode,
                    preferred_order=order,
                    cache_only_success=True,
                )
                fetch_result, attempts = cached_result
            return {
                "index": index,
                "candidate": candidate,
                "url": url,
                "fetch_result": fetch_result,
                "attempts": attempts,
                "cache_hit": cache_hit,
            }
        except Exception as exc:  # noqa: BLE001 — isolate per-URL failures
            return {
                "index": index,
                "candidate": candidate,
                "url": url,
                "fetch_result": None,
                "attempts": [
                    {
                        "capability": "web_fetch",
                        "provider": "batch",
                        "status": "error",
                        "error_type": "runtime_error",
                        "error": str(exc),
                    }
                ],
                "cache_hit": False,
                "batch_error": True,
            }

    return list(await asyncio.gather(*(run_one(i, c, u) for i, c, u in work)))
