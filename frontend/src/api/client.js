/**
 * Signal Stack API client: one documented helper per FastAPI endpoint.
 * Base URL: VITE_API_BASE if set, otherwise http://127.0.0.1:8000
 *
 * @typedef {{ id:number, name:string, website:string, industry?:string|null, business_context?:string|null, profile_summary?:string|null, owner_id?:string|null }} Company
 * @typedef {{ id:number, category:"Customers"|"Competitors"|"Market"|"Internal", name:string, url_or_path:string, reason:string, reliability_score?:number, relevance_score?:number, status:"pending"|"approved"|"inactive"|"removed", last_checked_at?:string|null, last_status_code?:number|null, consecutive_failures?:number }} Source
 * @typedef {{ id:number, title:string, category:string, competitor_name?:string|null, signal_stance:"opportunity"|"threat"|"neutral", verified_status:"verified"|"partially_verified"|"unverified", total_rank_score:number, relevance_score:number, impact_score:number, urgency_score:number, credibility_score:number, recency_score:number, novelty_score:number, evidence_strength_score:number, summary:string, evidence_snippet?:string, source_url?:string, interpretation?:string, recommended_action?:string }} Signal
 * @typedef {{ id:number, question_text?:string, answer_text?:string|null, skipped?:boolean }} InterviewMessage
 * @typedef {{ completed:boolean, progress:{primary_completed:number, primary_total:number}, current_question:InterviewMessage|null, messages:InterviewMessage[] }} InterviewState
 */

import { getAuthHeaders } from "../lib/auth";

export const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { status = 0, body = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function detailToMessage(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && d.msg ? `${(d.loc || []).filter((x) => x !== "body").join(".")}: ${d.msg}` : JSON.stringify(d)))
      .join("; ");
  }
  try { return JSON.stringify(detail); } catch { return String(detail); }
}

function buildQuery(query) {
  if (!query) return "";
  const p = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    p.set(k, typeof v === "boolean" ? String(v) : v);
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function request(path, { method = "GET", query, body, formData } = {}) {
  const init = { method, headers: getAuthHeaders({ Accept: "application/json" }) };
  if (formData) init.body = formData; // browser sets the multipart boundary
  else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`${API_BASE}${path}${buildQuery(query)}`, init);
  } catch {
    throw new ApiError(`Cannot reach the backend at ${API_BASE}. Check that FastAPI is running and allows CORS from this origin.`);
  }
  const text = await res.text();
  let data = null;
  if (text) { try { data = JSON.parse(text); } catch { data = text; } }
  if (!res.ok) {
    const msg = detailToMessage(data && data.detail) || (typeof data === "string" && data) || `${res.status} ${res.statusText}`;
    throw new ApiError(msg, { status: res.status, body: data });
  }
  return data;
}

const co = (id) => `/companies/${encodeURIComponent(id)}`;

// ---- Health & companies ----------------------------------------------------
/** @returns {Promise<{status:string, available_free_llm_providers:string[]}>} */
export const getHealth = () => request("/health");
/** @returns {Promise<Company[]>} */
export const listCompanies = () => request("/companies");
/** @param {{name:string, website:string, industry?:string, business_context?:string}} body @returns {Promise<Company>} */
export const createCompany = (body) => request("/companies", { method: "POST", body });
/** @returns {Promise<Company & {verified_facts:string[], assumptions:string[], context_history:object[]}>} */
export const getCompany = (id) => request(co(id));
/** @returns {Promise<{company:Company, crawl_metadata:{pages_visited:any, fetch_errors:any, extracted_chars:number}}>} */
export const researchCompany = (id) => request(`${co(id)}/research`, { method: "POST" });
/**
 * @param {{business_context:string, change_summary?:string, reassess_signal_stack:boolean}} body
 * @returns {Promise<{company:Company, change_summary:string, deactivated_source_ids:number[], deprecation_explanations:any, added_sources:Source[], active_signal_stack:Source[]}>}
 */
export const updateContext = (id, body) => request(`${co(id)}/context`, { method: "PUT", body });

