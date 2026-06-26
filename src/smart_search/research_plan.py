import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import config
from .research_intent import (
    contains_any as _contains_any,
    is_docs_intent as _is_docs_intent,
    is_zh_current_intent as _is_zh_current_intent,
)
from .research_keywords import (
    DEEP_ALLOWED_TOOLS,
    DEEP_CHINA_KEYWORDS,
    DEEP_CURRENT_KEYWORDS,
    DEEP_EXA_DISCOVERY_KEYWORDS,
    DEEP_HIGH_COMPLEXITY_KEYWORDS,
    DEEP_RECENT_KEYWORDS,
)


def _elapsed_ms(start: float) -> float:
    return round((time.time() - start) * 1000, 2)


def _bilingual_search_queries(query: str) -> list[dict[str, str]]:
    question = query.strip()
    return [
        {
            "locale": "zh",
            "label": "Chinese-language sources",
            "query": f"中文搜索，优先检索中文来源，并回答原问题：{question}",
        },
        {
            "locale": "en",
            "label": "English-language sources",
            "query": f"Search English-language sources and answer the original question: {question}",
        },
    ]

def _extract_urls(query: str) -> list[str]:
    urls = []
    for match in re.findall(r"https?://[^\s<>\]\)\"']+", query):
        cleaned = match.rstrip(".,;，。；)")
        if cleaned:
            urls.append(cleaned)
    return urls


def _slugify_query(query: str) -> str:
    slug = re.sub(r"https?://", "", query.lower())
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", slug, flags=re.IGNORECASE)
    slug = slug.strip("-")
    return slug[:48] or "deep-research"


def _default_evidence_dir(query: str) -> str:
    timestamp = time.strftime("%Y%m%d-%H%M")
    return str(config.evidence_dir / f"{timestamp}-{_slugify_query(query)}")


def _quote_arg(value: str) -> str:
    escaped = value.replace("`", "``").replace("$", "`$").replace('"', '`"')
    return f'"{escaped}"'


def _path_join(base: str, filename: str) -> str:
    return str(Path(base) / filename)


def _deep_step(
    step_id: str,
    subquestion_id: str,
    tool: str,
    purpose: str,
    command: str,
    output_path: str,
) -> dict[str, str]:
    return {
        "id": step_id,
        "subquestion_id": subquestion_id,
        "tool": tool,
        "purpose": purpose,
        "command": command,
        "output_path": output_path,
    }


def _deep_capability(capability: str, tools: list[str], reason: str) -> dict[str, Any]:
    return {"capability": capability, "tools": tools, "reason": reason}


def _deep_subquestion(sub_id: str, question: str, reason: str, required_capabilities: list[str]) -> dict[str, Any]:
    return {
        "id": sub_id,
        "question": question,
        "reason": reason,
        "required_capabilities": required_capabilities,
    }


def _deep_budget(value: str) -> str:
    budget = (value or "standard").strip().lower()
    return budget if budget in {"quick", "standard", "deep"} else "standard"


CANDIDATE_FETCH_LIMIT_BY_BUDGET = {"quick": 3, "standard": 5, "deep": 6}


def candidate_fetch_limit_for_budget(budget: str) -> int:
    """Cap discovery candidate fetches by research budget (cost control)."""
    return CANDIDATE_FETCH_LIMIT_BY_BUDGET.get(_deep_budget(budget), CANDIDATE_FETCH_LIMIT_BY_BUDGET["standard"])


def _is_deep_complex(query: str, budget: str) -> bool:
    q = re.sub(r"https?://[^\s<>\]\)\"']+", "", query)
    object_separators = len(re.findall(r"[/、,，]| 和 | 与 | vs | VS | versus ", q))
    return budget == "deep" or _contains_any(query, DEEP_HIGH_COMPLEXITY_KEYWORDS) or object_separators >= 2


