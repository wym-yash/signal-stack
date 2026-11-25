from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
import trafilatura

from db import get_company, update_company_research
from llm_client import FreeLLMClient


class CompanyResearchResult(BaseModel):
    industry: str = Field(description="Primary industry or vertical of the company.")
    profile_summary: str = Field(
        description="Concise executive overview of what the company offers, who it serves, and its positioning."
    )
    verified_facts: list[str] = Field(
        default_factory=list,
        description=(
            "Facts explicitly supported by the fetched website content. "
            "Do NOT treat guesses or unstated details as verified facts."
        ),
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Reasonable inferences, hypotheses, or unknowns inferred from the website or missing public details "
            "that must be validated with the founder or via research."
        ),
    )


def normalize_url(website: str) -> str:
    raw = (website or "").strip()
    if not raw:
        raise ValueError("Website URL cannot be empty.")
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw


def _extract_candidate_links(base_url: str, html: str, max_links: int = 4) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc.lower()
    keywords = ("about", "company", "product", "service", "solution", "pricing", "program", "how-it-works")
    seen: list[str] = []

    for tag in soup.find_all("a", href=True):
        href = (tag.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc.lower() != base_domain:
            continue
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        if clean_url == base_url.rstrip("/") or clean_url in seen:
            continue
        text_and_path = f"{parsed.path.lower()} {tag.get_text(' ', strip=True).lower()}"
        if any(k in text_and_path for k in keywords):
            seen.append(clean_url)
        if len(seen) >= max_links:
            break

    return seen


def fetch_public_site_context(website: str, max_subpages: int = 3) -> dict[str, Any]:
    root_url = normalize_url(website)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; SignalStackResearchBot/1.0; "
            "+https://github.com/example/signal-stack)"
        )
    }

    pages_visited: list[dict[str, Any]] = []
    combined_chunks: list[str] = []
    errors: list[str] = []

    with httpx.Client(timeout=12.0, follow_redirects=True, headers=headers) as client:
        root_html = ""
        try:
            resp = client.get(root_url)
            status = resp.status_code
            root_html = resp.text if status < 400 else ""
            extracted = trafilatura.extract(root_html, include_comments=False, include_tables=True) or ""
            if not extracted and root_html:
                soup = BeautifulSoup(root_html, "html.parser")
                for s in soup(["script", "style", "noscript"]):
                    s.decompose()
                extracted = " ".join(soup.get_text(" ", strip=True).split())

            pages_visited.append(
                {
                    "url": str(resp.url),
                    "status_code": status,
                    "chars_extracted": len(extracted),
                }
            )
            if extracted:
                combined_chunks.append(f"SOURCE URL: {resp.url}\n{extracted[:6000]}")
        except Exception as exc:
            errors.append(f"Root fetch error ({root_url}): {exc}")
            pages_visited.append({"url": root_url, "status_code": None, "chars_extracted": 0})

        if root_html and max_subpages > 0:
            sub_urls = _extract_candidate_links(str(root_url), root_html, max_links=max_subpages)
            for sub_url in sub_urls:
                try:
                    sub_resp = client.get(sub_url)
                    sub_status = sub_resp.status_code
                    sub_html = sub_resp.text if sub_status < 400 else ""
                    sub_text = trafilatura.extract(sub_html, include_comments=False, include_tables=True) or ""
                    if not sub_text and sub_html:
                        soup = BeautifulSoup(sub_html, "html.parser")
                        for s in soup(["script", "style", "noscript"]):
                            s.decompose()
                        sub_text = " ".join(soup.get_text(" ", strip=True).split())

                    pages_visited.append(
                        {
                            "url": str(sub_resp.url),
                            "status_code": sub_status,
                            "chars_extracted": len(sub_text),
                        }
                    )
                    if sub_text:
                        combined_chunks.append(f"SOURCE URL: {sub_resp.url}\n{sub_text[:4000]}")
                except Exception as exc:
                    errors.append(f"Subpage fetch error ({sub_url}): {exc}")

    combined_text = "\n\n---\n\n".join(combined_chunks)[:16000]
    return {
        "root_url": root_url,
        "pages_visited": pages_visited,
        "extracted_text": combined_text,
        "fetch_errors": errors,
    }


def run_initial_research(company_id: int, llm: Optional[FreeLLMClient] = None) -> dict[str, Any]:
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Company with id={company_id} not found.")

    llm_client = llm or FreeLLMClient()
    crawl_data = fetch_public_site_context(company["website"])

    system_prompt = (
        "You are a senior business intelligence researcher. "
        "Analyze a company from its name, optional context, and publicly fetched website text. "
        "Be strictly disciplined: ONLY put claims directly supported by the fetched website text into "
        "'verified_facts'. Put educated inferences, unverified details, missing business model details, "
        "or limitations (such as blocked/empty website text) into 'assumptions'. Never fabricate facts."
    )

    user_prompt = (
        f"Company Name: {company['name']}\n"
        f"Website: {company['website']}\n"
        f"Current Industry Input: {company.get('industry') or 'Not specified'}\n"
        f"Existing Business Context: {company.get('business_context') or 'None yet'}\n"
        f"Pages Visited: {crawl_data['pages_visited']}\n"
        f"Fetch Errors: {crawl_data['fetch_errors']}\n\n"
        f"Extracted Public Website Text:\n"
        f"{crawl_data['extracted_text'] or '[No readable public text could be extracted]'}"
    )

    result = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_model=CompanyResearchResult,
        temperature=0.15,
    )

    updated = update_company_research(
        company_id=company_id,
        profile_summary=result.profile_summary,
        verified_facts=result.verified_facts,
        assumptions=result.assumptions,
        industry=result.industry,
    )

    return {
        "company": updated,
        "crawl_metadata": {
            "pages_visited": crawl_data["pages_visited"],
            "fetch_errors": crawl_data["fetch_errors"],
            "extracted_chars": len(crawl_data["extracted_text"]),
        },
    }