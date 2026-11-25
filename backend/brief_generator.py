import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from crawler import list_signals
from db import get_company, get_conn, utc_now
from llm_client import FreeLLMClient
from signal_stack import list_sources

MAX_SIGNALS_FOR_BRIEF = 10
MAX_SUMMARY_CHARS = 240
MAX_SNIPPET_CHARS = 200
MAX_CONTEXT_CHARS = 900
MAX_PROFILE_CHARS = 600


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


class ExecutiveTopItem(BaseModel):
    headline: str
    why_it_matters: str
    evidence_link: str
    verification_status: str


class OpportunityItem(BaseModel):
    title: str
    evidence: str
    impact: str
    next_step: str
    priority: str = Field(description="High, Medium, or Low")


class RiskThreatItem(BaseModel):
    title: str
    evidence: str
    possible_impact: str
    urgency: str = Field(description="High, Medium, or Low")


class RecommendedActionItem(BaseModel):
    action: str
    reason: str
    suggested_owner: str
    priority: str = Field(description="P1, P2, or P3")


class WatchlistItem(BaseModel):
    topic: str
    early_signal: str
    what_to_watch_next: str


class AppendixEntry(BaseModel):
    source_name: str
    direct_link: str
    published_date: str
    discovery_date: str
    evidence_snippet: str
    verification_status: str
    reliability_score: float
    evidence_strength_score: float
    strategic_relevance_score: float


class MondayMorningBriefSchema(BaseModel):
    title: str
    executive_summary: list[ExecutiveTopItem] = Field(
        default_factory=list,
        description="Up to the 5 most important developments leadership should know.",
    )
    customer_signals_status_note: str = Field(
        default="",
        description="Explicitly note if no meaningful customer signal occurred; otherwise summarize.",
    )
    customer_signals: list[str] = Field(default_factory=list)

    competitor_intelligence_status_note: str = Field(
        default="",
        description="Explicitly note if no meaningful competitor development occurred; otherwise summarize.",
    )
    competitor_intelligence: list[str] = Field(default_factory=list)

    market_intelligence_status_note: str = Field(
        default="",
        description="Explicitly note if no meaningful market development occurred; otherwise summarize.",
    )
    market_intelligence: list[str] = Field(default_factory=list)

    internal_intelligence_status_note: str = Field(
        default="",
        description="Explicitly note if no meaningful internal signal occurred; otherwise summarize.",
    )
    internal_intelligence: list[str] = Field(default_factory=list)

    opportunities: list[OpportunityItem] = Field(default_factory=list)
    opportunities_note: str = Field(default="")

    risks_and_threats: list[RiskThreatItem] = Field(default_factory=list)
    risks_note: str = Field(default="")

    recommended_actions: list[RecommendedActionItem] = Field(default_factory=list)
    watch_list: list[WatchlistItem] = Field(default_factory=list)
    source_appendix: list[AppendixEntry] = Field(default_factory=list)


def _render_brief_markdown(company_name: str, data: MondayMorningBriefSchema) -> str:
    lines: list[str] = [
        f"# {data.title or f'{company_name} — Monday Morning Intelligence Brief'}",
        "",
        "## 1. Executive Summary",
    ]
    if data.executive_summary:
        for idx, item in enumerate(data.executive_summary[:5], start=1):
            lines.append(
                f"{idx}. **{item.headline}** ({item.verification_status}) — {item.why_it_matters} "
                f"[Source]({item.evidence_link})"
            )
    else:
        lines.append("No high-priority developments were recorded in the current intelligence window.")

    sections = [
        ("## 2. Customer Signals", data.customer_signals_status_note, data.customer_signals),
        ("## 3. Competitor Intelligence", data.competitor_intelligence_status_note, data.competitor_intelligence),
        ("## 4. Market Intelligence", data.market_intelligence_status_note, data.market_intelligence),
        ("## 5. Internal Business Intelligence", data.internal_intelligence_status_note, data.internal_intelligence),
    ]
    for heading, note, bullets in sections:
        lines.extend(["", heading])
        if note:
            lines.append(f"*{note}*")
        if bullets:
            for b in bullets:
                lines.append(f"- {b}")
        elif not note:
            lines.append("No meaningful developments recorded in this category for this period.")

    lines.extend(["", "## 6. Opportunities Identified"])
    if data.opportunities_note:
        lines.append(f"*{data.opportunities_note}*")
    if data.opportunities:
        for opp in data.opportunities:
            lines.append(
                f"- **[{opp.priority}] {opp.title}**: {opp.impact} "
                f"(Evidence: {opp.evidence} | Next step: {opp.next_step})"
            )
    else:
        lines.append("No verified opportunities identified from current signals.")

    lines.extend(["", "## 7. Risks & Threats"])
    if data.risks_note:
        lines.append(f"*{data.risks_note}*")
    if data.risks_and_threats:
        for risk in data.risks_and_threats:
            lines.append(
                f"- **[Urgency: {risk.urgency}] {risk.title}**: {risk.possible_impact} "
                f"(Evidence: {risk.evidence})"
            )
    else:
        lines.append("No material risks or threats flagged from current signals.")

    lines.extend(["", "## 8. Recommended Actions for This Week"])
    if data.recommended_actions:
        for act in data.recommended_actions:
            lines.append(
                f"- **[{act.priority}] {act.action}** — *Owner:* {act.suggested_owner} | *Why:* {act.reason}"
            )
    else:
        lines.append("No immediate weekly actions required beyond continuing source monitoring.")

    lines.extend(["", "## 9. What We Should Watch"])
    if data.watch_list:
        for w in data.watch_list:
            lines.append(
                f"- **{w.topic}**: {w.early_signal} — *Watch next:* {w.what_to_watch_next}"
            )
    else:
        lines.append("No early watchlist items recorded yet.")

    lines.extend(["", "## 10. Source Appendix"])
    if data.source_appendix:
        for entry in data.source_appendix:
            lines.append(
                f"- **{entry.source_name}** ([Link]({entry.direct_link})) | "
                f"Published: {entry.published_date or 'N/A'} | Discovered: {entry.discovery_date} | "
                f"Status: `{entry.verification_status}` | "
                f"Scores (Reliability: {entry.reliability_score:.2f}, Evidence: {entry.evidence_strength_score:.2f}, "
                f"Relevance: {entry.strategic_relevance_score:.2f}) | "
                f"Evidence: *\"{entry.evidence_snippet}\"*"
            )
    else:
        lines.append("No source evidence records available yet.")

    return "\n".join(lines).strip()


