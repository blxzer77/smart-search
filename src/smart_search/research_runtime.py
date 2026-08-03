"""Runtime helpers for research execution without importing service at module level."""

from .research_artifacts import write_research_artifact as _write_research_artifact
from .research_gap import research_gap_status as _research_gap_status
from .research_plan import (
    _deep_budget,
    _default_evidence_dir,
    _elapsed_ms,
    _extract_urls,
    build_deep_research_plan,
)
from .research_routing import _research_capability_routes, _research_fetch_order
from .research_synthesis import (
    citation_items as _citation_items,
    evidence_only_synthesis as _evidence_only_synthesis,
    research_evidence_item as _research_evidence_item,
    select_candidate_urls as _select_candidate_urls,
)


def _service():
    from . import service as svc

    return svc


async def _run_web_fetch_fallback(*args, **kwargs):
    # Route via service so tests can monkeypatch service._run_web_fetch_fallback.
    return await _service()._run_web_fetch_fallback(*args, **kwargs)


async def _run_bilingual_web_search(*args, **kwargs):
    return await _service()._run_bilingual_web_search(*args, **kwargs)


async def _run_docs_search_fallback(*args, **kwargs):
    return await _service()._run_docs_search_fallback(*args, **kwargs)


def validate_minimum_profile(*args, **kwargs):
    return _service().validate_minimum_profile(*args, **kwargs)


def _attempt(*args, **kwargs):
    return _service()._attempt(*args, **kwargs)


def _normalize_source_results(*args, **kwargs):
    return _service()._normalize_source_results(*args, **kwargs)


def _provider_names_from_attempts(*args, **kwargs):
    return _service()._provider_names_from_attempts(*args, **kwargs)


def _fallback_used(*args, **kwargs):
    return _service()._fallback_used(*args, **kwargs)


async def context7_library(*args, **kwargs):
    return await _service().context7_library(*args, **kwargs)


async def context7_docs(*args, **kwargs):
    return await _service().context7_docs(*args, **kwargs)


async def exa_search(*args, **kwargs):
    return await _service().exa_search(*args, **kwargs)
