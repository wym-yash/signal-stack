import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(os.getenv("DATABASE_PATH", "signal_stack.db"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            website TEXT NOT NULL,
            industry TEXT DEFAULT '',
            business_context TEXT DEFAULT '',
            profile_summary TEXT DEFAULT '',
            verified_facts_json TEXT DEFAULT '[]',
            assumptions_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS context_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            previous_context TEXT NOT NULL,
            new_context TEXT NOT NULL,
            change_summary TEXT DEFAULT '',
            changed_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS interview_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            question_index INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            is_followup INTEGER NOT NULL DEFAULT 0,
            parent_question_index INTEGER,
            answer_text TEXT DEFAULT '',
            skipped INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('Customers', 'Competitors', 'Market', 'Internal')),
            name TEXT NOT NULL,
            url_or_path TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'approved' CHECK(status IN ('pending', 'approved', 'inactive', 'removed')),
            reliability_score REAL NOT NULL DEFAULT 0.75,
            relevance_score REAL NOT NULL DEFAULT 0.75,
            last_checked_at TEXT,
            last_status_code INTEGER,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            source_id INTEGER,
            category TEXT NOT NULL CHECK(category IN ('Customers', 'Competitors', 'Market', 'Internal')),
            competitor_name TEXT DEFAULT '',
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            evidence_snippet TEXT NOT NULL,
            source_url TEXT NOT NULL,
            published_date TEXT,
            discovered_at TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            signal_stance TEXT NOT NULL DEFAULT 'neutral' CHECK(signal_stance IN ('opportunity', 'threat', 'neutral')),
            relevance_score REAL NOT NULL DEFAULT 0.5,
            impact_score REAL NOT NULL DEFAULT 0.5,
            urgency_score REAL NOT NULL DEFAULT 0.5,
            credibility_score REAL NOT NULL DEFAULT 0.5,
            recency_score REAL NOT NULL DEFAULT 0.5,
            novelty_score REAL NOT NULL DEFAULT 0.5,
            evidence_strength_score REAL NOT NULL DEFAULT 0.5,
            total_rank_score REAL NOT NULL DEFAULT 0.0,
            verified_status TEXT NOT NULL DEFAULT 'unverified' CHECK(verified_status IN ('verified', 'partially_verified', 'unverified')),
            interpretation TEXT NOT NULL DEFAULT '',
            recommended_action TEXT NOT NULL DEFAULT '',
            UNIQUE(company_id, content_hash),
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            brief_type TEXT NOT NULL DEFAULT 'weekly',
            markdown_content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            job_type TEXT NOT NULL CHECK(job_type IN ('weekly_brief', 'monthly_audit', 'manual_run')),
            status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
            details TEXT NOT NULL DEFAULT '',
            ran_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER UNIQUE,
            briefing_day TEXT NOT NULL DEFAULT 'Monday',
            briefing_time TEXT NOT NULL DEFAULT '08:00',
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            monitoring_frequency TEXT NOT NULL DEFAULT 'daily',
            source_refresh_frequency TEXT NOT NULL DEFAULT 'weekly',
            monthly_audit_day INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        );
        """)


def create_company(name: str, website: str, industry: str = "", business_context: str = "") -> dict[str, Any]:
    now = utc_now()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO companies (name, website, industry, business_context, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name.strip(), website.strip(), industry.strip(), business_context.strip(), now, now),
        )
        company_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO settings (company_id)
            VALUES (?)
            """,
            (company_id,),
        )
        return get_company(company_id)


def get_company(company_id: int) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["verified_facts"] = json.loads(d.pop("verified_facts_json") or "[]")
        d["assumptions"] = json.loads(d.pop("assumptions_json") or "[]")
        return d


def list_companies() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM companies ORDER BY id DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["verified_facts"] = json.loads(d.pop("verified_facts_json") or "[]")
            d["assumptions"] = json.loads(d.pop("assumptions_json") or "[]")
            out.append(d)
        return out


def update_company_research(
    company_id: int,
    profile_summary: str,
    verified_facts: list[str],
    assumptions: list[str],
    industry: str = "",
) -> Optional[dict[str, Any]]:
    now = utc_now()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE companies
            SET profile_summary = ?,
                verified_facts_json = ?,
                assumptions_json = ?,
                industry = CASE WHEN ? != '' THEN ? ELSE industry END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                profile_summary,
                json.dumps(verified_facts),
                json.dumps(assumptions),
                industry,
                industry,
                now,
                company_id,
            ),
        )
    return get_company(company_id)


def update_business_context(company_id: int, new_context: str, change_summary: str = "") -> Optional[dict[str, Any]]:
    now = utc_now()
    with get_conn() as conn:
        row = conn.execute("SELECT business_context FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return None
        prev_context = row["business_context"] or ""
        conn.execute(
            """
            INSERT INTO context_history (company_id, previous_context, new_context, change_summary, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (company_id, prev_context, new_context.strip(), change_summary.strip(), now),
        )
        conn.execute(
            """
            UPDATE companies
            SET business_context = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_context.strip(), now, company_id),
        )
    return get_company(company_id)


def log_job_run(company_id: Optional[int], job_type: str, status: str, details: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO job_runs (company_id, job_type, status, details, ran_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (company_id, job_type, status, details, utc_now()),
        )