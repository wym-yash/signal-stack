export function fmtDate(v) {
  if (!v) return "—";
  let s = String(v);
  // Naive timestamps from SQLite/Python (no zone) are treated as UTC.
  if (/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d(:\d\d(\.\d+)?)?$/.test(s)) s = s.replace(" ", "T") + "Z";
  const d = new Date(s);
  if (isNaN(d)) return String(v);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function fmtScore(v) {
  if (typeof v !== "number" || isNaN(v)) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

/** Bar width in percent. Handles 0–1, 0–10 and 0–100 score scales. */
export function pct(v) {
  if (typeof v !== "number" || isNaN(v)) return 0;
  if (v <= 1) return Math.max(0, v * 100);
  if (v <= 10) return v * 10;
  return Math.min(v, 100);
}

export const isUrl = (s) => /^https?:\/\//i.test(String(s || ""));

export function looseText(v) {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(looseText).join("; ");
  const pick = v.explanation ?? v.reason ?? v.summary ?? v.message ?? v.note ?? v.recommendation;
  if (pick) {
    const head = v.name ?? v.source_name ?? (v.source_id != null ? `#${v.source_id}` : "");
    return head ? `${head} — ${looseText(pick)}` : looseText(pick);
  }
  try { return JSON.stringify(v); } catch { return String(v); }
}

/** Normalise arrays, dicts or strings into a list of display strings. */
export function asItems(v) {
  if (v == null || v === "") return [];
  if (Array.isArray(v)) return v.map(looseText).filter(Boolean);
  if (typeof v === "object") return Object.entries(v).map(([k, val]) => `#${k} — ${looseText(val)}`);
  return [String(v)];
}

export function countOf(v) {
  if (v == null) return 0;
  if (typeof v === "number") return v;
  if (Array.isArray(v)) return v.length;
  if (typeof v === "object") return Object.keys(v).length;
  return 0;
}

export function qText(m) {
  return m?.question_text ?? m?.question ?? m?.content ?? m?.text ?? m?.prompt ?? "";
}
export function aText(m) {
  return m?.answer_text ?? m?.answer ?? "";
}
