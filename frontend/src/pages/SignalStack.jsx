import { useState } from "react";
import { generateSignalStack, getSignalStack, uploadInternalFile } from "../api/client";
import { useAction, useAsync } from "../lib/hooks";
import { isUrl } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorNote, Loading, PageHeader, ScoreBar, Segmented } from "../components/ui";

export const CATEGORIES = ["Customers", "Competitors", "Market", "Internal"];
const ALLOWED = [".csv", ".xlsx", ".xls", ".pdf", ".txt"];

export function SourceCard({ s }) {
  return (
    <article className="card p-4">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h3 className="text-base leading-snug">{s.name}</h3>
        <Badge value={s.status} />
      </div>
      <p className="mb-2 text-sm">
        {isUrl(s.url_or_path) ? <a className="link" href={s.url_or_path} target="_blank" rel="noopener noreferrer">{s.url_or_path}</a> : <span className="break-all text-mute">{s.url_or_path}</span>}
      </p>
      <p className="mb-3 text-sm text-mute"><span className="font-medium text-ink">Why: </span>{s.reason}</p>
      <div className="grid grid-cols-2 gap-4">
        <ScoreBar label="Reliability" value={s.reliability_score} />
        <ScoreBar label="Relevance" value={s.relevance_score} />
      </div>
    </article>
  );
}

function InternalUpload({ id, onDone }) {
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState(null);
  const [localErr, setLocalErr] = useState(null);
  const up = useAction((f) => uploadInternalFile(id, f));

  const pick = (f) => {
    if (!f) return;
    if (!ALLOWED.some((e) => f.name.toLowerCase().endsWith(e))) {
      setFile(null);
      setLocalErr(`${f.name} isn't supported. Use ${ALLOWED.join(", ")}.`);
      return;
    }
    setLocalErr(null);
    setFile(f);
  };
  const send = async () => {
    const r = await up.run(file);
    if (r) { setFile(null); onDone?.(r); }
  };
  const r = up.result;

  return (
    <Card aria-labelledby="upload">
      <h2 id="upload" className="mb-1 text-xl">Internal intelligence</h2>
      <p className="mb-4 text-sm text-mute">Upload sales exports, call notes or reports. We extract signals from them and add the file to the Internal category.</p>
      <label
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-6 py-10 text-center transition duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-olive ${drag ? "border-olive bg-olive/5" : "border-line bg-paper hover:border-olive/60"}`}
      >
        <input type="file" className="sr-only" accept={ALLOWED.join(",")} onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
        <span className="font-medium">{file ? file.name : "Drop a file here, or browse"}</span>
        <span className="text-sm text-mute">{file ? `${(file.size / 1024).toFixed(0)} KB ready to upload` : "CSV, XLSX, XLS, PDF or TXT"}</span>
      </label>
      {localErr && <p role="alert" className="mt-3 text-sm text-clay">{localErr}</p>}
      <div className="mt-3"><ErrorNote error={up.error} /></div>
      <div className="mt-3"><Button busy={up.busy} disabled={!file} onClick={send}>{up.busy ? "Extracting signals…" : "Upload and extract"}</Button></div>
      {r && (
        <div className="mt-4 rounded-md border border-line bg-paper p-4 text-sm" role="status">
          <p><span className="font-medium">{r.source?.name}</span> added for {r.company_domain}. {r.extracted_count} signals extracted.</p>
          {r.signals?.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-mute">{r.signals.slice(0, 5).map((s, i) => <li key={s.id ?? i}>{s.title}</li>)}</ul>}
        </div>
      )}
    </Card>
  );
}

export default function SignalStack({ company }) {
  const id = company.id;
  const [cat, setCat] = useState("Customers");
  const q = useAsync(() => getSignalStack(id), [id]);
  const gen = useAction(async () => { const r = await generateSignalStack(id, 20); q.setData(r); return r; });
  const all = q.data || [];
  const rows = all.filter((s) => s.category === cat);
  const opts = CATEGORIES.map((c) => ({ value: c, label: `${c} (${all.filter((s) => s.category === c).length})` }));

  return (
    <>
      <PageHeader kicker={company.name} title="Signal stack">
        <Button busy={gen.busy} onClick={gen.run}>{gen.busy ? "Generating sources…" : "Generate signal stack (20+ sources)"}</Button>
      </PageHeader>
      <div className="mb-5 space-y-3">
        <ErrorNote error={gen.error} />
        {gen.result && <p role="status" className="text-sm text-mute">Generated {gen.result.length} sources across four categories.</p>}
      </div>
      <div className="mb-5"><Segmented label="Category" options={opts} value={cat} onChange={setCat} /></div>
      {q.loading && !q.data && <Loading />}
      <ErrorNote error={q.error} onRetry={q.reload} />
      {q.data && (rows.length ? (
        <div className="grid gap-4 md:grid-cols-2">{rows.map((s) => <SourceCard key={s.id} s={s} />)}</div>
      ) : (
        <Empty title={`No ${cat.toLowerCase()} sources yet`} hint={all.length ? "Generate again or add one in the Source Manager." : "Generate the signal stack to get a first set of sources."} />
      ))}
      <div className="mt-10"><InternalUpload id={id} onDone={() => q.reload()} /></div>
    </>
  );
}
