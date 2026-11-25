import { useState } from "react";
import { addSource, deleteSource, getSignalStack, setSourceStatus } from "../api/client";
import { useAction, useAsync } from "../lib/hooks";
import { fmtDate, isUrl } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorNote, Field, Loading, PageHeader } from "../components/ui";
import { CATEGORIES } from "./SignalStack";

const STATUSES = ["pending", "approved", "inactive", "removed"];
const blank = { category: "Customers", name: "", url_or_path: "", reason: "", status: "approved", reliability_score: "", relevance_score: "" };

function Health({ s }) {
  const fails = s.consecutive_failures ?? 0;
  return (
    <dl className="grid grid-cols-3 gap-3 text-xs">
      <div><dt className="text-mute">Last checked</dt><dd className="tnum mt-0.5 text-ink">{fmtDate(s.last_checked_at)}</dd></div>
      <div><dt className="text-mute">Last HTTP status</dt><dd className="tnum mt-0.5 text-ink">{s.last_status_code ?? "—"}</dd></div>
      <div><dt className="text-mute">Consecutive failures</dt><dd className={`tnum mt-0.5 font-medium ${fails >= 3 ? "text-clay" : fails > 0 ? "text-ochre" : "text-ink"}`}>{fails}</dd></div>
    </dl>
  );
}

export default function SourceManager({ company }) {
  const id = company.id;
  const [cat, setCat] = useState("");
  const [status, setStatus] = useState("");
  const [form, setForm] = useState(blank);
  const [busyId, setBusyId] = useState(null);
  const [confirmId, setConfirmId] = useState(null);
  const [rowErr, setRowErr] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const q = useAsync(() => getSignalStack(id, { category: cat, status }), [id, cat, status]);

  const add = useAction(async () => {
    const body = { category: form.category, name: form.name.trim(), url_or_path: form.url_or_path.trim(), reason: form.reason.trim(), status: form.status };
    if (form.reliability_score !== "") body.reliability_score = Number(form.reliability_score);
    if (form.relevance_score !== "") body.relevance_score = Number(form.relevance_score);
    const r = await addSource(id, body);
    setForm(blank);
    await q.reload();
    return r;
  });

  const act = async (s, fn) => {
    setBusyId(s.id); setRowErr(null);
    try { await fn(); } catch (e) { setRowErr(e); } finally { setBusyId(null); setConfirmId(null); }
  };
  const changeStatus = (s, next) => act(s, async () => {
    const u = await setSourceStatus(id, s.id, next);
    q.setData((list) => list.map((x) => (x.id === s.id ? { ...x, ...(u || {}), status: u?.status ?? next } : x)));
  });
  const remove = (s) => act(s, async () => {
    await deleteSource(id, s.id);
    q.setData((list) => list.filter((x) => x.id !== s.id));
  });

  return (
    <>
      <PageHeader kicker={company.name} title="Source manager" />
      <div className="grid gap-6 xl:grid-cols-[22rem_minmax(0,1fr)]">
        <Card aria-labelledby="add-src" className="xl:self-start">
          <h2 id="add-src" className="mb-4 text-xl">Add a custom source</h2>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
            <Field label="Category"><select className="input" value={form.category} onChange={set("category")}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label="Name"><input required className="input" value={form.name} onChange={set("name")} /></Field>
            <Field label="URL or path"><input required className="input" value={form.url_or_path} onChange={set("url_or_path")} /></Field>
            <Field label="Why include it"><textarea required className="input min-h-20" value={form.reason} onChange={set("reason")} /></Field>
            <Field label="Initial status"><select className="input" value={form.status} onChange={set("status")}>{STATUSES.slice(0, 3).map((c) => <option key={c}>{c}</option>)}</select></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Reliability"><input type="number" step="any" min="0" className="input" placeholder="optional" value={form.reliability_score} onChange={set("reliability_score")} /></Field>
              <Field label="Relevance"><input type="number" step="any" min="0" className="input" placeholder="optional" value={form.relevance_score} onChange={set("relevance_score")} /></Field>
            </div>
            <ErrorNote error={add.error} />
            <Button type="submit" busy={add.busy}>Add source</Button>
          </form>
        </Card>

        <section aria-labelledby="all-src">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <h2 id="all-src" className="text-xl">All sources {q.data && <span className="tnum text-base text-mute">({q.data.length})</span>}</h2>
            <div className="flex flex-wrap gap-3">
              <Field label="Category"><select className="input" value={cat} onChange={(e) => setCat(e.target.value)}><option value="">All</option>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
              <Field label="Status"><select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{STATUSES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            </div>
          </div>
          <div className="mb-3 space-y-3"><ErrorNote error={rowErr} /><ErrorNote error={q.error} onRetry={q.reload} /></div>
          {q.loading && !q.data && <Loading />}
          {q.data && (q.data.length ? (
            <ul className="space-y-3">
              {q.data.map((s) => (
                <li key={s.id} className="card p-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge value={s.category} tone="stone" /><Badge value={s.status} />
                    <h3 className="text-base">{s.name}</h3>
                  </div>
                  <p className="mb-3 text-sm">{isUrl(s.url_or_path) ? <a className="link" href={s.url_or_path} target="_blank" rel="noopener noreferrer">{s.url_or_path}</a> : <span className="break-all text-mute">{s.url_or_path}</span>}</p>
                  <Health s={s} />
                  <div className="mt-4 flex flex-wrap gap-2">
                    {s.status !== "approved" && <Button busy={busyId === s.id} onClick={() => changeStatus(s, "approved")}>{s.status === "pending" ? "Approve" : "Reactivate"}</Button>}
                    {s.status !== "inactive" && <Button variant="ghost" busy={busyId === s.id} onClick={() => changeStatus(s, "inactive")}>Deactivate</Button>}
                    {confirmId === s.id ? (
                      <>
                        <Button variant="danger" busy={busyId === s.id} onClick={() => remove(s)}>Confirm delete</Button>
                        <Button variant="ghost" onClick={() => setConfirmId(null)}>Cancel</Button>
                      </>
                    ) : <Button variant="danger" onClick={() => setConfirmId(s.id)}>Delete</Button>}
                  </div>
                </li>
              ))}
            </ul>
          ) : <Empty title="No sources match" hint="Change the filters, or add a source on the left." />)}
        </section>
      </div>
    </>
  );
}
