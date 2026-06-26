from typing import Any


def is_http_evidence_url(url: str) -> bool:
    normalized = (url or "").strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")


def http_fetched_evidence_items(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in evidence_items
        if is_http_evidence_url(str(item.get("url") or "")) and bool(item.get("verified"))
    ]


def research_gap_status(
    evidence_items: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    *,
    signals: dict[str, Any] | None = None,
) -> tuple[str, str]:
    http_evidence = http_fetched_evidence_items(evidence_items)
    if not evidence_items:
        return "failed", "provider_exhausted"
    if not http_evidence:
        if not gaps:
            gaps.append(
                {
                    "subquestion_id": "",
                    "reason": "only docs or discovery evidence without fetched HTTP page content",
                }
            )
        return "failed", "docs_only_without_fetch"
    if signals and signals.get("cross_validation_need") == "high" and len(http_evidence) < 2:
        gaps.append(
            {
                "subquestion_id": "",
                "reason": "high-risk query requires at least two fetched HTTP evidence items",
            }
        )
        return "degraded", "high_risk_needs_more_fetch"
    if gaps:
        return "degraded", "degraded_with_gaps"
    return "closed", "evidence_converged"
