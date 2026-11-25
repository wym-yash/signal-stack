import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from db import get_company, get_conn, update_business_context, utc_now
from llm_client import FreeLLMClient

TARGET_PRIMARY_QUESTIONS = 10


class QuestionPlan(BaseModel):
    questions: list[str] = Field(
        min_length=10,
        max_length=10,
        description=(
            "Exactly 10 sharp, non-generic founder interview questions tailored to this specific company "
            "and its research findings. Cover business lines/revenue, target segments, customer pain points, "
            "differentiation/value prop, key competitors/substitutes, market/regulatory shifts, 6-12 month growth "
            "priorities, internal data/blind spots, and key founder decisions Signal Stack should support."
        ),
    )


class FollowUpDecision(BaseModel):
    ask_followup: bool = Field(
        description="True if the founder's latest answer hints at a high-value detail or ambiguity worth one concise follow-up."
    )
    followup_question: str = Field(
        default="",
        description="Single crisp follow-up question if ask_followup is True, else empty string.",
    )


class ContextSynthesis(BaseModel):
    synthesized_business_context: str = Field(
        description="Clear, structured summary of the company's business context based on answered interview questions."
    )


def _list_messages(company_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM interview_messages
            WHERE company_id = ?
            ORDER BY question_index ASC, is_followup ASC, id ASC
            """,
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def generate_ten_questions(company_id: int, llm: Optional[FreeLLMClient] = None) -> list[dict[str, Any]]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    existing = _list_messages(company_id)
    if len(existing) >= TARGET_PRIMARY_QUESTIONS:
        return existing

    llm_client = llm or FreeLLMClient()
    existing_questions = [m["question_text"] for m in existing]

    system_prompt = (
        "You are an executive strategy interviewer designing a 10-question founder interview. "
        "Every question must be specific to the company's actual product, domain, positioning, "
        "verified facts, and open assumptions—never generic boilerplate. "
        "Do not repeat or closely paraphrase any already-generated questions."
    )

    user_prompt = (
        f"Company Name: {company['name']}\n"
        f"Website: {company['website']}\n"
        f"Industry: {company.get('industry') or 'Unknown'}\n"
        f"Profile Summary: {company.get('profile_summary') or 'Not researched yet'}\n"
        f"Verified Facts: {json.dumps(company.get('verified_facts', []))}\n"
        f"Assumptions / Open Questions: {json.dumps(company.get('assumptions', []))}\n"
        f"Already Generated Questions: {json.dumps(existing_questions)}\n\n"
        f"Generate exactly {TARGET_PRIMARY_QUESTIONS} tailored primary questions (1 to 10)."
    )

    plan = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_model=QuestionPlan,
        temperature=0.35,
    )

    now = utc_now()
    with get_conn() as conn:
        conn.execute("DELETE FROM interview_messages WHERE company_id = ?", (company_id,))
        for idx, q_text in enumerate(plan.questions[:TARGET_PRIMARY_QUESTIONS], start=1):
            conn.execute(
                """
                INSERT INTO interview_messages (
                    company_id, question_index, question_text, is_followup,
                    parent_question_index, answer_text, skipped, updated_at
                )
                VALUES (?, ?, ?, 0, NULL, '', 0, ?)
                """,
                (company_id, idx, q_text.strip(), now),
            )

    return _list_messages(company_id)


def get_next_question(company_id: int, llm: Optional[FreeLLMClient] = None) -> dict[str, Any]:
    messages = generate_ten_questions(company_id, llm=llm)
    pending = [
        m for m in messages
        if not m["skipped"] and not (m["answer_text"] or "").strip()
    ]

    primary_total = sum(1 for m in messages if m["is_followup"] == 0)
    primary_done = sum(
        1 for m in messages
        if m["is_followup"] == 0 and (m["skipped"] == 1 or bool((m["answer_text"] or "").strip()))
    )

    if not pending:
        return {
            "completed": True,
            "progress": {"primary_completed": primary_done, "primary_total": primary_total},
            "current_question": None,
            "messages": messages,
        }

    return {
        "completed": False,
        "progress": {"primary_completed": primary_done, "primary_total": primary_total},
        "current_question": pending[0],
        "messages": messages,
    }


def sync_business_context_from_interview(company_id: int, llm: Optional[FreeLLMClient] = None) -> Optional[str]:
    company = get_company(company_id)
    if not company:
        return None

    messages = _list_messages(company_id)
    answered_pairs = [
        {
            "q_index": m["question_index"],
            "is_followup": bool(m["is_followup"]),
            "question": m["question_text"],
            "answer": m["answer_text"],
        }
        for m in messages
        if not m["skipped"] and (m["answer_text"] or "").strip()
    ]

    if not answered_pairs:
        return company.get("business_context", "")

    llm_client = llm or FreeLLMClient()
    system_prompt = (
        "You synthesize founder interview responses into a crisp, factual business context brief "
        "used for downstream competitor, customer, market, and intelligence monitoring."
    )
    user_prompt = (
        f"Company: {company['name']} ({company['website']})\n"
        f"Profile Summary: {company.get('profile_summary', '')}\n"
        f"Answered Interview Items: {json.dumps(answered_pairs)}\n"
        "Summarize key business lines, target segments, pain points, differentiation, competitors, "
        "market priorities, internal signals, and founder decision needs without inventing facts."
    )

    synth = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_model=ContextSynthesis,
        temperature=0.2,
    )
    update_business_context(
        company_id=company_id,
        new_context=synth.synthesized_business_context,
        change_summary="Updated from adaptive founder interview responses",
    )
    return synth.synthesized_business_context


def submit_interview_step(
    company_id: int,
    message_id: int,
    answer_text: str = "",
    skip: bool = False,
    allow_followup: bool = True,
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    messages = _list_messages(company_id)
    target = next((m for m in messages if m["id"] == message_id), None)
    if not target:
        raise ValueError(f"Interview message id={message_id} not found for company_id={company_id}.")

    now = utc_now()
    clean_answer = (answer_text or "").strip()
    llm_client = llm or FreeLLMClient()

    with get_conn() as conn:
        if skip:
            conn.execute(
                """
                UPDATE interview_messages
                SET skipped = 1, answer_text = '', updated_at = ?
                WHERE id = ?
                """,
                (now, message_id),
            )
        else:
            if not clean_answer:
                raise ValueError("Provide an answer_text or set skip=True.")
            conn.execute(
                """
                UPDATE interview_messages
                SET skipped = 0, answer_text = ?, updated_at = ?
                WHERE id = ?
                """,
                (clean_answer, now, message_id),
            )

            # Optionally insert at most one concise follow-up right after a non-followup answer
            if allow_followup and target["is_followup"] == 0:
                already_has_followup = any(
                    m["is_followup"] == 1 and m["parent_question_index"] == target["question_index"]
                    for m in messages
                )
                if not already_has_followup:
                    company = get_company(company_id)
                    existing_qs = [m["question_text"] for m in _list_messages(company_id)]
                    decision = llm_client.generate_structured(
                        system_prompt=(
                            "Decide whether a founder's answer warrants ONE brief, high-signal follow-up question. "
                            "Keep ask_followup False unless there is a clear ambiguity or strategic detail worth probing. "
                            "Never repeat existing questions."
                        ),
                        user_prompt=(
                            f"Company: {company['name'] if company else ''}\n"
                            f"Question Asked: {target['question_text']}\n"
                            f"Founder Answer: {clean_answer}\n"
                            f"Existing Questions: {json.dumps(existing_qs)}"
                        ),
                        schema_model=FollowUpDecision,
                        temperature=0.25,
                    )
                    if decision.ask_followup and decision.followup_question.strip():
                        q_clean = decision.followup_question.strip()
                        if q_clean.lower() not in {q.lower() for q in existing_qs}:
                            conn.execute(
                                """
                                INSERT INTO interview_messages (
                                    company_id, question_index, question_text, is_followup,
                                    parent_question_index, answer_text, skipped, updated_at
                                )
                                VALUES (?, ?, ?, 1, ?, '', 0, ?)
                                """,
                                (
                                    company_id,
                                    target["question_index"],
                                    q_clean,
                                    target["question_index"],
                                    now,
                                ),
                            )

    updated_context = sync_business_context_from_interview(company_id, llm=llm_client)
    next_state = get_next_question(company_id, llm=llm_client)
    next_state["business_context"] = updated_context
    return next_state


def edit_interview_answer(
    company_id: int,
    message_id: int,
    new_answer_text: str,
    skip: bool = False,
    llm: Optional[FreeLLMClient] = None,
) -> dict[str, Any]:
    messages = _list_messages(company_id)
    target = next((m for m in messages if m["id"] == message_id), None)
    if not target:
        raise ValueError(f"Interview message id={message_id} not found for company_id={company_id}.")

    now = utc_now()
    with get_conn() as conn:
        if skip:
            conn.execute(
                """
                UPDATE interview_messages
                SET skipped = 1, answer_text = '', updated_at = ?
                WHERE id = ?
                """,
                (now, message_id),
            )
        else:
            clean = (new_answer_text or "").strip()
            if not clean:
                raise ValueError("new_answer_text cannot be empty when skip=False.")
            conn.execute(
                """
                UPDATE interview_messages
                SET skipped = 0, answer_text = ?, updated_at = ?
                WHERE id = ?
                """,
                (clean, now, message_id),
            )

    llm_client = llm or FreeLLMClient()
    updated_context = sync_business_context_from_interview(company_id, llm=llm_client)
    return {
        "business_context": updated_context,
        "messages": _list_messages(company_id),
    }