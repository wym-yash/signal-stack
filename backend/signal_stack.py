from io import BytesIO
import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import openpyxl
import pandas as pd
from pydantic import BaseModel, Field
from pypdf import PdfReader

from db import get_company, get_conn, update_business_context, utc_now
from llm_client import FreeLLMClient

VALID_CATEGORIES = ("Customers", "Competitors", "Market", "Internal")


class ProposedSource(BaseModel):
    category: str = Field(description="One of: Customers, Competitors, Market, Internal")
    name: str = Field(description="Concise name of the source, competitor, community, feed, or internal channel.")
    url_or_path: str = Field(
        description="Public URL (https://...) or internal channel/file reference for Internal sources."
    )
    competitor_name: str = Field(
        default="",
        description="If category is Competitors, the competitor/substitute brand name; otherwise empty string.",
    )
    reason: str = Field(
        description=(
            "Clear justification covering specificity to the company's problem space, recency/update cadence, "
            "and credibility for the intelligence type."
        )
    )
    reliability_score: float = Field(default=0.75, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.8, ge=0.0, le=1.0)


class SignalStackPlan(BaseModel):
    sources: list[ProposedSource] = Field(
        min_length=12,
        description=(
            "Curated intelligence sources across Customers, Competitors (include 5-10 distinct competitors/substitutes), "
            "Market, and Internal. Provide at least 20 sources when generating for MeetUniversity or when requested."
        ),
    )


class ContextChangeAssessment(BaseModel):
    change_summary: str = Field(description="Concise summary of what shifted in the company's business context.")
    sources_to_deprecate_ids: list[int] = Field(
        default_factory=list,
        description="Existing source IDs that are now low-relevance or no longer aligned with the updated context.",
    )
    deprecation_explanations: dict[str, str] = Field(
        default_factory=dict,
        description="Map of string source ID -> why that source is less relevant now.",
    )
    new_sources: list[ProposedSource] = Field(
        default_factory=list,
        description="New sources recommended to cover the updated business context.",
    )


class ExtractedInternalSignal(BaseModel):
    title: str
    summary: str
    evidence_snippet: str
    signal_stance: str = Field(default="neutral", description="opportunity, threat, or neutral")
    impact_score: float = Field(default=0.65, ge=0.0, le=1.0)
    urgency_score: float = Field(default=0.6, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.8, ge=0.0, le=1.0)
    interpretation: str = Field(default="")
    recommended_action: str = Field(default="")


class InternalFileExtractionResult(BaseModel):
    signals: list[ExtractedInternalSignal] = Field(default_factory=list)


