import hashlib
import json
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
import trafilatura

from db import get_company, get_conn, utc_now
from llm_client import FreeLLMClient

BOT_USER_AGENT = "SignalStackBot/1.0 (+https://github.com/example/signal-stack)"


class ExtractedDevelopment(BaseModel):
    title: str = Field(description="Concise headline of a real development found in the fetched source text.")
    summary: str = Field(description="What happened, grounded strictly in the fetched source text.")
    evidence_snippet: str = Field(description="Direct short excerpt or exact factual detail from the fetched text.")
    competitor_name: str = Field(default="", description="Competitor name if relevant, else empty string.")
    published_date: str = Field(default="", description="Publication/event date if stated in text, else empty string.")
    signal_stance: str = Field(default="neutral", description="opportunity, threat, or neutral")
    relevance_score: float = Field(default=0.7, ge=0.0, le=1.0)
    impact_score: float = Field(default=0.65, ge=0.0, le=1.0)
    urgency_score: float = Field(default=0.55, ge=0.0, le=1.0)
    novelty_score: float = Field(default=0.75, ge=0.0, le=1.0)
    evidence_strength_score: float = Field(default=0.7, ge=0.0, le=1.0)
    verified_status: str = Field(
        default="partially_verified",
        description="verified, partially_verified, or unverified based strictly on direct text evidence.",
    )
    interpretation: str = Field(
        description="Strategic interpretation of why this matters to the company (clearly distinct from raw facts)."
    )
    recommended_action: str = Field(default="", description="Concrete suggested action for leadership.")


class SourceExtractionBatch(BaseModel):
    developments: list[ExtractedDevelopment] = Field(
        default_factory=list,
        description="Zero or more real developments extracted from the source text. Return [] if nothing meaningful is present.",
    )


def compute_rank_score(
    relevance: float,
    impact: float,
    urgency: float,
    credibility: float,
    recency: float,
    novelty: float,
) -> float:
    weighted = (
        0.24 * relevance
        + 0.24 * impact
        + 0.16 * urgency
        + 0.14 * credibility
        + 0.12 * recency
        + 0.10 * novelty
    )
    return round(weighted * 100.0, 2)


def is_allowed_by_robots(url: str, timeout: float = 6.0) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": BOT_USER_AGENT}) as client:
            resp = client.get(robots_url)
            if resp.status_code >= 400:
                # If robots.txt doesn't exist or isn't served, allow public HTTP fetch cautiously
                return True
            rp.parse(resp.text.splitlines())
            return rp.can_fetch(BOT_USER_AGENT, url) or rp.can_fetch("*", url)
    except Exception:
        return True


def fetch_source_content(url: str, timeout: float = 12.0) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "status_code": None, "text": "", "error": "Non-HTTP URL"}

    if not is_allowed_by_robots(url):
        return {"ok": False, "status_code": 403, "text": "", "error": "Blocked by robots.txt"}

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": BOT_USER_AGENT},
        ) as client:
            resp = client.get(url)
            status = resp.status_code
            if status >= 400:
                return {"ok": False, "status_code": status, "text": "", "error": f"HTTP {status}"}

            html = resp.text or ""
            text = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
            if not text and html:
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "noscript", "svg"]):
                    tag.decompose()
                text = " ".join(soup.get_text(" ", strip=True).split())

            return {"ok": True, "status_code": status, "text": text[:12000], "error": ""}
    except Exception as exc:
        return {"ok": False, "status_code": None, "text": "", "error": str(exc)}


