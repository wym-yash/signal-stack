import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from crawler import list_signals
from db import get_company, get_conn, utc_now
from llm_client import FreeLLMClient
from signal_stack import list_sources


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


def generate_monday_morning_brief(
    company_id: int,
    brief_type: str = "weekly",
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    signals = list_signals(company_id=company_id, limit=80)
    sources = list_sources(company_id=company_id)
    source_map = {s["id"]: s for s in sources}

    compact_signals = [
        {
            "id": sig["id"],
            "category": sig["category"],
            "competitor_name": sig["competitor_name"],
            "title": sig["title"],
            "summary": sig["summary"],
            "evidence_snippet": sig["evidence_snippet"],
            "source_url": sig["source_url"],
            "source_name": source_map.get(sig["source_id"], {}).get("name", sig["source_url"]),
            "published_date": sig["published_date"] or "",
            "discovered_at": sig["discovered_at"],
            "signal_stance": sig["signal_stance"],
            "total_rank_score": sig["total_rank_score"],
            "reliability_score": sig["credibility_score"],
            "evidence_strength_score": sig["evidence_strength_score"],
            "strategic_relevance_score": sig["relevance_score"],
            "verified_status": sig["verified_status"],
            "interpretation": sig["interpretation"],
            "recommended_action": sig["recommended_action"],
        }
        for sig in signals
    ]

    llm_client = llm or FreeLLMClient()
    system_prompt = (
        "You are an executive chief-of-staff intelligence analyst writing a Monday Morning Intelligence Brief "
        "for a founder/CEO. Ground every claim strictly in the provided intelligence signals and company profile. "
        "Never fabricate developments, statistics, dates, or quotes. "
        "If a category (Customer Signals, Competitor Intelligence, Market Intelligence, or Internal Business Intelligence) "
        "has no meaningful development in the provided data, explicitly say so in that category's status note and leave "
        "its list empty—never manufacture filler items. "
        "Clearly distinguish verified facts/evidence from strategic interpretation."
    )
    user_prompt = (
        f"Company: {company['name']} ({company['website']})\n"
        f"Industry: {company.get('industry') or 'Unknown'}\n"
        f"Profile Summary: {company.get('profile_summary') or ''}\n"
        f"Business Context: {company.get('business_context') or ''}\n"
        f"Verified Facts: {json.dumps(company.get('verified_facts', []))}\n"
        f"Assumptions: {json.dumps(company.get('assumptions', []))}\n"
        f"Collected Signals ({len(compact_signals)} total): {json.dumps(compact_signals)}"
    )

    structured = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_model=MondayMorningBriefSchema,
        temperature=0.2,
    )

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