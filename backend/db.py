import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_raw_db_path = (os.getenv("DATABASE_PATH") or "").strip()
DB_PATH = Path(_raw_db_path or "signal_stack.db")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    if str(DB_PATH.parent) not in ("", "."):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
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


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT DEFAULT '',
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

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            company_id INTEGER,
            status TEXT NOT NULL DEFAULT 'allowed',
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """)
        _ensure_column(conn, "companies", "owner_id", "TEXT DEFAULT ''")


def _row_to_company(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["verified_facts"] = json.loads(d.pop("verified_facts_json") or "[]")
    d["assumptions"] = json.loads(d.pop("assumptions_json") or "[]")
    return d


def create_company(
    name: str,
    website: str,
    industry: str = "",
    business_context: str = "",
    owner_id: str = "",
) -> dict[str, Any]:
    clean_name = (name or "").strip()
    clean_website = (website or "").strip()
    clean_industry = (industry or "").strip()
    clean_context = (business_context or "").strip()
    clean_owner = (owner_id or "").strip()

    if not clean_name:
        raise ValueError("Company name is required.")
    if not clean_website:
        raise ValueError("Website is required.")

    now = utc_now()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO companies (owner_id, name, website, industry, business_context, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_owner, clean_name, clean_website, clean_industry, clean_context, now, now),
        )
        company_id = cur.lastrowid
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (company_id)
            VALUES (?)
            """,
            (company_id,),
        )
        if clean_context:
            conn.execute(
                """
                INSERT INTO context_history (company_id, previous_context, new_context, change_summary, changed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (company_id, "", clean_context, "Initial setup context", now),
            )

    company = get_company(company_id)
    if not company:
        raise RuntimeError(f"Company row could not be loaded after creation (id={company_id}).")
    return company


def get_company(company_id: int) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return None
        return _row_to_company(row)


def list_companies(owner_id: Optional[str] = None) -> list[dict[str, Any]]:
    clean_owner = (owner_id or "").strip()
    with get_conn() as conn:
        if clean_owner:
            rows = conn.execute(
                "SELECT * FROM companies WHERE owner_id = ? ORDER BY id DESC",
                (clean_owner,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM companies WHERE owner_id = '' ORDER BY id DESC"
            ).fetchall()
        return [_row_to_company(r) for r in rows]


def update_company_research(
    company_id: int,
    profile_summary: str,
    verified_facts: list[str],
    assumptions: list[str],
    industry: str = "",
) -> Optional[dict[str, Any]]:
    now = utc_now()
    clean_industry = (industry or "").strip()
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
                clean_industry,
                clean_industry,
                now,
                company_id,
            ),
        )
    return get_company(company_id)


def update_business_context(company_id: int, new_context: str, change_summary: str = "") -> Optional[dict[str, Any]]:
    now = utc_now()
    clean_context = (new_context or "").strip()
    clean_summary = (change_summary or "").strip()
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
            (company_id, prev_context, clean_context, clean_summary, now),
        )
        conn.execute(
            """
            UPDATE companies
            SET business_context = ?, updated_at = ?
            WHERE id = ?
            """,
            (clean_context, now, company_id),
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


def log_audit_event(
    actor_id: str,
    action: str,
    company_id: Optional[int] = None,
    status: str = "allowed",
    details: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (actor_id, action, company_id, status, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ((actor_id or "").strip(), action, company_id, status, details, utc_now()),
        )