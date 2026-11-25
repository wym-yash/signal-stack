import { useEffect, useState } from "react";
import { getSettings, listRuns, runManualCycle, runMonthlyAudit, updateSettings } from "../api/client";
import { useAction, useAsync } from "../lib/hooks";
import { asItems, fmtDate, looseText } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorNote, Field, List, Loading, PageHeader, Stat, Toggle } from "../components/ui";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const FIELDS = ["briefing_day", "briefing_time", "timezone", "monitoring_frequency", "source_refresh_frequency", "monthly_audit_day"];
const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : ["UTC", "Asia/Kolkata", "America/New_York", "Europe/London"];

function SettingsForm({ id }) {
  const q = useAsync(() => getSettings(id), [id]);
  const [v, setV] = useState({});
  useEffect(() => { if (q.data) setV(Object.fromEntries(FIELDS.map((k) => [k, q.data[k] ?? ""]))); }, [q.data]);
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }));
  const save = useAction(async () => {
    const body = {};
    FIELDS.forEach((k) => {
      let x = v[k];
      if (x === "" || x == null) return;
      if (k === "briefing_time") x = String(x).slice(0, 5);
      if (k === "monthly_audit_day" && typeof q.data?.[k] !== "string" && !isNaN(Number(x))) x = Number(x);
      body[k] = x;
    });
    const r = await updateSettings(id, body);
    q.setData(r);
    return r;
  });

  const lower = typeof v.briefing_day === "string" && v.briefing_day && v.briefing_day === v.briefing_day.toLowerCase();
  const days = DAYS.map((d) => (lower ? d.toLowerCase() : d));
  if (v.briefing_day && !days.includes(v.briefing_day)) days.unshift(v.briefing_day);
  const numericDay = typeof q.data?.monthly_audit_day !== "string";

  return (
    <Card aria-labelledby="sched">
      <h2 id="sched" className="mb-4 text-xl">Schedule</h2>
      {q.loading && !q.data && <Loading />}
      <ErrorNote error={q.error} onRetry={q.reload} />
      {q.data && (
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
          <Field label="Briefing day"><select className="input" value={v.briefing_day ?? ""} onChange={set("briefing_day")}><option value="" disabled>Choose a day</option>{days.map((d) => <option key={d}>{d}</option>)}</select></Field>
          <Field label="Briefing time"><input type="time" className="input" value={String(v.briefing_time ?? "").slice(0, 5)} onChange={set("briefing_time")} /></Field>
          <Field label="Timezone"><input className="input" list="tz" value={v.timezone ?? ""} onChange={set("timezone")} /><datalist id="tz">{zones.map((z) => <option key={z} value={z} />)}</datalist></Field>
          <Field label="Monitoring frequency"><input className="input" list="freq" value={v.monitoring_frequency ?? ""} onChange={set("monitoring_frequency")} /></Field>
          <Field label="Source refresh frequency"><input className="input" list="freq" value={v.source_refresh_frequency ?? ""} onChange={set("source_refresh_frequency")} /><datalist id="freq"><option value="daily" /><option value="weekly" /><option value="monthly" /></datalist></Field>
          <Field label="Monthly audit day" hint={numericDay ? "Day of the month" : undefined}><input type={numericDay ? "number" : "text"} min="1" max="31" className="input" value={v.monthly_audit_day ?? ""} onChange={set("monthly_audit_day")} /></Field>
          <div className="sm:col-span-2"><ErrorNote error={save.error} /></div>
          <div className="flex items-center gap-3 sm:col-span-2"><Button type="submit" busy={save.busy}>Save schedule</Button>{save.result && !save.busy && <span role="status" className="text-sm text-moss">Saved</span>}</div>
        </form>
      )}
    </Card>
  );
}

function AuditResult({ r }) {
  const blocks = [
    ["Dead or failing sources", r.dead_or_failing_sources], ["Duplicate sources", r.duplicate_sources], ["Inactive sources", r.inactive_sources],
    ["Declining relevance", r.declining_relevance_notes], ["Recommendations", r.recommendations], ["Applied actions", r.applied_actions],
  ];
  return (
    <div className="mt-5 space-y-4 rounded-md border border-line bg-paper p-4" role="status">
      <p className="text-xs text-mute">Audited {fmtDate(r.audited_at)}</p>
      {r.audit_summary && <p className="text-sm leading-relaxed">{looseText(r.audit_summary)}</p>}
      {blocks.map(([t, items]) => {
        const list = asItems(items);
        return (
          <div key={t}>
            <h3 className="mb-1 text-base">{t} <span className="tnum text-sm text-mute">({list.length})</span></h3>
            {list.length ? <List items={list} tone="text-mute" /> : <p className="text-sm text-mute">Nothing to report.</p>}
          </div>
        );
      })}
    </div>
  );
}