// ---- Interview -------------------------------------------------------------
/** @returns {Promise<{messages:InterviewMessage[], next_state:InterviewState}>} */
export const startInterview = (id) => request(`${co(id)}/interview/start`, { method: "POST" });
/** @returns {Promise<InterviewState>} */
export const getInterviewNext = (id) => request(`${co(id)}/interview/next`);
/** @param {{message_id:number, answer_text?:string, skip?:boolean, allow_followup?:boolean}} body @returns {Promise<InterviewState & {business_context:string}>} */
export const submitAnswer = (id, body) => request(`${co(id)}/interview/answer`, { method: "POST", body });
/** @param {{message_id:number, new_answer_text?:string, skip?:boolean}} body @returns {Promise<{business_context:string, messages:InterviewMessage[]}>} */
export const editAnswer = (id, body) => request(`${co(id)}/interview/edit`, { method: "PUT", body });

// ---- Signal stack & sources ------------------------------------------------
/** @param {{category?:string, status?:string}} [filters] @returns {Promise<Source[]>} */
export const getSignalStack = (id, filters = {}) => request(`${co(id)}/signal-stack`, { query: filters });
/** @returns {Promise<Source[]>} */
export const generateSignalStack = (id, minSources = 20) =>
  request(`${co(id)}/signal-stack/generate`, { method: "POST", query: { min_sources: minSources } });
/** @param {{category:string, name:string, url_or_path:string, reason:string, status?:string, reliability_score?:number, relevance_score?:number}} body @returns {Promise<Source>} */
export const addSource = (id, body) => request(`${co(id)}/signal-stack/sources`, { method: "POST", body });
/** @param {"pending"|"approved"|"inactive"|"removed"} status @returns {Promise<Source>} */
export const setSourceStatus = (id, sourceId, status) =>
  request(`${co(id)}/signal-stack/sources/${encodeURIComponent(sourceId)}/status`, { method: "PATCH", body: { status } });
/** @returns {Promise<{deleted:true, source_id:number}>} */
export const deleteSource = (id, sourceId) =>
  request(`${co(id)}/signal-stack/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
/** @param {File} file .csv .xlsx .xls .pdf .txt @returns {Promise<{source:Source, company_domain:string, extracted_count:number, signals:Signal[]}>} */
export const uploadInternalFile = (id, file) => {
  const formData = new FormData();
  formData.append("file", file);
  return request(`${co(id)}/signal-stack/internal-upload`, { method: "POST", formData });
};

// ---- Crawl & signals -------------------------------------------------------
/** @returns {Promise<{company_id:number, sources_checked:number, sources_failed:number, signals_processed:number, errors:any[], signals:Signal[]}>} */
export const crawlSources = (id, maxSources = 25) =>
  request(`${co(id)}/crawl`, { method: "POST", query: { max_sources: maxSources } });
/** @param {{category?:string, competitor_name?:string, verified_status?:string, min_rank_score?:number, limit?:number}} [filters] @returns {Promise<Signal[]>} */
export const getSignals = (id, filters = {}) => request(`${co(id)}/signals`, { query: { limit: 100, ...filters } });

// ---- Briefs ----------------------------------------------------------------
/** @returns {Promise<{brief:object, structured:object}>} */
export const generateBrief = (id, briefType = "weekly") =>
  request(`${co(id)}/briefs/generate`, { method: "POST", query: { brief_type: briefType } });
/** @returns {Promise<object[]>} */
export const listBriefs = (id) => request(`${co(id)}/briefs`);

// ---- Automation ------------------------------------------------------------
/** @returns {Promise<{crawl_summary:object, brief:object, brief_structured:object}>} */
export const runManualCycle = (id) => request(`${co(id)}/runs/manual`, { method: "POST" });
/** @returns {Promise<{company_id:number, audited_at:string, dead_or_failing_sources:any[], duplicate_sources:any[], inactive_sources:any[], declining_relevance_notes:any[], audit_summary:any, recommendations:any[], applied_actions:any[]}>} */
export const runMonthlyAudit = (id, applyRecommendations = false) =>
  request(`${co(id)}/runs/monthly-audit`, { method: "POST", query: { apply_recommendations: applyRecommendations } });
/** @returns {Promise<object[]>} */
export const listRuns = (id, limit = 50) => request(`${co(id)}/runs`, { query: { limit } });
/** @returns {Promise<object>} */
export const getSettings = (id) => request(`${co(id)}/settings`);
/** @param {{briefing_day?:string, briefing_time?:string, timezone?:string, monitoring_frequency?:string, source_refresh_frequency?:string, monthly_audit_day?:number|string}} body */
export const updateSettings = (id, body) => request(`${co(id)}/settings`, { method: "PUT", body });