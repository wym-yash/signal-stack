import { Check } from "./ui";

/** Verified facts and assumptions, deliberately styled apart. */
export default function Facts({ verified = [], assumptions = [] }) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <section className="card border-l-4 border-l-moss p-5" aria-labelledby="facts-verified">
        <h2 id="facts-verified" className="mb-1 flex items-center gap-2 text-lg text-moss"><Check /> Verified facts</h2>
        <p className="mb-4 text-sm text-mute">Found on the company's own pages.</p>
        {verified.length ? (
          <ul className="space-y-2.5 text-sm">
            {verified.map((f, i) => <li key={i} className="flex gap-2"><span className="mt-0.5 text-moss"><Check /></span><span>{f}</span></li>)}
          </ul>
        ) : <p className="text-sm text-mute">None yet. Run initial research to collect them.</p>}
      </section>
      <section className="rounded-lg border border-dashed border-ochre/50 bg-sand/60 p-5" aria-labelledby="facts-assumed">
        <h2 id="facts-assumed" className="mb-1 text-lg text-ochre">Assumptions</h2>
        <p className="mb-4 text-sm text-mute">Inferred, not confirmed. Correct them in the interview.</p>
        {assumptions.length ? (
          <ul className="space-y-2.5 text-sm">
            {assumptions.map((f, i) => <li key={i} className="flex gap-2"><span aria-hidden="true" className="text-ochre">?</span><span>{f}</span></li>)}
          </ul>
        ) : <p className="text-sm text-mute">No open assumptions.</p>}
      </section>
    </div>
  );
}
