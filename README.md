# Signal Stack

Signal Stack is a founder intelligence workspace built with FastAPI, SQLite, and React (Vite) for conducting founder interviews, managing signal sources, crawling signals, and generating Monday morning briefs.

## Features

- **Multi-company workspace isolation:** Companies are scoped by `owner_id` so workspaces and confidential assets stay hidden when signed out or viewed by other founders, with `X-Founder-Id` / `Authorization` header support and a founder sign-in/switcher bar in the UI.
- **Audit logging:** Records allowed and denied workspace access attempts in `audit_logs` across protected company, interview, source, crawl, signal, brief, run, and settings routes.
- **Founder interview & context flow:** Captures structured interview responses, updates business context, and tracks verified facts, assumptions, and context history.
- **Signal stack & crawling:** Manages customer, competitor, market, and internal sources (including file uploads), runs crawls, and ranks collected signals.
- **Resilient Monday morning brief generation:** Trims prompt payload size to avoid free-tier token caps (`413`), falls back to a deterministic markdown brief when upstream LLM quotas (`429`) or limits are hit, renders `markdown_content` cleanly in the UI, and supports markdown copy and `.md` export.

## Project Structure

- `backend/` — FastAPI app (`main.py`), SQLite database helpers (`db.py`), brief generation (`brief_generator.py`), LLM client (`llm_client.py`), signal stack, crawler, and automation modules.
- `frontend/` — React + Vite interface (`src/App.jsx`, `src/pages/Brief.jsx`, `src/lib/brief.js`, `src/api/client.js`).

## Running Locally

### Backend

```bash
uvicorn main:app --reload --port 8000