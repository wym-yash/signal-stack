# Signal Stack — Company Intelligence & Executive Briefing Engine

Signal Stack is an AI-powered company intelligence and executive briefing system designed to turn a company's public footprint, founder context, competitive landscape, market shifts, and internal records into a structured **Monday Morning Intelligence Brief**.

Built using **100% free and open-source libraries** alongside genuinely free-tier LLM APIs (Google Gemini and Groq), with zero paid scraping services or paid APIs.

---

## Current Project Status

- **Backend (`backend/`)**: Complete and operational (FastAPI + SQLite + APScheduler).
- **Frontend (`frontend/`)**: Vite + React starter scaffold initialized; dashboard UI integration in progress.

---

## Core Capabilities Implemented

1. **Company Setup & Initial Public Research (`backend/researcher.py`)**
   - Accepts a company name and website URL, crawls the homepage and key internal links (`/about`, `/pricing`, `/services`, `/programs`, etc.) via `httpx` + `trafilatura` / `BeautifulSoup4`.
   - Synthesizes an initial company profile that strictly separates **verified facts** (directly backed by crawled site content) from **assumptions** (inferences or missing details requiring founder validation).

2. **Adaptive 10-Question Founder Interview (`backend/interviewer.py`)**
   - Generates 10 tailored questions per company based on its business model, industry, verified facts, and open assumptions.
   - Operates one question at a time, avoids duplicate questions, triggers targeted follow-ups when an answer warrants deeper probing, supports skipping confidential questions, allows editing past answers, and continuously updates the company's `business_context` with full change history.

3. **Four-Category Signal Stack & Internal Ingestion (`backend/signal_stack.py`)**
   - Builds and justifies intelligence sources across **Customers**, **Competitors** (5–10 rivals/substitutes), **Market**, and **Internal**.
   - Supports manual source addition, approval/deactivation/removal, and automated **context-change reassessment** (flagging low-relevance sources and recommending replacements when a company's business context shifts).
   - Parses uploaded **CSV, XLSX/XLS, PDF, and TXT** internal files to extract customer objections, lost-deal reasons, product requests, sales patterns, and emerging risks.

4. **Polite Crawler, Deduplication & Multi-Factor Ranking (`backend/crawler.py`)**
   - Checks `robots.txt` directives before fetching approved public URLs.
   - Deduplicates developments per company using SHA-256 content hashes and preserves historical crawl/signal records in SQLite.
   - Ranks signals across **Relevance (24%)**, **Business Impact (24%)**, **Urgency (16%)**, **Source Credibility (14%)**, **Recency (12%)**, and **Novelty (10%)**, while keeping source reliability, evidence strength, and strategic relevance distinct from verification status.

5. **10-Section Monday Morning Brief Generator (`backend/brief_generator.py`)**
   - Generates a structured executive Markdown report covering:
     1. Executive Summary (Top 5 developments)
     2. Customer Signals
     3. Competitor Intelligence
     4. Market Intelligence
     5. Internal Business Intelligence
     6. Opportunities Identified
     7. Risks & Threats
     8. Recommended Actions for This Week
     9. What We Should Watch
     10. Source Appendix (links, publication/discovery dates, evidence snippets, verification status, and component scores)
   - Explicitly states when a category has no meaningful development rather than fabricating filler items.

6. **Automation, Scheduling & Source-Health Audits (`backend/scheduler.py`)**
   - **Weekly Intelligence Brief**: Runs approved source checks, extracts/ranks developments, generates and stores the Monday Morning Brief, and logs run status.
   - **Monthly Signal Stack Audit**: Checks dead/failing URLs, flags duplicate or inactive sources, identifies declining relevance, recommends additions/removals, and logs audit results and failures to `job_runs`.

---

## Repository Structure

```text