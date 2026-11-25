import { useEffect, useState } from "react";
import { editAnswer, getCompany, getInterviewNext, startInterview, submitAnswer } from "../api/client";
import { useAction, useAsync } from "../lib/hooks";
import { aText, qText } from "../lib/format";
import { Badge, Button, Card, ErrorNote, Loading, PageHeader, Toggle } from "../components/ui";

const isFollowup = (m) => !!(m?.is_followup || m?.followup || m?.kind === "followup" || m?.type === "followup");
const wasSkipped = (m) => !!(m?.skipped ?? m?.is_skipped);

function HistoryItem({ m, onSave, busy }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(aText(m));
  const save = async (payload) => { const ok = await onSave({ message_id: m.id, ...payload }); if (ok) setEditing(false); };
  return (
    <li className="py-4">
      <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
        {qText(m)} {isFollowup(m) && <Badge value="follow-up" tone="ochre" />}
      </p>
      {editing ? (
        <div className="mt-2 space-y-3">
          <label className="block"><span className="sr-only">Edit answer</span><textarea className="input" value={text} onChange={(e) => setText(e.target.value)} /></label>
          <div className="flex flex-wrap gap-2">
            <Button busy={busy} disabled={!text.trim()} onClick={() => save({ new_answer_text: text.trim() })}>Save answer</Button>
            <Button variant="ghost" busy={busy} onClick={() => save({ skip: true })}>Mark as skipped</Button>
            <Button variant="ghost" onClick={() => { setEditing(false); setText(aText(m)); }}>Cancel</Button>
          </div>
        </div>
      ) : (
        <div className="mt-1.5 flex items-start justify-between gap-3">
          <p className={`whitespace-pre-wrap text-sm ${wasSkipped(m) ? "italic text-mute" : "text-ink"}`}>{wasSkipped(m) ? "Skipped as confidential." : aText(m)}</p>
          <Button variant="ghost" onClick={() => { setText(aText(m)); setEditing(true); }}>Edit</Button>
        </div>
      )}
    </li>
  );
}

export default function Interview({ company }) {
  const id = company.id;
  const next = useAsync(() => getInterviewNext(id), [id]);
  const comp = useAsync(() => getCompany(id), [id]);
  const [iv, setIv] = useState(null);
  const [ctx, setCtx] = useState(null);
  const [answer, setAnswer] = useState("");
  const [followup, setFollowup] = useState(true);

  useEffect(() => { if (next.data) setIv(next.data); }, [next.data]);
  useEffect(() => { if (comp.data && ctx === null) setCtx(comp.data.business_context || ""); }, [comp.data, ctx]);

  const start = useAction(async () => {
    const r = await startInterview(id);
    const st = r.next_state || {};
    setIv({ ...st, messages: st.messages?.length ? st.messages : r.messages || [] });
    return r;
  });
  const submit = useAction(async (payload) => {
    const r = await submitAnswer(id, payload);
    setIv(r);
    if (r.business_context != null) setCtx(r.business_context);
    setAnswer("");
    return r;
  });
  const edit = useAction(async (payload) => {
    const r = await editAnswer(id, payload);
    setIv((s) => ({ ...s, messages: r.messages }));
    if (r.business_context != null) setCtx(r.business_context);
    return r;
  });

  const q = iv?.current_question;
  const p = iv?.progress || { primary_completed: 0, primary_total: 10 };
  const history = (iv?.messages || []).filter((m) => m.id !== q?.id && (aText(m) || wasSkipped(m)));
  const notStarted = !iv ? !!next.error : !iv.completed && !q && (iv.messages || []).length === 0;
  const done = p.primary_total ? Math.min(100, (p.primary_completed / p.primary_total) * 100) : 0;

  return (
    <>
      <PageHeader kicker={company.name} title="Founder interview" />
      {next.loading && !iv && <Loading />}
      {notStarted && (
        <Card>
          <h2 className="mb-1 text-xl">Start the interview</h2>
          <p className="mb-4 max-w-xl text-sm text-mute">Ten questions, one at a time, with follow-ups where an answer needs more detail. Skip anything confidential.</p>
          {next.error && <p className="mb-3 text-sm text-mute">{next.error.message}</p>}
          <ErrorNote error={start.error} />
          <div className="mt-2"><Button busy={start.busy} onClick={start.run}>Begin interview</Button></div>
        </Card>
      )}

      {iv && !notStarted && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="space-y-6">
            <Card aria-labelledby="progress">
              <div className="mb-2 flex items-baseline justify-between">
                <h2 id="progress" className="text-base">Progress</h2>
                <p className="tnum text-sm text-mute">{p.primary_completed} / {p.primary_total} primary questions</p>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-sand" role="progressbar" aria-valuemin={0} aria-valuemax={p.primary_total} aria-valuenow={p.primary_completed} aria-labelledby="progress">
                <div className="h-full rounded-full bg-olive transition-[width] duration-500" style={{ width: `${done}%` }} />
              </div>
            </Card>

            {iv.completed || !q ? (
              <Card><h2 className="text-xl">Interview complete</h2><p className="mt-1 text-sm text-mute">Your answers now shape the business context. Edit any answer below and it updates.</p></Card>
            ) : (
              <Card aria-labelledby="question">
                <p className="mb-2 flex items-center gap-2 text-sm text-mute">
                  {isFollowup(q) ? <Badge value="follow-up" tone="ochre" /> : `Question ${Math.min(p.primary_completed + 1, p.primary_total)} of ${p.primary_total}`}
                </p>
                <h2 id="question" className="mb-4 text-2xl leading-snug">{qText(q)}</h2>
                <form onSubmit={(e) => { e.preventDefault(); submit.run({ message_id: q.id, answer_text: answer.trim(), allow_followup: followup }); }} className="space-y-3">
                  <label className="block"><span className="sr-only">Your answer</span><textarea className="input min-h-36" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Answer in your own words" /></label>
                  <Toggle checked={followup} onChange={setFollowup} label="Allow a follow-up question" />
                  <ErrorNote error={submit.error} />
                  <div className="flex flex-wrap gap-2">
                    <Button type="submit" busy={submit.busy} disabled={!answer.trim()}>Submit answer</Button>
                    <Button variant="ghost" disabled={submit.busy} onClick={() => submit.run({ message_id: q.id, skip: true })}>Skip confidential question</Button>
                  </div>
                </form>
              </Card>
            )}

            {history.length > 0 && (
              <Card aria-labelledby="answers">
                <h2 id="answers" className="mb-1 text-xl">Previous answers</h2>
                <ErrorNote error={edit.error} />
                <ul className="divide-y divide-line">
                  {history.map((m) => <HistoryItem key={m.id} m={m} busy={edit.busy} onSave={edit.run} />)}
                </ul>
              </Card>
            )}
          </div>

          <aside className="lg:sticky lg:top-28 lg:self-start" aria-labelledby="ctx-live">
            <Card>
              <h2 id="ctx-live" className="mb-1 text-lg">Business context, live</h2>
              <p className="mb-3 text-xs text-mute">Rewritten after each answer.</p>
              <div aria-live="polite" className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed">
                {ctx ? ctx : <span className="text-mute">Nothing yet. Answer the first question to start building it.</span>}
              </div>
            </Card>
          </aside>
        </div>
      )}
    </>
  );
}
