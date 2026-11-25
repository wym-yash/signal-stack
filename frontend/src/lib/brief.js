export const briefMarkdown = (b) =>
  b?.markdown_content ??
  b?.markdown ??
  b?.content ??
  b?.body ??
  b?.brief_markdown ??
  b?.brief_text ??
  b?.text ??
  "";

export const briefDate = (b) => b?.created_at ?? b?.generated_at ?? b?.createdAt ?? null;

/** Split a brief into its numbered/headed sections. Falls back to one block. */
export function splitSections(md) {
  const text = String(md || "");
  for (const level of [2, 1, 3]) {
    const re = new RegExp(`^${"#".repeat(level)}\\s+(.+)$`, "gm");
    const hits = [...text.matchAll(re)];
    if (hits.length >= 3) {
      const intro = text.slice(0, hits[0].index).trim();
      const sections = hits.map((h, i) => ({
        title: h[1].trim(),
        body: text
          .slice(h.index + h[0].length, i + 1 < hits.length ? hits[i + 1].index : undefined)
          .trim(),
      }));
      return { intro, sections };
    }
  }
  return { intro: text, sections: [] };
}

/** True when a section is blank or just says nothing meaningful happened. */
export function isEmptyBody(body) {
  const t = String(body || "")
    .replace(/[*_`>#-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!t) return true;
  if (/^(none|n\/a|nothing|no data)\b/i.test(t) && t.length < 120) return true;
  return (
    t.length < 180 &&
    /\b(no|not any|nothing|without)\b[^.]{0,60}\b(development|developments|signal|signals|change|changes|update|updates|movement|activity|news)\b/i.test(
      t
    )
  );
}