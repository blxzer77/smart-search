import time
from typing import Any

from . import service as _service
from .research_cache import CACHE_TTL_BY_CAPABILITY, cached_call, is_time_sensitive, make_key
from .research_fetch_batch import fetch_research_candidates_concurrent
from .research_keywords import MINIMUM_PROFILE_ERROR, RESEARCH_ROUTE_POLICY_VERSION
from .research_progress import ProgressReporter, make_progress_reporter

RESEARCH_OUTPUT_SCHEMA_VERSION = 1


def _elapsed_ms(*args, **kwargs):
    return _service._elapsed_ms(*args, **kwargs)


def validate_minimum_profile(*args, **kwargs):
    return _service.validate_minimum_profile(*args, **kwargs)


def build_deep_research_plan(*args, **kwargs):
    return _service.build_deep_research_plan(*args, **kwargs)


def _deep_budget(*args, **kwargs):
    return _service._deep_budget(*args, **kwargs)


def _default_evidence_dir(*args, **kwargs):
    return _service._default_evidence_dir(*args, **kwargs)


def _research_capability_routes(*args, **kwargs):
    return _service._research_capability_routes(*args, **kwargs)


def _write_research_artifact(*args, **kwargs):
    return _service._write_research_artifact(*args, **kwargs)


def _extract_urls(*args, **kwargs):
    return _service._extract_urls(*args, **kwargs)


def _research_evidence_item(*args, **kwargs):
    return _service._research_evidence_item(*args, **kwargs)


def _select_candidate_urls(*args, **kwargs):
    return _service._select_candidate_urls(*args, **kwargs)


def _research_gap_status(*args, **kwargs):
    return _service._research_gap_status(*args, **kwargs)


def _evidence_only_synthesis(*args, **kwargs):
    return _service._evidence_only_synthesis(*args, **kwargs)


def _citation_items(*args, **kwargs):
    return _service._citation_items(*args, **kwargs)


def _provider_names_from_attempts(*args, **kwargs):
    return _service._provider_names_from_attempts(*args, **kwargs)


def _fallback_used(*args, **kwargs):
    return _service._fallback_used(*args, **kwargs)


def _attempt(*args, **kwargs):
    return _service._attempt(*args, **kwargs)


def _normalize_source_results(*args, **kwargs):
    return _service._normalize_source_results(*args, **kwargs)


def _research_fetch_order(*args, **kwargs):
    return _service._research_fetch_order(*args, **kwargs)


async def _run_web_fetch_fallback(*args, **kwargs):
    return await _service._run_web_fetch_fallback(*args, **kwargs)


async def _run_bilingual_web_search(*args, **kwargs):
    return await _service._run_bilingual_web_search(*args, **kwargs)


async def _run_docs_search_fallback(*args, **kwargs):
    return await _service._run_docs_search_fallback(*args, **kwargs)


async def context7_library(*args, **kwargs):
    return await _service.context7_library(*args, **kwargs)


async def context7_docs(*args, **kwargs):
    return await _service.context7_docs(*args, **kwargs)


async def exa_search(*args, **kwargs):
    return await _service.exa_search(*args, **kwargs)


