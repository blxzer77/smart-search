import hashlib
import re
from typing import Any


def research_evidence_item(
    *,
    url: str,
    provider: str,
    title: str = "",
    content: str = "",
    source_type: str = "fetched_page",
    subquestion_id: str = "",
) -> dict[str, Any]:
    digest = hashlib.sha1(f"{url}\n{provider}\n{title}".encode("utf-8")).hexdigest()[:12]
    return {
        "id": f"e{digest}",
        "url": url,
        "title": title or url,
        "provider": provider,
        "source_type": source_type,
        "subquestion_id": subquestion_id,
        "content": content,
        "content_len": len(content or ""),
        "verified": bool(content and content.strip()),
    }


def citation_items(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence_items:
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append({
            "id": item.get("id", ""),
            "url": url,
            "title": item.get("title") or url,
            "provider": item.get("provider") or "",
            "source_type": item.get("source_type", ""),
            "subquestion_id": item.get("subquestion_id", ""),
            "verified": bool(item.get("verified")),
            "content_len": item.get("content_len", 0),
        })
    return citations


def evidence_only_synthesis(question: str, evidence_items: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> str:
    if not evidence_items:
        return (
            f"未能为 `{question}` 获取可引用的页面正文证据。"
            "本次 research 已停止在降级状态，未对缺证据的结论做断言。"
        )
    lines = [f"Research result for: {question}", ""]
    lines.append("Evidence-backed findings:")
    for index, item in enumerate(evidence_items, 1):
        content = re.sub(r"\s+", " ", (item.get("content") or "").strip())
        excerpt = content[:360]
        lines.append(f"{index}. {item.get('title') or item.get('url')} ({item.get('provider')})")
        if excerpt:
            lines.append(f"   Evidence excerpt: {excerpt}")
        lines.append(f"   Source: {item.get('url')}")
    if gaps:
        lines.extend(["", "Unverified gaps:"])
        for gap in gaps:
            lines.append(f"- {gap.get('subquestion_id', '')}: {gap.get('reason', '')}")
    return "\n".join(lines).strip()


def select_candidate_urls(sources: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        url = (source.get("url") or "").strip()
        if not url or url.startswith("context7:") or url in seen:
            continue
        seen.add(url)
        selected.append(source)
        if len(selected) >= limit:
            break
    return selected