def _build_fallback_brief(
    company: dict[str, Any],
    compact_signals: list[dict[str, Any]],
    reason: str,
) -> MondayMorningBriefSchema:
    company_name = company["name"]
    exec_items: list[ExecutiveTopItem] = []
    opportunities: list[OpportunityItem] = []
    risks: list[RiskThreatItem] = []
    actions: list[RecommendedActionItem] = []
    watch_items: list[WatchlistItem] = []
    appendix: list[AppendixEntry] = []

    by_category: dict[str, list[str]] = {
        "Customers": [],
        "Competitors": [],
        "Market": [],
        "Internal": [],
    }

    for sig in compact_signals[:MAX_SIGNALS_FOR_BRIEF]:
        title = _clip(sig.get("title") or "Recorded signal", 90)
        summary = _clip(sig.get("summary") or sig.get("evidence_snippet") or "", 180)
        snippet = _clip(sig.get("evidence_snippet") or summary, 160)
        url = sig.get("source_url") or company.get("website") or ""
        source_name = _clip(sig.get("source_name") or url or "Signal Source", 70)
        status = sig.get("verified_status") or "unverified"
        cat = sig.get("category") or "Market"

        if len(exec_items) < 5:
            exec_items.append(
                ExecutiveTopItem(
                    headline=title,
                    why_it_matters=summary or f"Recorded under {cat} for {company_name}.",
                    evidence_link=url,
                    verification_status=status,
                )
            )

        bullet = f"{title}: {summary}" if summary else title
        if cat in by_category and len(by_category[cat]) < 3:
            by_category[cat].append(bullet)

        stance = (sig.get("signal_stance") or "neutral").lower()
        if stance == "opportunity" and len(opportunities) < 3:
            opportunities.append(
                OpportunityItem(
                    title=title,
                    evidence=snippet or title,
                    impact=summary or f"Potential upside in {cat}.",
                    next_step=_clip(sig.get("recommended_action") or "Validate with product and GTM leads.", 120),
                    priority="Medium",
                )
            )
        elif stance == "threat" and len(risks) < 3:
            risks.append(
                RiskThreatItem(
                    title=title,
                    evidence=snippet or title,
                    possible_impact=summary or f"Potential competitive or market risk in {cat}.",
                    urgency="Medium",
                )
            )

        if len(actions) < 3:
            actions.append(
                RecommendedActionItem(
                    action=_clip(sig.get("recommended_action") or f"Review '{title}' and verify source details", 120),
                    reason=summary or f"High-ranked signal in {cat}.",
                    suggested_owner="Strategy / Product Lead",
                    priority="P2",
                )
            )

        if len(watch_items) < 3:
            watch_items.append(
                WatchlistItem(
                    topic=title,
                    early_signal=snippet or summary or title,
                    what_to_watch_next="Track follow-up announcements, customer reaction, and competitor responses.",
                )
            )

        appendix.append(
            AppendixEntry(
                source_name=source_name,
                direct_link=url,
                published_date=str(sig.get("published_date") or ""),
                discovery_date=str(sig.get("discovered_at") or ""),
                evidence_snippet=snippet,
                verification_status=status,
                reliability_score=float(sig.get("reliability_score") or 0.5),
                evidence_strength_score=float(sig.get("evidence_strength_score") or 0.5),
                strategic_relevance_score=float(sig.get("strategic_relevance_score") or 0.5),
            )
        )

    fallback_note = f"Fallback brief generated from stored signals ({_clip(reason, 120)})."

    return MondayMorningBriefSchema(
        title=f"{company_name} — Monday Morning Intelligence Brief",
        executive_summary=exec_items,
        customer_signals_status_note="" if by_category["Customers"] else f"No meaningful customer signals in current window. {fallback_note}",
        customer_signals=by_category["Customers"],
        competitor_intelligence_status_note="" if by_category["Competitors"] else f"No meaningful competitor signals in current window. {fallback_note}",
        competitor_intelligence=by_category["Competitors"],
        market_intelligence_status_note="" if by_category["Market"] else f"No meaningful market signals in current window. {fallback_note}",
        market_intelligence=by_category["Market"],
        internal_intelligence_status_note="" if by_category["Internal"] else f"No meaningful internal signals in current window. {fallback_note}",
        internal_intelligence=by_category["Internal"],
        opportunities=opportunities,
        opportunities_note="" if opportunities else fallback_note,
        risks_and_threats=risks,
        risks_note="" if risks else fallback_note,
        recommended_actions=actions,
        watch_list=watch_items,
        source_appendix=appendix,
    )