def save_ranked_signal(
    company_id: int,
    source_id: Optional[int],
    category: str,
    title: str,
    summary: str,
    evidence_snippet: str,
    source_url: str,
    competitor_name: str = "",
    published_date: Optional[str] = None,
    signal_stance: str = "neutral",
    relevance_score: float = 0.6,
    impact_score: float = 0.6,
    urgency_score: float = 0.5,
    credibility_score: float = 0.7,
    recency_score: float = 0.6,
    novelty_score: float = 0.7,
    evidence_strength_score: float = 0.65,
    verified_status: str = "partially_verified",
    interpretation: str = "",
    recommended_action: str = "",
) -> dict[str, Any]:
    canonical_key = f"{category.lower()}|{title.strip().lower()}|{evidence_snippet.strip().lower()[:240]}"
    content_hash = hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()

    rank_score = compute_rank_score(
        relevance=relevance_score,
        impact=impact_score,
        urgency=urgency_score,
        credibility=credibility_score,
        recency=recency_score,
        novelty=novelty_score,
    )

    stance = signal_stance if signal_stance in ("opportunity", "threat", "neutral") else "neutral"
    v_status = (
        verified_status
        if verified_status in ("verified", "partially_verified", "unverified")
        else "partially_verified"
    )
    now = utc_now()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO signals (
                company_id, source_id, category, competitor_name, title, summary,
                evidence_snippet, source_url, published_date, discovered_at, content_hash,
                signal_stance, relevance_score, impact_score, urgency_score,
                credibility_score, recency_score, novelty_score, evidence_strength_score,
                total_rank_score, verified_status, interpretation, recommended_action
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, content_hash) DO UPDATE SET
                discovered_at = excluded.discovered_at,
                total_rank_score = MAX(signals.total_rank_score, excluded.total_rank_score),
                novelty_score = MIN(signals.novelty_score, 0.35)
            """,
            (
                company_id,
                source_id,
                category,
                competitor_name.strip(),
                title.strip(),
                summary.strip(),
                evidence_snippet.strip(),
                source_url.strip(),
                published_date.strip() if published_date else None,
                now,
                content_hash,
                stance,
                relevance_score,
                impact_score,
                urgency_score,
                credibility_score,
                recency_score,
                novelty_score,
                evidence_strength_score,
                rank_score,
                v_status,
                interpretation.strip(),
                recommended_action.strip(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM signals WHERE company_id = ? AND content_hash = ?",
            (company_id, content_hash),
        ).fetchone()
        return dict(row)


def crawl_company_sources(
    company_id: int,
    max_sources: int = 25,
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    llm_client = llm or FreeLLMClient()
    now = utc_now()

    with get_conn() as conn:
        source_rows = conn.execute(
            """
            SELECT * FROM sources
            WHERE company_id = ? AND status = 'approved' AND category != 'Internal'
            ORDER BY id ASC
            LIMIT ?
            """,
            (company_id, max_sources),
        ).fetchall()

    sources = [dict(r) for r in source_rows]
    sources_checked = 0
    sources_failed = 0
    new_or_updated_signals: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for src in sources:
        sources_checked += 1
        fetch_res = fetch_source_content(src["url_or_path"])

        if not fetch_res["ok"] or not fetch_res["text"].strip():
            sources_failed += 1
            err_msg = fetch_res["error"] or "Empty text extracted"
            errors.append({"source_id": src["id"], "url": src["url_or_path"], "error": err_msg})
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE sources
                    SET last_checked_at = ?, last_status_code = ?,
                        consecutive_failures = consecutive_failures + 1
                    WHERE id = ?
                    """,
                    (now, fetch_res["status_code"], src["id"]),
                )
            continue

        with get_conn() as conn:
            conn.execute(
                """
                UPDATE sources
                SET last_checked_at = ?, last_status_code = ?, consecutive_failures = 0
                WHERE id = ?
                """,
                (now, fetch_res["status_code"], src["id"]),
            )

        system_prompt = (
            "You are a precision business intelligence extractor. Extract ONLY real developments "
            "explicitly supported by the provided fetched webpage text. Never fabricate events, dates, "
            "or quotes. Keep 'summary' factual and put strategic analysis in 'interpretation'. "
            "If the page contains only navigation or generic boilerplate with no meaningful signal, return an empty list."
        )
        user_prompt = (
            f"Target Company: {company['name']} ({company['website']})\n"
            f"Business Context: {company.get('business_context') or 'N/A'}\n"
            f"Source Category: {src['category']}\n"
            f"Source Name: {src['name']}\n"
            f"Source URL: {src['url_or_path']}\n"
            f"Source Reason: {src['reason']}\n\n"
            f"Fetched Text:\n{fetch_res['text']}"
        )

        try:
            batch = llm_client.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=SourceExtractionBatch,
                temperature=0.2,
            )
            for dev in batch.developments:
                sig = save_ranked_signal(
                    company_id=company_id,
                    source_id=src["id"],
                    category=src["category"],
                    competitor_name=dev.competitor_name,
                    title=dev.title,
                    summary=dev.summary,
                    evidence_snippet=dev.evidence_snippet,
                    source_url=src["url_or_path"],
                    published_date=dev.published_date or None,
                    signal_stance=dev.signal_stance,
                    relevance_score=dev.relevance_score,
                    impact_score=dev.impact_score,
                    urgency_score=dev.urgency_score,
                    credibility_score=float(src["reliability_score"]),
                    recency_score=dev.novelty_score,
                    novelty_score=dev.novelty_score,
                    evidence_strength_score=dev.evidence_strength_score,
                    verified_status=dev.verified_status,
                    interpretation=dev.interpretation,
                    recommended_action=dev.recommended_action,
                )
                new_or_updated_signals.append(sig)
        except Exception as exc:
            sources_failed += 1
            errors.append({"source_id": src["id"], "url": src["url_or_path"], "error": f"LLM extraction failed: {exc}"})

    return {
        "company_id": company_id,
        "sources_checked": sources_checked,
        "sources_failed": sources_failed,
        "signals_processed": len(new_or_updated_signals),
        "errors": errors,
        "signals": new_or_updated_signals,
    }


def list_signals(
    company_id: int,
    category: Optional[str] = None,
    competitor_name: Optional[str] = None,
    verified_status: Optional[str] = None,
    min_rank_score: Optional[float] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM signals WHERE company_id = ?"
    params: list[Any] = [company_id]

    if category:
        query += " AND category = ?"
        params.append(category)
    if competitor_name:
        query += " AND lower(competitor_name) LIKE lower(?)"
        params.append(f"%{competitor_name.strip()}%")
    if verified_status:
        query += " AND verified_status = ?"
        params.append(verified_status)
    if min_rank_score is not None:
        query += " AND total_rank_score >= ?"
        params.append(min_rank_score)

    query += " ORDER BY total_rank_score DESC, discovered_at DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["signals_breakdown"] = json.dumps({
                "relevance": d["relevance_score"],
                "impact": d["impact_score"],
                "urgency": d["urgency_score"],
                "credibility": d["credibility_score"],
                "recency": d["recency_score"],
                "novelty": d["novelty_score"],
                "evidence_strength": d["evidence_strength_score"],
            })
            out.append(d)
        return out