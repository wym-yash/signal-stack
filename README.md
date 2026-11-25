# Signal Stack

Signal Stack is a multi-company intelligence workspace built with FastAPI, SQLite, and React (Vite). It supports founder discovery interviews, signal source management, web/internal signal crawling, ranking, automated runs, and Monday morning brief generation with strict per-founder workspace isolation and audit tracking.

## Architecture Overview

- **Backend (`FastAPI` + `SQLite`):** Exposes REST endpoints for company management, business context updates, founder interviews, signal stack curation, crawling, ranked signal retrieval, brief generation, automation cycles/audits, and settings.
- **Frontend (`React` + `Vite`):** Provides a multi-page workspace UI with a founder ID sign-in/switcher bar, company research and context controls, interview flow, signal stack/crawl views, Monday morning brief viewer/exporter, and automation/run controls.
- **Access Control & Auditing:** Scopes workspaces to `owner_id` and records allowed and denied access attempts in `audit_logs` using `X-Founder-Id` or `Authorization` credentials.
- **Brief Generation & LLM Fallback:** Collects stored signals and company context, trims prompt payloads to stay within free-tier token limits, uses `FreeLLMClient` across configured providers, and falls back to a deterministic structured brief when LLM providers hit quota or rate limits.

## Key Features

### Multi-Company Workspace Ownership & Isolation
- Each company workspace is associated with an `owner_id`.
- Unauthenticated requests or requests from another founder ID do not expose owned workspaces or confidential workspace assets, returning unauthorized/forbidden responses (`401`/`403`) where applicable.
- The frontend includes a founder ID sign-in/switcher bar so you can test switching identities or signing out directly in the UI.

### Audit Logging
- Protected endpoints for companies, context updates, interviews, signal stacks, crawls, signals, briefs, runs, and settings log access outcomes (`allowed` vs. `denied`) in `audit_logs`.
- Useful for verifying that unauthorized cross-founder reads/writes are blocked and recorded cleanly.

### Founder Interview & Business Context
- Structured interview flow (`start`, `next`, `answer`, `edit`, `skip`) that folds answers into `business_context`.
- Supports updating `business_context` with change summaries, tracking verified facts and assumptions, reviewing `context_history`, and reassessing active signal sources when context changes.

### Signal Stack, Crawling & Ranking
- Organizes sources across `Customers`, `Competitors`, `Market`, and `Internal` categories, including internal file uploads.
- Supports generating, approving, deactivating, or removing sources, running crawls, and querying ranked signals with category, competitor, verification status, and score filters.

### Resilient Monday Morning Brief Generation
- Caps signal count (`MAX_SIGNALS_FOR_BRIEF`) and clips long text fields (`summary`, `evidence_snippet`, `business_context`, `profile_summary`) to prevent `413` token-per-minute rejections on tight free-tier limits.
- Wraps `FreeLLMClient.generate_structured(...)` with a deterministic fallback builder (`_build_fallback_brief`) so brief generation still produces a structured markdown brief when providers return `429` quota/rate-limit errors or fail.
- Renders saved briefs from `markdown_content` in the UI, splits sections cleanly, and supports copying markdown or downloading a `.md` file.

## Project Structure

```text
.
├── backend/
│   ├── main.py              # FastAPI routes, auth/ownership enforcement, audit logging
│   ├── db.py                # SQLite connection helpers, schema, owner_id & audit_logs queries
│   ├── brief_generator.py   # Prompt compaction, structured brief schema, fallback & markdown renderer
│   ├── llm_client.py        # FreeLLMClient wrapper and provider fallback logic
│   ├── crawler.py           # Signal crawling and signal listing/ranking queries
│   └── signal_stack.py      # Source management and signal stack generation
└── frontend/
    ├── src/
    │   ├── App.jsx          # Main layout and founder sign-in/switcher bar
    │   ├── api/client.js    # API client helpers and auth header attachment
    │   ├── lib/auth.js      # Founder identity storage and header builder
    │   ├── lib/brief.js     # Brief markdown/date extractors and section helpers
    │   └── pages/Brief.jsx  # Monday morning brief view, history selector, copy & .md export

SIGNAL STACK - LOCAL RUN & VERIFICATION GUIDE

===========================================



1. ENVIRONMENT SETUP

--------------------

- Ensure Python (3.10+) and Node.js / npm are installed.

- Optional: Add LLM keys to your .env file (in the project root or backend/

  depending on your env loader):

    GEMINI_API_KEY=your_gemini_api_key_here

    GROQ_API_KEY=your_groq_api_key_here

- Note: Brief generation trims prompt payloads to stay within free-tier

  token ceilings and falls back to a deterministic structured markdown brief

  from stored signals if LLM providers hit rate/quota limits or are unconfigured.



2. START THE BACKEND (FASTAPI)

------------------------------

Open a terminal in the backend directory and run:

  uvicorn main:app --reload --port 8000



Backend URL:

  http://127.0.0.1:8000



3. START THE FRONTEND (REACT + VITE)

------------------------------------

Open a second terminal in the frontend directory and run:

  npm install

  npm run dev



- By default, the frontend connects to http://127.0.0.1:8000.

- If using another backend URL, set VITE_API_BASE before starting Vite.



4. QUICK END-TO-END SMOKE TEST

-------------------------------

a) Founder Identity & Workspace Isolation:

   - Sign in using the founder sign-in/switcher bar in the UI (e.g., founder-a),

     or pass X-Founder-Id / Authorization headers in API calls.

   - Create or select a company owned by founder-a and confirm owned assets

     are hidden when signed out or viewed under a different founder ID.

   - Check SQLite audit_logs to confirm allowed and denied access attempts

     are recorded.



b) Interview, Signal Stack & Crawl:

   - Run through interview prompts and update business context as needed.

   - Generate or manage sources and run a crawl to collect signals.



c) Monday Morning Brief:

   - Open "Monday morning brief" and click "Generate brief".

   - Verify the brief renders its sections in the UI (reading markdown_content),appears in brief history, and supports "Copy markdown" and "Download .md".

The google drive link with all demo: https://drive.google.com/drive/folders/1Ti5QAy2y0p11TRhfq-ism4Ny-vxyOPrR?usp=drive_link