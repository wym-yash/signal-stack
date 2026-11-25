import json
from typing import Any, Optional
from urllib.parse import urlparse

from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel, Field

from brief_generator import generate_monday_morning_brief
from crawler import crawl_company_sources, fetch_source_content
from db import get_company, get_conn, list_companies, log_job_run, utc_now
from llm_client import FreeLLMClient
from signal_stack import add_source, list_sources, update_source_status


class AuditSourceRecommendation(BaseModel):
    source_id: Optional[int] = Field(default=None, description="ID if referring to an existing source.")
    category: str = Field(default="Market")
    name: str
    url_or_path: str
    action: str = Field(description="keep, mark_inactive, remove, or add_new")
    reason: str


class MonthlyAuditReportSchema(BaseModel):
    audit_summary: str
    declining_relevance_notes: list[str] = Field(default_factory=list)
    recommendations: list[AuditSourceRecommendation] = Field(default_factory=list)


_scheduler: Optional[BackgroundScheduler] = None


def get_settings(company_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM settings WHERE company_id = ?", (company_id,)).fetchone()
        if not row:
            conn.execute("INSERT INTO settings (company_id) VALUES (?)", (company_id,))
            row = conn.execute("SELECT * FROM settings WHERE company_id = ?", (company_id,)).fetchone()
        return dict(row)


def update_settings(company_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = {
        "briefing_day",
        "briefing_time",
        "timezone",
        "monitoring_frequency",
        "source_refresh_frequency",
        "monthly_audit_day",
    }
    clean = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}
    if not clean:
        return get_settings(company_id)

    get_settings(company_id)  # Ensure row exists
    assignments = ", ".join(f"{col} = ?" for col in clean.keys())
    values = list(clean.values()) + [company_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE settings SET {assignments} WHERE company_id = ?", values)
    return get_settings(company_id)


def run_monthly_signal_stack_audit(
    company_id: int,
    apply_recommendations: bool = False,
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        err = f"Company id={company_id} not found."
        log_job_run(company_id, "monthly_audit", "failed", err)
        raise ValueError(err)

    try:
        sources = list_sources(company_id)
        dead_or_failing: list[dict[str, Any]] = []
        duplicate_sources: list[dict[str, Any]] = []
        inactive_sources: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        for s in sources:
            key = (s["category"].lower(), s["url_or_path"].strip().lower())
            if key in seen_keys:
                duplicate_sources.append(s)
            else:
                seen_keys.add(key)

            if s["status"] == "inactive":
                inactive_sources.append(s)

            if s["category"] != "Internal" and s["status"] == "approved":
                parsed = urlparse(s["url_or_path"])
                if parsed.scheme in ("http", "https"):
                    probe = fetch_source_content(s["url_or_path"], timeout=8.0)
                    now = utc_now()
                    with get_conn() as conn:
                        if not probe["ok"]:
                            conn.execute(
                                """
                                UPDATE sources
                                SET last_checked_at = ?, last_status_code = ?,
                                    consecutive_failures = consecutive_failures + 1
                                WHERE id = ?
                                """,
                                (now, probe["status_code"], s["id"]),
                            )
                            dead_or_failing.append({**s, "probe_error": probe["error"]})
                        else:
                            conn.execute(
                                """
                                UPDATE sources
                                SET last_checked_at = ?, last_status_code = ?, consecutive_failures = 0
                                WHERE id = ?
                                """,
                                (now, probe["status_code"], s["id"]),
                            )

        # Count collected signals per source to spot low-yield/declining sources
        with get_conn() as conn:
            sig_counts = {
                r["source_id"]: r["cnt"]
                for r in conn.execute(
                    """
                    SELECT source_id, COUNT(*) AS cnt
                    FROM signals
                    WHERE company_id = ? AND source_id IS NOT NULL
                    GROUP BY source_id
                    """,
                    (company_id,),
                ).fetchall()
            }

        enriched_sources = [
            {
                "id": s["id"],
                "category": s["category"],
                "name": s["name"],
                "url_or_path": s["url_or_path"],
                "status": s["status"],
                "reliability_score": s["reliability_score"],
                "relevance_score": s["relevance_score"],
                "consecutive_failures": s["consecutive_failures"],
                "signals_collected": sig_counts.get(s["id"], 0),
            }
            for s in sources
        ]

        llm_client = llm or FreeLLMClient()
        system_prompt = (
            "You are a Signal Stack reliability and hygiene auditor. Review source health probes, "
            "duplicate/inactive flags, signal counts, and company context. Identify sources with declining "
            "relevance or health issues, and recommend concrete additions/removals/inactivations."
        )
        user_prompt = (
            f"Company: {company['name']} ({company['website']})\n"
            f"Business Context: {company.get('business_context') or ''}\n"
            f"Sources Audit Input: {json.dumps(enriched_sources)}\n"
            f"Dead/Failing Count: {len(dead_or_failing)} | Duplicates Count: {len(duplicate_sources)}"
        )

        report = llm_client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=MonthlyAuditReportSchema,
            temperature=0.2,
        )

        applied_actions: list[str] = []
        if apply_recommendations:
            for rec in report.recommendations:
                if rec.action == "mark_inactive" and rec.source_id is not None:
                    update_source_status(company_id, rec.source_id, "inactive")
                    applied_actions.append(f"Marked source #{rec.source_id} inactive")
                elif rec.action == "add_new" and rec.name.strip() and rec.url_or_path.strip():
                    cat = rec.category if rec.category in ("Customers", "Competitors", "Market", "Internal") else "Market"
                    add_source(
                        company_id=company_id,
                        category=cat,
                        name=rec.name,
                        url_or_path=rec.url_or_path,
                        reason=f"[Monthly Audit Addition] {rec.reason}",
                        status="approved",
                    )
                    applied_actions.append(f"Added source '{rec.name}'")

        result = {
            "company_id": company_id,
            "audited_at": utc_now(),
            "dead_or_failing_sources": dead_or_failing,
            "duplicate_sources": duplicate_sources,
            "inactive_sources": inactive_sources,
            "declining_relevance_notes": report.declining_relevance_notes,
            "audit_summary": report.audit_summary,
            "recommendations": [r.model_dump() for r in report.recommendations],
            "applied_actions": applied_actions,
        }
        log_job_run(
            company_id=company_id,
            job_type="monthly_audit",
            status="success",
            details=(
                f"Checked {len(sources)} sources; dead/failing={len(dead_or_failing)}, "
                f"duplicates={len(duplicate_sources)}, recs={len(report.recommendations)}"
            ),
        )
        return result
    except Exception as exc:
        log_job_run(company_id=company_id, job_type="monthly_audit", status="failed", details=str(exc))
        raise


def run_weekly_intelligence_cycle(
    company_id: int,
    job_type: str = "weekly_brief",
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        err = f"Company id={company_id} not found."
        log_job_run(company_id, job_type, "failed", err)
        raise ValueError(err)

    try:
        llm_client = llm or FreeLLMClient()
        crawl_summary = crawl_company_sources(company_id=company_id, llm=llm_client)
        brief_res = generate_monday_morning_brief(
            company_id=company_id,
            brief_type="weekly" if job_type == "weekly_brief" else "manual",
            llm=llm_client,
        )
        details = (
            f"Crawled {crawl_summary['sources_checked']} sources "
            f"(failed={crawl_summary['sources_failed']}), "
            f"processed {crawl_summary['signals_processed']} signals, "
            f"generated brief #{brief_res['brief']['id']}"
        )
        log_job_run(company_id=company_id, job_type=job_type, status="success", details=details)
        return {
            "crawl_summary": crawl_summary,
            "brief": brief_res["brief"],
            "brief_structured": brief_res["structured"],
        }
    except Exception as exc:
        log_job_run(company_id=company_id, job_type=job_type, status="failed", details=str(exc))
        raise


def _scheduled_weekly_all_companies() -> None:
    for comp in list_companies():
        try:
            run_weekly_intelligence_cycle(comp["id"], job_type="weekly_brief")
        except Exception:
            # Already logged to job_runs inside run_weekly_intelligence_cycle
            pass


def _scheduled_monthly_all_companies() -> None:
    for comp in list_companies():
        try:
            run_monthly_signal_stack_audit(comp["id"], apply_recommendations=False)
        except Exception:
            # Already logged to job_runs inside run_monthly_signal_stack_audit
            pass


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    # Weekly Monday brief cycle + Monthly Signal Stack health audit cycle
    scheduler.add_job(
        _scheduled_weekly_all_companies,
        trigger="cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        id="weekly_monday_brief_job",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled_monthly_all_companies,
        trigger="cron",
        day=1,
        hour=9,
        minute=0,
        id="monthly_signal_stack_audit_job",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def list_job_runs(company_id: Optional[int] = None, limit: int = 50) -> list[dict[str, Any]]:
    query = "SELECT * FROM job_runs"
    params: list[Any] = []
    if company_id is not None:
        query += " WHERE company_id = ?"
        params.append(company_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    