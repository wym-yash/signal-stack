const STORAGE_KEY = "signal_stack_founder_session_v1";

export function getFounderSession() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.token || !parsed.founderId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function setFounderSession({ token, founderId, email = "", name = "" }) {
  const session = {
    token: String(token || "").trim(),
    founderId: String(founderId || "").trim(),
    email: String(email || "").trim(),
    name: String(name || "").trim(),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return session;
}

export function clearFounderSession() {
  window.localStorage.removeItem(STORAGE_KEY);
}

export function getAuthHeaders(extraHeaders = {}) {
  const session = getFounderSession();
  const headers = { ...extraHeaders };
  if (session?.token) {
    headers.Authorization = `Bearer ${session.token}`;
  }
  if (session?.founderId) {
    headers["X-Founder-Id"] = session.founderId;
  }
  return headers;
}

export function isCompanyOwner(company, session = getFounderSession()) {
  if (!company || !session?.founderId) return false;
  return String(company.owner_id ?? "") === String(session.founderId);
}

export function getOwnedCompanies(companies = [], session = getFounderSession()) {
  if (!Array.isArray(companies)) return [];
  if (!session?.founderId) return [];
  return companies.filter((company) => isCompanyOwner(company, session));
}