import { useMemo, useState } from "react";
import { crawlSources, getSignals } from "../api/client";
import { useAction, useAsync, useDebounced } from "../lib/hooks";
import { asItems, fmtDate, fmtScore, isUrl } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorNote, Field, List, Loading, PageHeader, ScoreBar, Segmented, Stat } from "../components/ui";
import { CATEGORIES } from "./SignalStack";

const SCORES = [
  ["relevance_score", "Relevance"], ["impact_score", "Impact"], ["urgency_score", "Urgency"], ["credibility_score", "Credibility"],
  ["recency_score", "Recency"], ["novelty_score", "Novelty"], ["evidence_strength_score", "Evidence strength"],
];
const dateOf = (s) => new Date(s.published_at ?? s.created_at ?? s.detected_at ?? 0).getTime() || 0;

function SignalCard({ s }) {
  return (
    <article className="card p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge value={s.category} tone="stone" />
        {s.competitor_name && <Badge value={s.competitor_name} tone="stone" />}
        <Badge value={s.signal_stance} />
        <Badge value={s.verified_status} />
        <span className="ml-auto text-xs text-mute">{fmtDate(s.published_at ?? s.created_at ?? s.detected_at)}</span>
      </div>
      <div className="mb-4 flex items-start justify-between gap-4">
        <h2 className="text-xl leading-snug">{s.title}</h2>
        <div className="shrink-0 text-right">
          <p className="tnum font-display text-3xl leading-none text-olive-deep">{fmtScore(s.total_rank_score)}</p>
          <p className="mt-1 text-xs text-mute">Total rank</p>
        </div>
      </div>
      <div className="mb-4 grid grid-cols-2 gap-x-5 gap-y-3 sm:grid-cols-4">
        {SCORES.map(([k, l]) => <ScoreBar key={k} label={l} value={s[k]} />)}
      </div>
      <p className="text-[15px] leading-relaxed">{s.summary}</p>
      {s.evidence_snippet && (
        <blockquote className="mt-3 border-l-2 border-line pl-4 text-sm text-mute">
          “{s.evidence_snippet}”
          {s.source_url && <footer className="mt-1.5">{isUrl(s.source_url) ? <a className="link" href={s.source_url} target="_blank" rel="noopener noreferrer">{s.source_url}</a> : s.source_url}</footer>}
        </blockquote>
      )}
      {!s.evidence_snippet && s.source_url && <p className="mt-3 text-sm"><a className="link" href={s.source_url} target="_blank" rel="noopener noreferrer">{s.source_url}</a></p>}
      {(s.interpretation || s.recommended_action) && (
        <div className="mt-5 space-y-4 rounded-md border border-olive/25 bg-olive/5 p-4">
          {s.interpretation && <div><h3 className="mb-1 text-base text-olive-deep">Strategic interpretation</h3><p className="text-sm leading-relaxed">{s.interpretation}</p></div>}
          {s.recommended_action && <div><h3 className="mb-1 text-base text-olive-deep">Recommended action</h3><p className="text-sm leading-relaxed">{s.recommended_action}</p></div>}
        </div>
      )}
    </article>
  );
}

export default function Feed({ company }) {
  const id = company.id;
  const [f, setF] = useState({ category: "", competitor_name: "", verified_status: "", min_rank_score: "" });
  const [sort, setSort] = useState("ranked");
  const dComp = useDebounced(f.competitor_name);
  const dMin = useDebounced(f.min_rank_score);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const q = useAsync(
    () => getSignals(id, { category: f.category, competitor_name: dComp.trim(), verified_status: f.verified_status, min_rank_score: dMin === "" ? undefined : Number(dMin) }),
    [id, f.category, dComp, f.verified_status, dMin]
  );
  const crawl = useAction(async () => { const r = await crawlSources(id, 25); await q.reload(); return r; });

  const rows = useMemo(() => {
    const list = [...(q.data || [])];
    return sort === "ranked" ? list.sort((a, b) => (b.total_rank_score ?? 0) - (a.total_rank_score ?? 0)) : list.sort((a, b) => dateOf(b) - dateOf(a));
  }, [q.data, sort]);

  const r = crawl.result;
  const errs = asItems(r?.errors);

  return (
    <>
      <PageHeader kicker={company.name} title="Intelligence feed">
        <Button busy={crawl.busy} onClick={crawl.run}>{crawl.busy ? "Crawling sources…" : "Crawl approved sources"}</Button>
      </PageHeader>
      <div className="mb-6 space-y-4">
        <ErrorNote error={crawl.error} />
        {r && (
          <Card aria-label="Crawl result" className="p-4" role="status">
            <div className="grid grid-cols-3 gap-3"><Stat label="Sources checked" value={r.sources_checked} /><Stat label="Sources failed" value={r.sources_failed} /><Stat label="Signals processed" value={r.signals_processed} /></div>
            {errs.length > 0 && <details className="mt-3 text-sm"><summary className="min-h-11 cursor-pointer py-2 text-clay">Show {errs.length} crawl errors</summary><List items={errs} tone="text-mute" /></details>}
          </Card>
        )}
      </div>

      <div className="mb-6 flex flex-wrap items-end gap-3">
        <Field label="Category"><select className="input" value={f.category} onChange={set("category")}><option value="">All</option>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="Competitor"><input className="input" value={f.competitor_name} onChange={set("competitor_name")} placeholder="Exact name" /></Field>
        <Field label="Verification"><select className="input" value={f.verified_status} onChange={set("verified_status")}><option value="">All</option><option value="verified">Verified</option><option value="partially_verified">Partially verified</option><option value="unverified">Unverified</option></select></Field>
        <Field label="Min rank score"><input type="number" step="any" min="0" className="input w-32" value={f.min_rank_score} onChange={set("min_rank_score")} /></Field>
        <div className="sm:ml-auto"><Segmented label="Sort" value={sort} onChange={setSort} options={[{ value: "ranked", label: "Ranked" }, { value: "recent", label: "Newest" }]} /></div>
      </div>

      <ErrorNote error={q.error} onRetry={q.reload} />
      {q.loading && !q.data && <Loading label="Loading signals…" />}
      {q.data && (rows.length ? (
        <div className="space-y-5">{rows.map((s) => <SignalCard key={s.id} s={s} />)}</div>
      ) : (
        <Empty title="No signals match" hint="Crawl your approved sources to collect signals, or loosen the filters." />
      ))}
    </>
  );
}