async def research(
    query: str,
    budget: str = "deep",
    evidence_dir: str = "",
    fallback: str = "auto",
    locale_scope: str = "both",
    dry_run: bool = False,
    progress: bool = False,
) -> dict[str, Any]:
    start = time.time()
    question = query.strip()
    fallback_mode = (fallback or "auto").strip().lower()
    report: ProgressReporter = make_progress_reporter(progress and not dry_run)
    if fallback_mode not in {"auto", "off"}:
        return {
            "ok": False,
            "error_type": "parameter_error",
            "error": f"Invalid fallback mode: {fallback_mode}",
            "question": question,
            "mode": "deep_research_execution",
            "route_policy_version": RESEARCH_ROUTE_POLICY_VERSION,
            "elapsed_ms": _elapsed_ms(start),
        }

    from .research_discovery import LOCALE_SCOPE_CHOICES, normalize_locale_scope
    from .research_plan import candidate_fetch_limit_for_budget

    try:
        locale_scope_mode = normalize_locale_scope(locale_scope)
    except ValueError:
        invalid_scope = (locale_scope or "").strip().lower() or "(empty)"
        return {
            "ok": False,
            "error_type": "parameter_error",
            "error": f"Invalid locale scope: {invalid_scope}; expected one of: {', '.join(sorted(LOCALE_SCOPE_CHOICES))}",
            "question": question,
            "mode": "deep_research_execution",
            "route_policy_version": RESEARCH_ROUTE_POLICY_VERSION,
            "elapsed_ms": _elapsed_ms(start),
        }

    minimum = validate_minimum_profile()
    budget_mode = _deep_budget(budget or "deep")
    plan = build_deep_research_plan(question, budget=budget_mode, evidence_dir=evidence_dir)
    routes = _research_capability_routes(
        question,
        plan,
        fallback_mode,
        capability_status=minimum.get("capability_status", {}),
    )
    fetch_limit = candidate_fetch_limit_for_budget(budget_mode)

    if dry_run:
        if report:
            report("dry-run: plan only, no live providers")
        return {
            "ok": True,
            "dry_run": True,
            "mode": "deep_research",
            "query_mode": "research",
            "question": question,
            "budget": budget_mode,
            "locale_scope": locale_scope_mode,
            "candidate_fetch_limit": fetch_limit,
            "research_plan": plan,
            "routing_decision": routes,
            "minimum_profile_ok": minimum.get("ok", False),
            "capability_status": minimum.get("capability_status", {}),
            "output_schema_version": RESEARCH_OUTPUT_SCHEMA_VERSION,
            "route_policy_version": RESEARCH_ROUTE_POLICY_VERSION,
            "evidence_dir": plan.get("evidence_dir") or _default_evidence_dir(question),
            "elapsed_ms": _elapsed_ms(start),
        }

    if not minimum.get("ok"):
        return {
            "ok": False,
            "error_type": minimum.get("error_type", "config_error"),
            "error": minimum.get("error", MINIMUM_PROFILE_ERROR),
            "question": question,
            "mode": "deep_research_execution",
            "minimum_profile_ok": False,
            "capability_status": minimum.get("capability_status", {}),
            "final_answer": "",
            "citations": [],
            "evidence_items": [],
            "gap_check": {
                "status": "failed",
                "gaps": [{"subquestion_id": "", "reason": "minimum profile is missing required capabilities"}],
            },
            "provider_attempts": [],
            "fallback_used": False,
            "degraded": True,
            "route_policy_version": RESEARCH_ROUTE_POLICY_VERSION,
            "evidence_dir": evidence_dir,
            "elapsed_ms": _elapsed_ms(start),
        }

    if report:
        report(f"plan ready ({len(plan.get('steps') or [])} steps, budget={budget_mode})")

    evidence_root = plan.get("evidence_dir") or _default_evidence_dir(question)
    provider_attempts: list[dict[str, Any]] = []
    discovery_sources: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    stage_results: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    _write_research_artifact(evidence_root, "00-plan.json", plan)

    urls = _extract_urls(question)
    fetch_order = routes["capabilities"]["web_fetch"]["providers"]
    if urls:
        if report:
            report(f"known_url_fetch: {len(urls)} url(s)")
        for index, url in enumerate(urls, 1):
            fetch_key = make_key("web_fetch", url, fallback_mode, "|".join(fetch_order))
            cached_result, cache_hit = await cached_call(
                "web_fetch",
                fetch_key,
                CACHE_TTL_BY_CAPABILITY["web_fetch"],
                _run_web_fetch_fallback,
                url,
                fallback=fallback_mode,
                preferred_order=fetch_order,
                cache_only_success=True,
            )
            fetch_result, attempts = cached_result
            if cache_hit:
                for a in attempts:
                    a["cache_hit"] = True
            provider_attempts.extend(attempts)
            stage_results.append({"stage": "known_url_fetch", "url": url, "ok": bool(fetch_result), "provider_attempts": attempts, "cache_hit": cache_hit})
            if fetch_result:
                item = _research_evidence_item(
                    url=fetch_result["url"],
                    provider=fetch_result["provider"],
                    title=fetch_result["url"],
                    content=fetch_result["content"],
                    subquestion_id="sq1",
                )
                evidence_items.append(item)
                _write_research_artifact(evidence_root, f"{index:02d}-fetch-{fetch_result['provider']}.md", fetch_result["content"])
            else:
                gaps.append({"subquestion_id": "sq1", "reason": f"failed to fetch known URL: {url}", "url": url})

    signals = routes["signals"]
    if signals["docs_api_intent"]:
        if report:
            report("docs_discovery: starting")
        docs_providers = routes["capabilities"]["docs_search"]["providers"]
        selected_docs_providers = docs_providers[:1] if fallback_mode == "off" else docs_providers
        if not selected_docs_providers:
            gaps.append({"subquestion_id": "sq2", "reason": "no configured docs_search provider for docs/API evidence"})
        for provider in selected_docs_providers:
            step_start = time.time()
            if provider == "context7":
                docs_ttl = None if is_time_sensitive(question) else CACHE_TTL_BY_CAPABILITY["docs_search"]
                data, cache_hit = await cached_call(
                    "docs_search",
                    make_key("context7_library", question),
                    docs_ttl,
                    context7_library,
                    question,
                    question,
                )
                if data.get("ok") and data.get("results"):
                    provider_attempts.append(_attempt("docs_search", "context7", "ok", step_start, result_count=len(data.get("results") or []), cache_hit=cache_hit))
                    stage_results.append({"stage": "docs_discovery", "provider": "context7", "ok": True, "result_count": len(data.get("results") or []), "cache_hit": cache_hit})
                    library_id = (data.get("results") or [{}])[0].get("id", "")
                    if library_id:
                        docs_start = time.time()
                        docs_data, docs_cache_hit = await cached_call(
                            "docs_search",
                            make_key("context7_docs", library_id, question),
                            docs_ttl,
                            context7_docs,
                            library_id,
                            question,
                        )
                        if docs_data.get("ok") and docs_data.get("content"):
                            provider_attempts.append(_attempt("docs_search", "context7", "ok", docs_start, result_count=1, cache_hit=docs_cache_hit))
                            item = _research_evidence_item(
                                url=f"context7:{library_id}",
                                provider="context7",
                                title=library_id,
                                content=docs_data.get("content", ""),
                                source_type="docs",
                                subquestion_id="sq2",
                            )
                            evidence_items.append(item)
                            _write_research_artifact(evidence_root, "docs-context7.md", docs_data.get("content", ""))
                            break
                        docs_status = "error" if docs_data.get("error_type") else "empty"
                        provider_attempts.append(_attempt("docs_search", "context7", docs_status, docs_start, error_type=docs_data.get("error_type", ""), error=docs_data.get("error", ""), cache_hit=docs_cache_hit))
                    if fallback_mode == "off":
                        break
                    continue
                status = "error" if data.get("error_type") in {"auth_error", "timeout", "network_error", "runtime_error"} else "empty"
                provider_attempts.append(_attempt("docs_search", "context7", status, step_start, error_type=data.get("error_type", ""), error=data.get("error", ""), cache_hit=cache_hit))
            elif provider == "exa":
                docs_ttl = None if is_time_sensitive(question) else CACHE_TTL_BY_CAPABILITY["docs_search"]
                data, cache_hit = await cached_call(
                    "docs_search",
                    make_key("exa_search", question, 5, True),
                    docs_ttl,
                    exa_search,
                    question,
                    num_results=5,
                    include_highlights=True,
                )
                if data.get("ok"):
                    sources = _normalize_source_results(data.get("results"), "exa")
                    if sources:
                        provider_attempts.append(_attempt("docs_search", "exa", "ok", step_start, result_count=len(sources), cache_hit=cache_hit))
                        discovery_sources.extend(sources)
                        stage_results.append({"stage": "docs_discovery", "provider": "exa", "ok": True, "result_count": len(sources), "cache_hit": cache_hit})
                        break
                provider_attempts.append(_attempt("docs_search", "exa", "error" if data.get("error_type") else "empty", step_start, error_type=data.get("error_type", ""), error=data.get("error", ""), cache_hit=cache_hit))

    should_run_web_discovery = (
        signals["current_or_locale_intent"]
        or signals["cross_validation_need"] == "high"
        or signals.get("broad_research_intent")
        or (not evidence_items and not discovery_sources)
    ) and not (urls and fallback_mode == "off")
    if should_run_web_discovery:
        web_provider_order = routes["capabilities"]["web_search"]["providers"]
        if web_provider_order:
            if report:
                report(f"web_discovery: locale_scope={locale_scope_mode}")
            web_ttl = None if is_time_sensitive(question) else CACHE_TTL_BY_CAPABILITY["web_search"]
            web_result, web_cache_hit = await cached_call(
                "web_search",
                make_key("bilingual", question, 5, ",".join(web_provider_order), fallback_mode, locale_scope_mode),
                web_ttl,
                _run_bilingual_web_search,
                question,
                count=5,
                providers=",".join(web_provider_order),
                fallback=fallback_mode,
                locale_scope=locale_scope_mode,
            )
            web_sources, attempts = web_result
            if web_cache_hit:
                for a in attempts:
                    a["cache_hit"] = True
            provider_attempts.extend(attempts)
            discovery_sources.extend(web_sources)
            stage_results.append({"stage": "web_discovery", "ok": bool(web_sources), "result_count": len(web_sources), "provider_attempts": attempts, "cache_hit": web_cache_hit})
            if report:
                report(f"web_discovery: {len(web_sources)} source(s)")
        else:
            gaps.append({"subquestion_id": "", "reason": "no configured web_search provider for discovery"})

    exa_in_selected_docs_route = "exa" in routes["capabilities"]["docs_search"]["providers"]
    if (
        fallback_mode != "off"
        and signals["official_low_noise_intent"]
        and exa_in_selected_docs_route
        and not any(source.get("provider") == "exa" for source in discovery_sources)
    ):
        exa_start = time.time()
        exa_ttl = None if is_time_sensitive(question) else CACHE_TTL_BY_CAPABILITY["docs_search"]
        data, exa_cache_hit = await cached_call(
            "docs_search",
            make_key("exa_supplemental", question, 5, True),
            exa_ttl,
            exa_search,
            question,
            num_results=5,
            include_highlights=True,
        )
        if data.get("ok"):
            sources = _normalize_source_results(data.get("results"), "exa")
            if sources:
                provider_attempts.append(_attempt("docs_search", "exa", "ok", exa_start, result_count=len(sources), cache_hit=exa_cache_hit))
                discovery_sources.extend(sources)
        else:
            provider_attempts.append(_attempt("docs_search", "exa", "error", exa_start, error_type=data.get("error_type", ""), error=data.get("error", ""), cache_hit=exa_cache_hit))

    candidates = _select_candidate_urls(discovery_sources, limit=fetch_limit)
    if report and candidates:
        report(f"candidate_fetch: {len(candidates)} candidate(s), limit={fetch_limit}")
    fetched_urls = {item.get("url") for item in evidence_items}
    no_new_evidence = True
    batch_results = await fetch_research_candidates_concurrent(
        candidates,
        question=question,
        fallback_mode=fallback_mode,
        fetched_urls=fetched_urls,
        run_web_fetch_fallback=_run_web_fetch_fallback,
        research_fetch_order=_research_fetch_order,
    )
    for entry in batch_results:
        index = entry["index"]
        candidate = entry["candidate"]
        url = entry["url"]
        fetch_result = entry["fetch_result"]
        attempts = entry["attempts"]
        entry_cache_hit = entry.get("cache_hit", False)
        if entry_cache_hit:
            for a in attempts:
                a["cache_hit"] = True
        provider_attempts.extend(attempts)
        stage_results.append({"stage": "candidate_fetch", "url": url, "ok": bool(fetch_result), "provider_attempts": attempts, "cache_hit": entry_cache_hit})
        if report:
            status = "ok" if fetch_result else "miss"
            report(f"candidate_fetch [{status}]: {url}")
        if fetch_result:
            no_new_evidence = False
            fetched_urls.add(url)
            content = fetch_result.get("content", "")
            item = _research_evidence_item(
                url=fetch_result["url"],
                provider=fetch_result["provider"],
                title=candidate.get("title") or fetch_result["url"],
                content=content,
                subquestion_id=candidate.get("subquestion_id", ""),
            )
            evidence_items.append(item)
            _write_research_artifact(evidence_root, f"fetch-{index:02d}-{fetch_result['provider']}.md", content)
        elif fallback_mode == "off":
            gaps.append({"subquestion_id": "", "reason": f"fetch failed with fallback off: {url}", "url": url})

    if not evidence_items:
        gaps.append({"subquestion_id": "", "reason": "no fetched/read evidence items were produced"})
    elif no_new_evidence and not urls and candidates:
        gaps.append({"subquestion_id": "", "reason": "discovery produced candidates but no new fetch evidence converged"})

    gap_status, stop_reason = _research_gap_status(evidence_items, gaps, signals=signals)
    citations = _citation_items(evidence_items)
    final_answer = _evidence_only_synthesis(question, evidence_items, gaps)
    research_ok = gap_status == "closed"
    if report:
        report(f"gap_check: {gap_status} ({len(evidence_items)} evidence item(s))")
    result = {
        "ok": research_ok,
        "error_type": "" if research_ok else "evidence_error",
        "error": "" if research_ok else "research could not obtain fetched evidence",
        "mode": "deep_research_execution",
        "query_mode": "research",
        "question": question,
        "budget": budget_mode,
        "locale_scope": locale_scope_mode,
        "candidate_fetch_limit": fetch_limit,
        "output_schema_version": RESEARCH_OUTPUT_SCHEMA_VERSION,
        "research_plan": plan,
        "routing_decision": routes,
        "stage_results": stage_results,
        "discovery_sources": discovery_sources,
        "final_answer": final_answer,
        "content": final_answer,
        "citations": citations,
        "evidence_items": evidence_items,
        "gap_check": {
            "status": gap_status,
            "gaps": gaps,
            "stop_reason": stop_reason,
        },
        "provider_attempts": provider_attempts,
        "providers_used": _provider_names_from_attempts(provider_attempts),
        "fallback_used": _fallback_used(provider_attempts),
        "degraded": bool(gaps),
        "route_policy_version": RESEARCH_ROUTE_POLICY_VERSION,
        "evidence_dir": evidence_root,
        "minimum_profile_ok": minimum.get("ok", False),
        "capability_status": minimum.get("capability_status", {}),
        "elapsed_ms": _elapsed_ms(start),
    }
    _write_research_artifact(evidence_root, "summary.json", result)
    return result
