import { useEffect, useState } from "react";
import { getCompany, updateContext } from "../api/client";
import { useAction, useAsync } from "../lib/hooks";
import { asItems, fmtDate } from "../lib/format";
import { diffText } from "../lib/diff";
import { Badge, Button, Card, Empty, ErrorNote, Field, List, Loading, PageHeader, Toggle } from "../components/ui";
import Facts from "../components/Facts";

function Diff({ entry }) {
  const before = entry.old_context ?? entry.previous_context ?? entry.old_value ?? entry.before;
  const after = entry.new_context ?? entry.business_context ?? entry.new_value ?? entry.after;
  if (typeof before === "string" && typeof after === "string") {
    const rows = diffText(before, after);
    return (
      <ul className="mt-3 space-y-1 text-sm">
        {rows.map((r, i) => (
          <li key={i} className={`flex gap-2 rounded px-2 py-1 ${r.type === "add" ? "bg-moss/10 text-moss" : r.type === "del" ? "bg-clay/10 text-clay line-through" : "text-mute"}`}>
            <span aria-hidden="true" className="w-3 shrink-0 font-medium">{r.type === "add" ? "+" : r.type === "del" ? "−" : ""}</span>
            <span className="sr-only">{r.type === "add" ? "Added: " : r.type === "del" ? "Removed: " : "Unchanged: "}</span>
            <span>{r.text}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (typeof entry.diff === "string") return <pre className="mt-3 overflow-x-auto rounded bg-sand p-3 text-xs">{entry.diff}</pre>;
  return null;
}

function ChangeReport({ r }) {
  const deactivated = asItems(r.deprecation_explanations);
  const added = r.added_sources || [];
  return (
    <div className="mt-5 space-y-4 rounded-md border border-line bg-paper p-4" role="status">
      {r.change_summary && <p className="text-sm"><span className="font-medium">Change summary:</span> {r.change_summary}</p>}
      <div>
        <h3 className="mb-1.5 text-base">Sources deactivated ({r.deactivated_source_ids?.length ?? 0})</h3>
        {deactivated.length ? <List items={deactivated} tone="text-mute" /> : <p className="text-sm text-mute">No sources were deactivated.</p>}
      </div>
      <div>
        <h3 className="mb-1.5 text-base">Sources added ({added.length})</h3>
        {added.length ? (
          <ul className="space-y-1.5 text-sm">
            {added.map((s) => <li key={s.id} className="flex flex-wrap items-center gap-2"><Badge value={s.category} tone="stone" /> <span>{s.name}</span><span className="text-mute">{s.reason}</span></li>)}
          </ul>
        ) : <p className="text-sm text-mute">No new sources were added.</p>}
      </div>
      {r.active_signal_stack && <p className="text-sm text-mute">{r.active_signal_stack.length} sources are now active.</p>}
    </div>
  );
}

export default function Profile({ company, onChanged, go }) {
  const id = company.id;
  const q = useAsync(() => getCompany(id), [id]);
  const [ctx, setCtx] = useState("");
  const [summary, setSummary] = useState("");
  const [reassess, setReassess] = useState(true);
  useEffect(() => { if (q.data) setCtx(q.data.business_context || ""); }, [q.data]);

  const save = useAction(async () => {
    const r = await updateContext(id, { business_context: ctx, change_summary: summary.trim() || undefined, reassess_signal_stack: reassess });
    setSummary("");
    await q.reload();
    onChanged?.();
    return r;
  });

  const c = q.data;
  return (
    <>
      <PageHeader kicker={company.name} title="Intelligence profile">
        <Button variant="ghost" onClick={() => go("interview")}>Refine in the interview</Button>
      </PageHeader>
      {q.loading && !c && <Loading />}
      <ErrorNote error={q.error} onRetry={q.reload} />
      {c && (
        <div className="space-y-8">
          <Card aria-labelledby="summary">
            <h2 id="summary" className="mb-2 text-xl">Profile summary</h2>
            {c.profile_summary ? <p className="max-w-3xl whitespace-pre-wrap text-[15px] leading-relaxed">{c.profile_summary}</p>
              : <p className="text-sm text-mute">No summary yet. Run initial research from Company Setup.</p>}
          </Card>

          <Facts verified={c.verified_facts} assumptions={c.assumptions} />

          <div className="grid gap-6 lg:grid-cols-2">
            <Card aria-labelledby="ctx">
              <h2 id="ctx" className="mb-1 text-xl">Business context</h2>
              <p className="mb-4 text-sm text-mute">Changing this can retire outdated sources and add new ones.</p>
              <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
                <Field label="Edit business context"><textarea className="input min-h-48" value={ctx} onChange={(e) => setCtx(e.target.value)} /></Field>
                <Field label="What changed? (optional)"><input className="input" value={summary} onChange={(e) => setSummary(e.target.value)} /></Field>
                <Toggle checked={reassess} onChange={setReassess} label="Reassess the signal stack" hint="Deactivate sources that no longer fit and add new ones." />
                <ErrorNote error={save.error} />
                <Button type="submit" busy={save.busy} disabled={!ctx.trim()}>Save context</Button>
              </form>
              {save.result && <ChangeReport r={save.result} />}
            </Card>

            <Card aria-labelledby="history">
              <h2 id="history" className="mb-4 text-xl">Context history</h2>
              {c.context_history?.length ? (
                <ol className="space-y-5">
                  {[...c.context_history].reverse().map((h, i) => (
                    <li key={h.id ?? i} className="border-b border-line pb-5 last:border-0 last:pb-0">
                      <p className="text-xs text-mute">{fmtDate(h.created_at ?? h.changed_at ?? h.timestamp)}</p>
                      <p className="mt-0.5 text-sm font-medium">{h.change_summary || "Context updated"}</p>
                      <Diff entry={h} />
                    </li>
                  ))}
                </ol>
              ) : <Empty title="No changes logged" hint="Edits to the business context will show up here with a diff." />}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