def generate_monday_morning_brief(
    company_id: int,
    brief_type: str = "weekly",
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    signals = list_signals(company_id=company_id, limit=MAX_SIGNALS_FOR_BRIEF)
    sources = list_sources(company_id=company_id)
    source_map = {s["id"]: s for s in sources}

    compact_signals = [
        {
            "id": sig["id"],
            "category": sig["category"],
            "competitor_name": _clip(sig.get("competitor_name"), 50),
            "title": _clip(sig.get("title"), 95),
            "summary": _clip(sig.get("summary"), MAX_SUMMARY_CHARS),
            "evidence_snippet": _clip(sig.get("evidence_snippet"), MAX_SNIPPET_CHARS),
            "source_url": sig.get("source_url") or "",
            "source_name": _clip(source_map.get(sig["source_id"], {}).get("name", sig.get("source_url") or ""), 60),
            "published_date": sig.get("published_date") or "",
            "discovered_at": sig.get("discovered_at") or "",
            "signal_stance": sig.get("signal_stance") or "neutral",
            "total_rank_score": round(float(sig.get("total_rank_score") or 0.0), 3),
            "reliability_score": round(float(sig.get("credibility_score") or 0.5), 2),
            "evidence_strength_score": round(float(sig.get("evidence_strength_score") or 0.5), 2),
            "strategic_relevance_score": round(float(sig.get("relevance_score") or 0.5), 2),
            "verified_status": sig.get("verified_status") or "unverified",
            "interpretation": _clip(sig.get("interpretation"), 140),
            "recommended_action": _clip(sig.get("recommended_action"), 140),
        }
        for sig in signals
    ]

    llm_client = llm or FreeLLMClient()
    system_prompt = (
        "You are an executive chief-of-staff intelligence analyst writing a concise Monday Morning Intelligence Brief. "
        "Ground every claim strictly in the provided signals and company profile. "
        "Never fabricate facts, numbers, dates, or quotes. "
        "If a category has no meaningful item in the provided signals, note that briefly and keep its list empty."
    )
    user_prompt = (
        f"Company: {_clip(company['name'], 80)} ({_clip(company['website'], 100)})\n"
        f"Industry: {_clip(company.get('industry') or 'Unknown', 80)}\n"
        f"Profile Summary: {_clip(company.get('profile_summary') or '', MAX_PROFILE_CHARS)}\n"
        f"Business Context: {_clip(company.get('business_context') or '', MAX_CONTEXT_CHARS)}\n"
        f"Verified Facts: {json.dumps([_clip(x, 120) for x in (company.get('verified_facts') or [])[:6]])}\n"
        f"Assumptions: {json.dumps([_clip(x, 120) for x in (company.get('assumptions') or [])[:6]])}\n"
        f"Top Signals ({len(compact_signals)}): {json.dumps(compact_signals)}"
    )

    try:
        structured = llm_client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=MondayMorningBriefSchema,
            temperature=0.2,
        )
    except Exception as exc:
        structured = _build_fallback_brief(company, compact_signals, str(exc))

    markdown_content = _render_brief_markdown(company["name"], structured)
    now = utc_now()

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO briefs (company_id, brief_type, markdown_content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (company_id, brief_type, markdown_content, now),
        )
        row = conn.execute("SELECT * FROM briefs WHERE id = ?", (cur.lastrowid,)).fetchone()
        return {
            "brief": dict(row),
            "structured": structured.model_dump(),
        }


def list_briefs(company_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM briefs WHERE company_id = ? ORDER BY id DESC",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]