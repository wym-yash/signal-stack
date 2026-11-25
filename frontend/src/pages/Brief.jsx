import { useEffect, useMemo, useState } from "react";
import { generateBrief, listBriefs } from "../api/client";
import { useAction, useAsync } from "../lib/hooks";
import { fmtDate } from "../lib/format";
import { briefDate, briefMarkdown, isEmptyBody, splitSections } from "../lib/brief";
import { Button, Card, Empty, ErrorNote, Field, Loading, PageHeader } from "../components/ui";
import Markdown from "../components/Markdown";

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }
}

export default function Brief({ company }) {
  const id = company.id;
  const q = useAsync(() => listBriefs(id), [id]);
  const [sel, setSel] = useState(null);
  const [copied, setCopied] = useState(false);

  const briefs = useMemo(
    () => [...(q.data || [])].sort((a, b) => (new Date(briefDate(b)) || 0) - (new Date(briefDate(a)) || 0) || (b.id ?? 0) - (a.id ?? 0)),
    [q.data]
  );
  useEffect(() => { if (briefs.length && !briefs.some((b) => b.id === sel)) setSel(briefs[0].id); }, [briefs, sel]);
  const current = briefs.find((b) => b.id === sel);
  const md = briefMarkdown(current);
  const { intro, sections } = useMemo(() => splitSections(md), [md]);

  const gen = useAction(async () => {
    const r = await generateBrief(id, "weekly");
    await q.reload();
    if (r?.brief?.id != null) setSel(r.brief.id);
    return r;
  });

  const copy = async () => { if (await copyText(md)) { setCopied(true); setTimeout(() => setCopied(false), 2000); } };
  const download = () => {
    const day = (briefDate(current) ? new Date(briefDate(current)) : new Date()).toISOString().slice(0, 10);
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `${company.name.replace(/\W+/g, "-").toLowerCase()}-brief-${day}.md` });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader kicker={company.name} title="Monday morning brief">
        <Button busy={gen.busy} onClick={gen.run}>{gen.busy ? "Writing the brief…" : "Generate brief"}</Button>
      </PageHeader>
      <div className="mb-5 space-y-3"><ErrorNote error={gen.error} /><ErrorNote error={q.error} onRetry={q.reload} /></div>
      {q.loading && !q.data && <Loading />}
      {q.data && !briefs.length && <Empty title="No briefs yet" hint="Generate one from the signals collected so far." />}
      {current && (
        <>
          <div className="mb-6 flex flex-wrap items-end gap-3">
            <Field label="Brief history" className="min-w-64">
              <select className="input" value={sel ?? ""} onChange={(e) => setSel(Number(e.target.value))}>
                {briefs.map((b) => <option key={b.id} value={b.id}>{fmtDate(briefDate(b))}{b.brief_type ? ` · ${b.brief_type}` : ""}</option>)}
              </select>
            </Field>
            <div className="flex flex-wrap gap-2 sm:ml-auto">
              <Button variant="ghost" onClick={copy}>{copied ? "Copied" : "Copy markdown"}</Button>
              <Button variant="ghost" onClick={download}>Download .md</Button>
            </div>
          </div>
          <p className="sr-only" role="status">{copied ? "Markdown copied to clipboard" : ""}</p>

          {!md.trim() ? <Empty title="This brief has no content" hint="Generate a new one." /> : sections.length ? (
            <div className="space-y-4">
              {intro && <Card className="p-5"><Markdown>{intro}</Markdown></Card>}
              {sections.map((s, i) => {
                const empty = isEmptyBody(s.body);
                return (
                  <Card key={i} aria-label={s.title} className={`p-5 ${empty ? "bg-paper" : ""}`}>
                    <h2 className="mb-2 text-xl">{s.title}</h2>
                    {empty ? (
                      <p className="text-sm text-mute">No meaningful development this week.{s.body && s.body.length < 180 ? ` ${s.body.replace(/[*_`>#-]/g, "").trim()}` : ""}</p>
                    ) : <Markdown>{s.body}</Markdown>}
                  </Card>
                );
              })}
            </div>
          ) : <Card><Markdown>{md}</Markdown></Card>}
        </>
      )}
    </>
  );
}