export default function Settings({ company, go }) {
  const id = company.id;
  const runs = useAsync(() => listRuns(id, 50), [id]);
  const [apply, setApply] = useState(false);
  const manual = useAction(async () => { const r = await runManualCycle(id); runs.reload(); return r; });
  const audit = useAction(async () => { const r = await runMonthlyAudit(id, apply); runs.reload(); return r; });
  const cs = manual.result?.crawl_summary;

  return (
    <>
      <PageHeader kicker={company.name} title="Settings and runs" />
      <div className="space-y-6">
        <SettingsForm id={id} />
        <div className="grid gap-6 lg:grid-cols-2">
          <Card aria-labelledby="weekly">
            <h2 id="weekly" className="mb-1 text-xl">Weekly cycle</h2>
            <p className="mb-4 text-sm text-mute">Crawl approved sources, rank signals and write a fresh brief.</p>
            <Button busy={manual.busy} onClick={manual.run}>{manual.busy ? "Running the cycle…" : "Run full weekly cycle now"}</Button>
            <div className="mt-3"><ErrorNote error={manual.error} /></div>
            {manual.result && (
              <div className="mt-4 space-y-3" role="status">
                {cs && typeof cs === "object" && (
                  <div className="grid grid-cols-3 gap-3">
                    {["sources_checked", "sources_failed", "signals_processed"].filter((k) => cs[k] != null).map((k) => <Stat key={k} label={k.replace(/_/g, " ")} value={cs[k]} />)}
                  </div>
                )}
                <Button variant="ghost" onClick={() => go("brief")}>View the new brief</Button>
              </div>
            )}
          </Card>
          <Card aria-labelledby="monthly">
            <h2 id="monthly" className="mb-1 text-xl">Monthly signal stack audit</h2>
            <p className="mb-2 text-sm text-mute">Find dead sources, duplicates and fading relevance.</p>
            <Toggle checked={apply} onChange={setApply} label="Apply recommendations" hint="Off: report only. On: the backend acts on its own recommendations." />
            <div className="mt-2"><Button busy={audit.busy} onClick={audit.run}>{audit.busy ? "Auditing…" : "Run monthly audit"}</Button></div>
            <div className="mt-3"><ErrorNote error={audit.error} /></div>
            {audit.result && <AuditResult r={audit.result} />}
          </Card>
        </div>

        <Card aria-labelledby="history">
          <h2 id="history" className="mb-4 text-xl">Run history</h2>
          {runs.loading && !runs.data && <Loading />}
          <ErrorNote error={runs.error} onRetry={runs.reload} />
          {runs.data && (runs.data.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <thead className="text-xs text-mute"><tr><th className="pb-2 pr-4 font-medium">When</th><th className="pb-2 pr-4 font-medium">Run</th><th className="pb-2 pr-4 font-medium">Status</th><th className="pb-2 font-medium">Details</th></tr></thead>
                <tbody>
                  {runs.data.map((r, i) => {
                    const status = String(r.status ?? "").toLowerCase();
                    const failed = ["failed", "error"].includes(status);
                    const details = looseText(r.details ?? r.error ?? r.message ?? "");
                    return (
                      <tr key={r.id ?? i} className={`border-t border-line align-top ${failed ? "bg-clay/5" : ""}`}>
                        <td className="tnum py-3 pr-4 whitespace-nowrap">{fmtDate(r.started_at ?? r.created_at ?? r.run_at)}</td>
                        <td className="py-3 pr-4">{String(r.run_type ?? r.job_type ?? r.job_name ?? r.kind ?? r.type ?? "run").replace(/_/g, " ")}{r.trigger ? <span className="text-mute"> · {r.trigger}</span> : null}</td>
                        <td className="py-3 pr-4"><Badge value={status || "unknown"} /></td>
                        <td className="py-3 text-mute">
                          {details.length > 140 ? <details><summary className="min-h-11 cursor-pointer py-2">{details.slice(0, 120)}…</summary><p className="whitespace-pre-wrap break-words">{details}</p></details> : details || "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <Empty title="No runs yet" hint="Scheduled and manual runs will be listed here." />)}
        </Card>
      </div>
    </>
  );
}