def build_deep_research_plan(query: str, budget: str = "standard", evidence_dir: str = "") -> dict[str, Any]:
    start = time.time()
    question = query.strip()
    budget = _deep_budget(budget)
    evidence_root = evidence_dir.strip() or _default_evidence_dir(question)
    urls = _extract_urls(question)
    known_url = bool(urls)
    docs_intent = _is_docs_intent(question)
    zh_current_intent = _is_zh_current_intent(question)
    recency_requirement = "none"
    if _contains_any(question, DEEP_CURRENT_KEYWORDS) or zh_current_intent:
        recency_requirement = "current"
    elif _contains_any(question, {"行情", "价格", "走势", "币圈", "股票", "市场"}) and _contains_any(question, DEEP_RECENT_KEYWORDS):
        recency_requirement = "current"
    elif _contains_any(question, DEEP_RECENT_KEYWORDS):
        recency_requirement = "recent"
    locale_domain_scope = "china" if _contains_any(question, DEEP_CHINA_KEYWORDS) else "global"
    if known_url:
        locale_domain_scope = "known_domains"
    claim_risk = "high" if recency_requirement in {"recent", "current"} or _contains_any(question, {"核验", "验证", "真假", "价格", "行情", "财经", "医疗", "政策", "监管", "risk"}) else "medium"
    cross_validation_need = "high" if claim_risk == "high" or _contains_any(question, {"对比", "选型", "核验", "验证", "compare", "versus"}) else "normal"
    authority_need = "high" if docs_intent or claim_risk == "high" or _contains_any(question, {"官方", "文档", "论文", "标准", "政策", "监管", "official"}) else "normal"
    complex_query = _is_deep_complex(question, budget)
    difficulty = "high" if complex_query else "standard"

    intent_signals = {
        "recency_requirement": recency_requirement,
        "docs_api_intent": docs_intent,
        "locale_domain_scope": locale_domain_scope,
        "known_url": known_url,
        "source_authority_need": authority_need,
        "claim_risk": claim_risk,
        "cross_validation_need": cross_validation_need,
        "breadth_depth_budget": budget,
    }

    decomposition: list[dict[str, Any]] = []
    capability_plan: list[dict[str, Any]] = []
    steps: list[dict[str, str]] = []

    def add_step(sub_id: str, tool: str, purpose: str, command: str, filename: str) -> None:
        step_id = f"s{len(steps) + 1}"
        steps.append(_deep_step(step_id, sub_id, tool, purpose, command, _path_join(evidence_root, filename)))

    def next_filename(suffix: str) -> str:
        return f"{len(steps) + 1:02d}-{suffix}"

    def command_search(q: str, extra_sources: int = 2, filename: str = "") -> str:
        output_name = filename or next_filename("search.json")
        return f"smart-search search {_quote_arg(q)} --validation balanced --extra-sources {extra_sources} --format json --output {_quote_arg(_path_join(evidence_root, output_name))}"

    def command_exa(q: str) -> str:
        return f"smart-search exa-search {_quote_arg(q)} --num-results 5 --format json --output {_quote_arg(_path_join(evidence_root, next_filename('exa.json')))}"

    def command_fetch(target: str = "<key-url>") -> str:
        return f"smart-search fetch {_quote_arg(target)} --format markdown --output {_quote_arg(_path_join(evidence_root, next_filename('fetch.md')))}"

    def add_bilingual_search_steps(sub_id: str, purpose: str, extra_sources: int) -> None:
        for variant in _bilingual_search_queries(question):
            filename = next_filename(f"search-{variant['locale']}.json")
            add_step(
                sub_id,
                "search",
                f"{purpose}: {variant['label']}",
                command_search(variant["query"], extra_sources, filename),
                filename,
            )

    def has_capability(name: str) -> bool:
        return any(item.get("capability") == name for item in capability_plan)

    if known_url:
        url = urls[0]
        parsed = urlparse(url)
        host = parsed.netloc or "provided URL"
        decomposition.append(
            _deep_subquestion(
                "sq1",
                f"这个已知来源页面本身说了什么？{url}",
                "用户已经给出 URL，Deep Research 必须先抓正文再扩展。",
                ["page_evidence"],
            )
        )
        decomposition.append(
            _deep_subquestion(
                "sq2",
                f"围绕 {host} 还需要哪些相邻来源或交叉来源？",
                "已知好 URL 适合用相似页面和广泛发现扩展证据。",
                ["adjacent_source_discovery", "broad_discovery"],
            )
        )
        capability_plan.extend(
            [
                _deep_capability("page_evidence", ["fetch"], "Fetch the user-provided URL before making claims."),
                _deep_capability("adjacent_source_discovery", ["exa-similar"], "Find pages adjacent to the known source."),
                _deep_capability("broad_discovery", ["search"], "Broaden the context if the fetched page leaves gaps."),
            ]
        )
        add_step("sq1", "fetch", "fetch user supplied URL first", f"smart-search fetch {_quote_arg(url)} --format markdown --output {_quote_arg(_path_join(evidence_root, '01-fetch.md'))}", "01-fetch.md")
        add_step("sq2", "exa-similar", "find adjacent sources from the provided URL", f"smart-search exa-similar {_quote_arg(url)} --num-results 5 --format json --output {_quote_arg(_path_join(evidence_root, '02-similar.json'))}", "02-similar.json")
        add_bilingual_search_steps("sq2", "broad discovery for missing context", 1)
    else:
        decomposition.append(
            _deep_subquestion(
                "sq1",
                f"{question} 的整体问题轮廓和候选来源是什么？",
                "先做 broad discovery，避免一开始把问题拆错。",
                ["broad_discovery"],
            )
        )
        capability_plan.append(_deep_capability("broad_discovery", ["search"], "Find the initial answer shape and candidate sources."))
        add_bilingual_search_steps("sq1", "bilingual broad discovery and routing metadata", 1 if budget == "quick" else 3)

        if docs_intent:
            decomposition.append(
                _deep_subquestion(
                    "sq2",
                    f"{question} 的官方文档、API 或 SDK 证据在哪里？",
                    "docs/API intent should resolve the library docs first, with Exa only as official-domain discovery.",
                    ["docs_source_discovery", "page_evidence"],
                )
            )
            capability_plan.append(
                _deep_capability(
                    "docs_source_discovery",
                    ["context7-library", "context7-docs"],
                    "Resolve official library/API documentation first; use Exa only for official-domain or supplemental discovery.",
                )
            )
            library_hint = " ".join(re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", question)[:2]) or "<library-name>"
            add_step(
                "sq2",
                "context7-library",
                "resolve library id for docs/API intent",
                f"smart-search context7-library {_quote_arg(library_hint)} {_quote_arg(question)} --format json --output {_quote_arg(_path_join(evidence_root, next_filename('context7-library.json')))}",
                next_filename("context7-library.json"),
            )
            add_step(
                "sq2",
                "context7-docs",
                "retrieve docs after selecting the best library_id",
                f"smart-search context7-docs {_quote_arg('<library_id>')} {_quote_arg(question)} --format json --output {_quote_arg(_path_join(evidence_root, next_filename('context7-docs.json')))}",
                next_filename("context7-docs.json"),
            )
            if _contains_any(question, DEEP_EXA_DISCOVERY_KEYWORDS):
                capability_plan.append(
                    _deep_capability(
                        "official_domain_discovery",
                        ["exa-search"],
                        "Use Exa for official-domain or low-noise supplemental docs discovery.",
                    )
                )
                add_step("sq2", "exa-search", "official-domain docs source discovery", command_exa(f"{question} official docs"), next_filename("exa.json"))

        if recency_requirement != "none" or locale_domain_scope == "china":
            sub_id = f"sq{len(decomposition) + 1}"
            decomposition.append(
                _deep_subquestion(
                    sub_id,
                    f"{question} 的最新或中文/国内来源如何交叉验证？",
                    "Current or China-scoped prompts use bilingual search instead of Zhipu reinforcement.",
                    ["current_or_locale_source_discovery"],
                )
            )
            capability_plan.append(
                _deep_capability("current_or_locale_source_discovery", ["search"], "Use Chinese and English broad search for current or locale-sensitive evidence.")
            )

        if complex_query:
            while len(decomposition) < (2 if budget != "deep" else 4):
                sub_id = f"sq{len(decomposition) + 1}"
                if len(decomposition) == 1:
                    sub_question = f"{question} 里有哪些主要选项、说法或路线需要分别验证？"
                    reason = "Complex prompts need explicit comparison targets before final synthesis."
                    caps = ["cross_validation"]
                elif len(decomposition) == 2:
                    sub_question = f"{question} 的成本、风险、限制和适用边界是什么？"
                    reason = "High-difficulty research needs downside and boundary checks."
                    caps = ["low_noise_source_discovery", "page_evidence"]
                else:
                    sub_question = f"基于已抓取证据，{question} 应该如何形成可执行结论？"
                    reason = "A deep budget should reserve one synthesis-oriented gap check subquestion."
                    caps = ["gap_check"]
                decomposition.append(_deep_subquestion(sub_id, sub_question, reason, caps))
            if not has_capability("cross_validation"):
                capability_plan.append(
                    _deep_capability("cross_validation", ["search"], "Compare independent sources before final claims; supplemental tools depend on intent.")
                )
            if budget == "deep" and _contains_any(question, DEEP_EXA_DISCOVERY_KEYWORDS):
                add_step("sq3", "exa-search", "low-noise evidence for tradeoffs and risks", command_exa(f"{question} risks limitations comparison"), next_filename("exa.json"))

        if cross_validation_need == "high":
            if not has_capability("cross_validation"):
                capability_plan.append(
                    _deep_capability("cross_validation", ["search"], "Compare independent sources before final claims; supplemental tools depend on intent.")
                )
            target_subquestion = decomposition[-1]["id"] if decomposition else "sq1"
            cross_validation_tools = next((item["tools"] for item in capability_plan if item.get("capability") == "cross_validation"), [])
            if recency_requirement != "none" or locale_domain_scope == "china" or zh_current_intent:
                if "search" not in cross_validation_tools:
                    cross_validation_tools.append("search")
                if not any(
                    step["tool"] == "search" and "English-language sources" in step.get("purpose", "")
                    for step in steps
                ):
                    add_bilingual_search_steps(target_subquestion, "current or locale-specific cross-source discovery", 2)
            elif docs_intent:
                if "context7-library" not in cross_validation_tools:
                    cross_validation_tools.extend(["context7-library", "context7-docs"])
            elif _contains_any(question, DEEP_EXA_DISCOVERY_KEYWORDS):
                if "exa-search" not in cross_validation_tools:
                    cross_validation_tools.append("exa-search")
                if not any(step["tool"] == "exa-search" for step in steps):
                    add_step(target_subquestion, "exa-search", "official-domain or low-noise cross-source discovery", command_exa(question), next_filename("exa.json"))

        capability_plan.append(_deep_capability("page_evidence", ["fetch"], "Fetch key URLs before claim-level conclusions."))
        add_step("sq1" if len(decomposition) == 1 else decomposition[-1]["id"], "fetch", "fetch key URLs before final claims", command_fetch(), next_filename("fetch.md"))

    for item in capability_plan:
        item["tools"] = [tool for tool in item["tools"] if tool in DEEP_ALLOWED_TOOLS]
    steps = [step for step in steps if step["tool"] in DEEP_ALLOWED_TOOLS]
    if budget == "quick" and len(decomposition) > 2:
        decomposition = decomposition[:2]
    if budget == "quick" and len(steps) > 4:
        limited_steps = steps[:4]
        if not any(step["tool"] == "fetch" for step in limited_steps):
            first_fetch = next((step for step in steps if step["tool"] == "fetch"), None)
            if first_fetch:
                first_fetch = dict(first_fetch)
                fetch_path = _path_join(evidence_root, "04-fetch.md")
                first_fetch["command"] = f"smart-search fetch {_quote_arg('<key-url>')} --format markdown --output {_quote_arg(fetch_path)}"
                first_fetch["output_path"] = fetch_path
                limited_steps = steps[:3] + [first_fetch]
        steps = limited_steps[:4]
    if budget == "quick":
        valid_subquestion_ids = {item["id"] for item in decomposition}
        fallback_subquestion_id = decomposition[-1]["id"] if decomposition else "sq1"
        for index, step in enumerate(steps, start=1):
            step["id"] = f"s{index}"
            if step.get("subquestion_id") not in valid_subquestion_ids:
                step["subquestion_id"] = fallback_subquestion_id

    return {
        "ok": True,
        "mode": "deep_research",
        "query_mode": "research",
        "question": question,
        "trigger_source": "explicit_cli",
        "difficulty": difficulty,
        "intent_signals": intent_signals,
        "decomposition": decomposition,
        "capability_plan": capability_plan,
        "evidence_policy": "fetch_before_claim",
        "preflight": {
            "tool": "doctor",
            "command": "smart-search doctor --format json",
            "when": "configuration or provider availability is uncertain",
            "executed_during_planning": False,
        },
        "steps": steps,
        "gap_check": {
            "required": True,
            "rule": "fetch missing evidence for key claims or downgrade unsupported claims to unverified candidates",
            "unsupported_claim_action": "downgrade_to_unverified_candidate",
        },
        "final_answer_policy": "cite fetched evidence, list unverified candidates, and include key commands",
        "usage_boundary": {
            "search": "smart-search search runs live fast/broad search immediately.",
            "research": "smart-search research builds this plan internally, then runs the staged discover/fetch/synthesis workflow.",
            "execution": "research executes the listed steps with existing CLI commands, then performs gap_check.",
        },
        "allowed_tools": sorted(DEEP_ALLOWED_TOOLS),
        "evidence_dir": evidence_root,
        "elapsed_ms": _elapsed_ms(start),
    }
