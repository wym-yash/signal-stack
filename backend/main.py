from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from brief_generator import generate_monday_morning_brief, list_briefs
from crawler import crawl_company_sources, list_signals
from db import (
    create_company,
    get_company,
    get_conn,
    init_db,
    list_companies,
    log_audit_event,
    update_business_context,
)
from interviewer import (
    edit_interview_answer,
    generate_ten_questions,
    get_next_question,
    submit_interview_step,
)
from llm_client import FreeLLMClient
from researcher import run_initial_research
from scheduler import (
    get_settings,
    list_job_runs,
    run_monthly_signal_stack_audit,
    run_weekly_intelligence_cycle,
    shutdown_scheduler,
    start_scheduler,
    update_settings,
)
from signal_stack import (
    add_source,
    generate_signal_stack,
    ingest_internal_file,
    list_sources,
    reassess_signal_stack_on_context_change,
    remove_source,
    update_source_status,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title="Signal Stack — Company Intelligence & Executive Briefing API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompanyCreateRequest(BaseModel):
    name: str
    website: str
    industry: str = ""
    business_context: str = ""


class ContextUpdateRequest(BaseModel):
    business_context: str
    change_summary: str = ""
    reassess_signal_stack: bool = True


class InterviewStepRequest(BaseModel):
    message_id: int
    answer_text: str = ""
    skip: bool = False
    allow_followup: bool = True


class InterviewEditRequest(BaseModel):
    message_id: int
    new_answer_text: str = ""
    skip: bool = False


class SourceCreateRequest(BaseModel):
    category: str
    name: str
    url_or_path: str
    reason: str
    status: str = "approved"
    reliability_score: float = Field(default=0.75, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.8, ge=0.0, le=1.0)


class SourceStatusRequest(BaseModel):
    status: str


class SettingsUpdateRequest(BaseModel):
    briefing_day: Optional[str] = None
    briefing_time: Optional[str] = None
    timezone: Optional[str] = None
    monitoring_frequency: Optional[str] = None
    source_refresh_frequency: Optional[str] = None
    monthly_audit_day: Optional[int] = None


def _get_founder_id(request: Request) -> str:
    header_val = (request.headers.get("x-founder-id") or "").strip()
    if header_val:
        return header_val
    auth_val = (request.headers.get("authorization") or "").strip()
    if auth_val.lower().startswith("bearer "):
        return auth_val[7:].strip()
    return ""


def _require_owned_company(company_id: int, founder_id: str, action: str) -> dict[str, Any]:
    comp = get_company(company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")
    owner_id = (comp.get("owner_id") or "").strip()
    if owner_id and founder_id and owner_id != founder_id:
        log_audit_event(
            actor_id=founder_id,
            action=action,
            company_id=company_id,
            status="denied",
            details=f"Owner mismatch: expected {owner_id}",
        )
        raise HTTPException(status_code=403, detail="Access denied for this company workspace")
    if owner_id and not founder_id:
        log_audit_event(
            actor_id="anonymous",
            action=action,
            company_id=company_id,
            status="denied",
            details=f"Missing founder identity for workspace owned by {owner_id}",
        )
        raise HTTPException(status_code=403, detail="Founder identity required for this workspace")
    return comp


@app.get("/health")
def health() -> dict[str, Any]:
    llm = FreeLLMClient()
    return {
        "status": "ok",
        "available_free_llm_providers": llm.available_providers(),
    }


@app.get("/companies")
def api_list_companies(request: Request) -> list[dict[str, Any]]:
    founder_id = _get_founder_id(request)
    return list_companies(owner_id=founder_id)


@app.post("/companies", status_code=201)
def api_create_company(payload: CompanyCreateRequest, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    try:
        company = create_company(
            name=payload.name,
            website=payload.website,
            industry=payload.industry,
            business_context=payload.business_context,
            owner_id=founder_id,
        )
        if not isinstance(company, dict):
            raise RuntimeError("Invalid company payload returned.")
        log_audit_event(
            actor_id=founder_id,
            action="company.create",
            company_id=company.get("id"),
            status="allowed",
            details=f"Created company {company.get('name')}",
        )
        return company
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/companies/{company_id}")
def api_get_company(company_id: int, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    comp = _require_owned_company(company_id, founder_id, "company.read")
    with get_conn() as conn:
        history = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM context_history WHERE company_id = ? ORDER BY id DESC",
                (company_id,),
            ).fetchall()
        ]
    log_audit_event(actor_id=founder_id, action="company.read", company_id=company_id, status="allowed")
    return {**comp, "context_history": history}


@app.post("/companies/{company_id}/research")
def api_run_research(company_id: int, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "company.research")
    try:
        result = run_initial_research(company_id)
        log_audit_event(actor_id=founder_id, action="company.research", company_id=company_id, status="allowed")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.put("/companies/{company_id}/context")
def api_update_context(company_id: int, payload: ContextUpdateRequest, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "company.context.update")
    try:
        if payload.reassess_signal_stack:
            result = reassess_signal_stack_on_context_change(
                company_id=company_id,
                new_business_context=payload.business_context,
                change_summary=payload.change_summary,
            )
            log_audit_event(
                actor_id=founder_id,
                action="company.context.update",
                company_id=company_id,
                status="allowed",
                details="reassessed_signal_stack=True",
            )
            return result
        updated = update_business_context(
            company_id=company_id,
            new_context=payload.business_context,
            change_summary=payload.change_summary,
        )
        log_audit_event(
            actor_id=founder_id,
            action="company.context.update",
            company_id=company_id,
            status="allowed",
            details="reassessed_signal_stack=False",
        )
        return {"company": updated, "reassessed": False}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/companies/{company_id}/interview/start")
def api_start_interview(company_id: int, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "interview.start")
    try:
        messages = generate_ten_questions(company_id)
        next_q = get_next_question(company_id)
        log_audit_event(actor_id=founder_id, action="interview.start", company_id=company_id, status="allowed")
        return {"messages": messages, "next_state": next_q}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/companies/{company_id}/interview/next")
def api_next_question(company_id: int, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "interview.next")
    try:
        return get_next_question(company_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/companies/{company_id}/interview/answer")
def api_submit_interview_step(company_id: int, payload: InterviewStepRequest, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "interview.answer")
    try:
        result = submit_interview_step(
            company_id=company_id,
            message_id=payload.message_id,
            answer_text=payload.answer_text,
            skip=payload.skip,
            allow_followup=payload.allow_followup,
        )
        log_audit_event(actor_id=founder_id, action="interview.answer", company_id=company_id, status="allowed")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.put("/companies/{company_id}/interview/edit")
def api_edit_interview_answer(company_id: int, payload: InterviewEditRequest, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "interview.edit")
    try:
        result = edit_interview_answer(
            company_id=company_id,
            message_id=payload.message_id,
            new_answer_text=payload.new_answer_text,
            skip=payload.skip,
        )
        log_audit_event(actor_id=founder_id, action="interview.edit", company_id=company_id, status="allowed")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/companies/{company_id}/signal-stack")
def api_list_sources(
    company_id: int,
    request: Request,
    category: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "sources.list")
    return list_sources(company_id=company_id, category=category, status=status)


@app.post("/companies/{company_id}/signal-stack/generate")
def api_generate_signal_stack(company_id: int, request: Request, min_sources: int = 20) -> list[dict[str, Any]]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "sources.generate")
    try:
        result = generate_signal_stack(company_id=company_id, min_sources=min_sources)
        log_audit_event(actor_id=founder_id, action="sources.generate", company_id=company_id, status="allowed")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/companies/{company_id}/signal-stack/sources", status_code=201)
def api_add_source(company_id: int, payload: SourceCreateRequest, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "sources.add")
    try:
        result = add_source(
            company_id=company_id,
            category=payload.category,
            name=payload.name,
            url_or_path=payload.url_or_path,
            reason=payload.reason,
            status=payload.status,
            reliability_score=payload.reliability_score,
            relevance_score=payload.relevance_score,
        )
        log_audit_event(actor_id=founder_id, action="sources.add", company_id=company_id, status="allowed")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.patch("/companies/{company_id}/signal-stack/sources/{source_id}/status")
def api_update_source_status(
    company_id: int,
    source_id: int,
    payload: SourceStatusRequest,
    request: Request,
) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "sources.status")
    try:
        updated = update_source_status(company_id=company_id, source_id=source_id, status=payload.status)
        if not updated:
            raise HTTPException(status_code=404, detail="Source not found")
        log_audit_event(
            actor_id=founder_id,
            action="sources.status",
            company_id=company_id,
            status="allowed",
            details=f"source_id={source_id} status={payload.status}",
        )
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/companies/{company_id}/signal-stack/sources/{source_id}")
def api_delete_source(company_id: int, source_id: int, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "sources.delete")
    deleted = remove_source(company_id=company_id, source_id=source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    log_audit_event(
        actor_id=founder_id,
        action="sources.delete",
        company_id=company_id,
        status="allowed",
        details=f"source_id={source_id}",
    )
    return {"deleted": True, "source_id": source_id}


@app.post("/companies/{company_id}/signal-stack/internal-upload")
async def api_upload_internal_file(
    company_id: int,
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "sources.internal_upload")
    try:
        content = await file.read()
        result = ingest_internal_file(
            company_id=company_id,
            filename=file.filename or "upload.txt",
            content=content,
        )
        log_audit_event(
            actor_id=founder_id,
            action="sources.internal_upload",
            company_id=company_id,
            status="allowed",
            details=f"filename={file.filename or 'upload.txt'}",
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/companies/{company_id}/crawl")
def api_crawl_sources(company_id: int, request: Request, max_sources: int = 25) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "crawl.run")
    try:
        result = crawl_company_sources(company_id=company_id, max_sources=max_sources)
        log_audit_event(actor_id=founder_id, action="crawl.run", company_id=company_id, status="allowed")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/companies/{company_id}/signals")
def api_list_signals(
    company_id: int,
    request: Request,
    category: Optional[str] = None,
    competitor_name: Optional[str] = None,
    verified_status: Optional[str] = None,
    min_rank_score: Optional[float] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "signals.list")
    return list_signals(
        company_id=company_id,
        category=category,
        competitor_name=competitor_name,
        verified_status=verified_status,
        min_rank_score=min_rank_score,
        limit=limit,
    )


@app.post("/companies/{company_id}/briefs/generate")
def api_generate_brief(company_id: int, request: Request, brief_type: str = "weekly") -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "briefs.generate")
    try:
        result = generate_monday_morning_brief(company_id=company_id, brief_type=brief_type)
        log_audit_event(
            actor_id=founder_id,
            action="briefs.generate",
            company_id=company_id,
            status="allowed",
            details=f"brief_type={brief_type}",
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/companies/{company_id}/briefs")
def api_list_briefs(company_id: int, request: Request) -> list[dict[str, Any]]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "briefs.list")
    return list_briefs(company_id=company_id)


@app.post("/companies/{company_id}/runs/manual")
def api_manual_run(company_id: int, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "runs.manual")
    try:
        result = run_weekly_intelligence_cycle(company_id=company_id, job_type="manual_run")
        log_audit_event(actor_id=founder_id, action="runs.manual", company_id=company_id, status="allowed")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/companies/{company_id}/runs/monthly-audit")
def api_monthly_audit(
    company_id: int,
    request: Request,
    apply_recommendations: bool = False,
) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "runs.monthly_audit")
    try:
        result = run_monthly_signal_stack_audit(
            company_id=company_id,
            apply_recommendations=apply_recommendations,
        )
        log_audit_event(
            actor_id=founder_id,
            action="runs.monthly_audit",
            company_id=company_id,
            status="allowed",
            details=f"apply_recommendations={apply_recommendations}",
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/companies/{company_id}/runs")
def api_list_runs(company_id: int, request: Request, limit: int = 50) -> list[dict[str, Any]]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "runs.list")
    return list_job_runs(company_id=company_id, limit=limit)


@app.get("/companies/{company_id}/settings")
def api_get_settings(company_id: int, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "settings.read")
    return get_settings(company_id)


@app.put("/companies/{company_id}/settings")
def api_update_settings(company_id: int, payload: SettingsUpdateRequest, request: Request) -> dict[str, Any]:
    founder_id = _get_founder_id(request)
    _require_owned_company(company_id, founder_id, "settings.update")
    updated = update_settings(company_id=company_id, updates=payload.model_dump())
    log_audit_event(actor_id=founder_id, action="settings.update", company_id=company_id, status="allowed")
    return updated