def list_sources(company_id: int, category: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM sources WHERE company_id = ?"
    params: list[Any] = [company_id]
    if category:
        query += " AND category = ?"
        params.append(category)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id ASC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def add_source(
    company_id: int,
    category: str,
    name: str,
    url_or_path: str,
    reason: str,
    status: str = "approved",
    reliability_score: float = 0.75,
    relevance_score: float = 0.75,
) -> dict[str, Any]:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Expected one of {VALID_CATEGORIES}.")
    if not name.strip() or not url_or_path.strip() or not reason.strip():
        raise ValueError("Source name, url_or_path, and reason are all required.")

    now = utc_now()
    with get_conn() as conn:
        # Avoid duplicate exact URL/path for the same company + category
        existing = conn.execute(
            """
            SELECT * FROM sources
            WHERE company_id = ? AND category = ? AND lower(url_or_path) = lower(?)
            """,
            (company_id, category, url_or_path.strip()),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE sources
                SET name = ?, reason = ?, status = ?, reliability_score = ?, relevance_score = ?
                WHERE id = ?
                """,
                (name.strip(), reason.strip(), status, reliability_score, relevance_score, existing["id"]),
            )
            row = conn.execute("SELECT * FROM sources WHERE id = ?", (existing["id"],)).fetchone()
            return dict(row)

        cur = conn.execute(
            """
            INSERT INTO sources (
                company_id, category, name, url_or_path, reason, status,
                reliability_score, relevance_score, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                category,
                name.strip(),
                url_or_path.strip(),
                reason.strip(),
                status,
                reliability_score,
                relevance_score,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def update_source_status(company_id: int, source_id: int, status: str) -> Optional[dict[str, Any]]:
    allowed = {"pending", "approved", "inactive", "removed"}
    if status not in allowed:
        raise ValueError(f"Invalid status '{status}'. Must be one of {allowed}.")
    with get_conn() as conn:
        conn.execute(
            "UPDATE sources SET status = ? WHERE id = ? AND company_id = ?",
            (status, source_id, company_id),
        )
        row = conn.execute("SELECT * FROM sources WHERE id = ? AND company_id = ?", (source_id, company_id)).fetchone()
        return dict(row) if row else None


def remove_source(company_id: int, source_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM sources WHERE id = ? AND company_id = ?", (source_id, company_id))
        return cur.rowcount > 0


def _interview_digest(company_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT question_index, is_followup, question_text, answer_text, skipped
            FROM interview_messages
            WHERE company_id = ?
            ORDER BY question_index ASC, is_followup ASC, id ASC
            """,
            (company_id,),
        ).fetchall()
        return [
            {
                "q": r["question_text"],
                "answer": "[SKIPPED]" if r["skipped"] else r["answer_text"],
            }
            for r in rows
            if r["skipped"] or (r["answer_text"] or "").strip()
        ]


def generate_signal_stack(
    company_id: int,
    min_sources: int = 20,
    llm: Optional[FreeLLMClient] = None,
) -> list[dict[str, Any]]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    llm_client = llm or FreeLLMClient()
    qna = _interview_digest(company_id)

    system_prompt = (
        "You are a competitive & market intelligence architect building a Signal Stack. "
        "Generate tailored, legitimate, public and internal intelligence sources across four categories: "
        "Customers, Competitors, Market, and Internal. "
        "Rules:\n"
        "1. Include 5 to 10 distinct competitors or substitutes in 'Competitors' with real public URLs (homepage/news/blog/careers/product pages).\n"
        "2. In 'Customers', include public community/discussion/review/forum/Q&A URLs where target customers discuss problems, alternatives, and expectations—not just company mentions.\n"
        "3. In 'Market', include credible regulatory, policy, industry report, or sector news URLs relevant to the company.\n"
        "4. In 'Internal', include internal intelligence channels/upload slots (e.g., CRM exports, sales call notes, support tickets, student/customer feedback logs).\n"
        "5. Every source MUST have a specific, credible, recency-aware 'reason' explaining why it matters to this exact company.\n"
        "6. Never invent fake URLs—only use real, well-known public domains/URLs or clearly labeled internal upload descriptors."
    )

    user_prompt = (
        f"Company: {company['name']}\n"
        f"Website: {company['website']}\n"
        f"Industry: {company.get('industry') or 'Unknown'}\n"
        f"Profile Summary: {company.get('profile_summary') or 'None'}\n"
        f"Business Context: {company.get('business_context') or 'None'}\n"
        f"Verified Facts: {json.dumps(company.get('verified_facts', []))}\n"
        f"Assumptions: {json.dumps(company.get('assumptions', []))}\n"
        f"Interview Q&A: {json.dumps(qna)}\n\n"
        f"Generate at least {min_sources} total sources across Customers, Competitors (5-10), Market, and Internal."
    )

    plan = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_model=SignalStackPlan,
        temperature=0.3,
    )

    saved: list[dict[str, Any]] = []
    for src in plan.sources:
        cat = src.category if src.category in VALID_CATEGORIES else "Market"
        display_name = (
            f"{src.competitor_name.strip()} — {src.name.strip()}"
            if cat == "Competitors" and src.competitor_name.strip() and src.competitor_name.strip().lower() not in src.name.lower()
            else src.name.strip()
        )
        saved.append(
            add_source(
                company_id=company_id,
                category=cat,
                name=display_name,
                url_or_path=src.url_or_path.strip(),
                reason=src.reason.strip(),
                status="approved",
                reliability_score=src.reliability_score,
                relevance_score=src.relevance_score,
            )
        )

    return list_sources(company_id)


def reassess_signal_stack_on_context_change(
    company_id: int,
    new_business_context: str,
    change_summary: str = "",
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    llm_client = llm or FreeLLMClient()
    current_sources = list_sources(company_id)

    updated_company = update_business_context(
        company_id=company_id,
        new_context=new_business_context,
        change_summary=change_summary or "Business context updated",
    )

    compact_sources = [
        {
            "id": s["id"],
            "category": s["category"],
            "name": s["name"],
            "url_or_path": s["url_or_path"],
            "reason": s["reason"],
            "status": s["status"],
        }
        for s in current_sources
        if s["status"] != "removed"
    ]

    system_prompt = (
        "You are re-evaluating an existing Signal Stack because the company's business context changed. "
        "Identify existing source IDs that are no longer relevant or lower priority, explain why, "
        "and propose replacement/additional sources aligned with the new business context."
    )
    user_prompt = (
        f"Company: {company['name']} ({company['website']})\n"
        f"Previous Business Context: {company.get('business_context') or ''}\n"
        f"New Business Context: {new_business_context}\n"
        f"Change Note: {change_summary or 'N/A'}\n"
        f"Current Sources: {json.dumps(compact_sources)}"
    )

    assessment = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_model=ContextChangeAssessment,
        temperature=0.25,
    )

    deprecated_ids = set(assessment.sources_to_deprecate_ids)
    for sid in deprecated_ids:
        update_source_status(company_id=company_id, source_id=sid, status="inactive")

    added_sources: list[dict[str, Any]] = []
    for new_src in assessment.new_sources:
        cat = new_src.category if new_src.category in VALID_CATEGORIES else "Market"
        added_sources.append(
            add_source(
                company_id=company_id,
                category=cat,
                name=new_src.name,
                url_or_path=new_src.url_or_path,
                reason=f"[Updated Context] {new_src.reason}",
                status="approved",
                reliability_score=new_src.reliability_score,
                relevance_score=new_src.relevance_score,
            )
        )

    return {
        "company": updated_company,
        "change_summary": assessment.change_summary,
        "deactivated_source_ids": sorted(deprecated_ids),
        "deprecation_explanations": assessment.deprecation_explanations,
        "added_sources": added_sources,
        "active_signal_stack": list_sources(company_id),
    }


def _extract_text_from_bytes(filename: str, content: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".txt" or ext == ".md":
        return content.decode("utf-8", errors="replace")
    if ext == ".csv":
        df = pd.read_csv(BytesIO(content))
        return df.to_string(index=False)
    if ext in (".xlsx", ".xls"):
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        parts: list[str] = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            rows = []
            for row in ws.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    rows.append(" | ".join("" if cell is None else str(cell) for cell in row))
            if rows:
                parts.append(f"--- Sheet: {sheet} ---\n" + "\n".join(rows))
        return "\n\n".join(parts)
    if ext == ".pdf":
        reader = PdfReader(BytesIO(content))
        pages_text = []
        for i, page in enumerate(reader.pages, start=1):
            txt = (page.extract_text() or "").strip()
            if txt:
                pages_text.append(f"--- Page {i} ---\n{txt}")
        return "\n\n".join(pages_text)
    raise ValueError(f"Unsupported file type '{ext}'. Supported formats: CSV, XLSX, XLS, PDF, TXT.")


def ingest_internal_file(
    company_id: int,
    filename: str,
    content: bytes,
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    raw_text = _extract_text_from_bytes(filename, content).strip()
    if not raw_text:
        raise ValueError(f"No readable text found in '{filename}'.")

    # Register/update this internal file as an approved Internal source
    internal_src = add_source(
        company_id=company_id,
        category="Internal",
        name=f"Internal Upload: {filename}",
        url_or_path=f"internal://{filename}",
        reason=f"Uploaded internal dataset/document ({filename}) analyzed for objections, churn/lost deals, requests, and risks.",
        status="approved",
        reliability_score=0.9,
        relevance_score=0.88,
    )

    llm_client = llm or FreeLLMClient()
    system_prompt = (
        "You are an internal business intelligence analyst. Extract distinct, evidence-backed signals "
        "from uploaded internal files (CRM notes, support logs, call transcripts, feedback sheets, reports). "
        "Focus on recurring customer objections, lost-deal reasons, product requests, sales patterns, and risks. "
        "Quote or closely ground 'evidence_snippet' in the provided text—never fabricate facts."
    )
    user_prompt = (
        f"Company: {company['name']}\n"
        f"Business Context: {company.get('business_context') or 'N/A'}\n"
        f"Filename: {filename}\n"
        f"Content:\n{raw_text[:14000]}"
    )

    extracted = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_model=InternalFileExtractionResult,
        temperature=0.2,
    )

    from crawler import save_ranked_signal

    inserted_signals: list[dict[str, Any]] = []
    for idx, item in enumerate(extracted.signals, start=1):
        stance = item.signal_stance if item.signal_stance in ("opportunity", "threat", "neutral") else "neutral"
        sig = save_ranked_signal(
            company_id=company_id,
            source_id=internal_src["id"],
            category="Internal",
            competitor_name="",
            title=item.title,
            summary=item.summary,
            evidence_snippet=item.evidence_snippet,
            source_url=f"internal://{filename}#item-{idx}",
            published_date=None,
            signal_stance=stance,
            relevance_score=item.relevance_score,
            impact_score=item.impact_score,
            urgency_score=item.urgency_score,
            credibility_score=0.9,
            recency_score=0.85,
            novelty_score=0.75,
            evidence_strength_score=0.85,
            verified_status="verified",
            interpretation=item.interpretation,
            recommended_action=item.recommended_action,
        )
        inserted_signals.append(sig)

    parsed_host = urlparse(company["website"]).netloc
    return {
        "source": internal_src,
        "company_domain": parsed_host,
        "extracted_count": len(inserted_signals),
        "signals": inserted_signals,
    }