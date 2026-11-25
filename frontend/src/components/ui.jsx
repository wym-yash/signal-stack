import { ApiError } from "../api/client";
import { pct, fmtScore } from "../lib/format";

export function Spinner({ className = "" }) {
  return (
    <svg className={`h-4 w-4 animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Button({ variant = "primary", busy = false, className = "", children, disabled, ...rest }) {
  return (
    <button type="button" className={`btn btn-${variant} ${className}`} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy && <Spinner />}
      {children}
    </button>
  );
}

const TONES = {
  moss: "border-moss/30 bg-moss/10 text-moss",
  ochre: "border-ochre/30 bg-ochre/10 text-ochre",
  clay: "border-clay/30 bg-clay/10 text-clay",
  stone: "border-line bg-sand text-stone",
};
const TONE_OF = {
  verified: "moss", partially_verified: "ochre", unverified: "stone",
  opportunity: "moss", threat: "clay", neutral: "stone",
  approved: "moss", pending: "ochre", inactive: "stone", removed: "clay",
  success: "moss", succeeded: "moss", completed: "moss", failed: "clay", error: "clay",
};

export function Badge({ value, tone, children }) {
  const key = String(value ?? "").toLowerCase();
  const t = tone || TONE_OF[key] || "stone";
  const label = children ?? String(value ?? "unknown").replace(/_/g, " ");
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[t]}`}>
      {label}
    </span>
  );
}

export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-mute">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-start gap-3 py-1.5">
      <input type="checkbox" className="mt-1 h-4 w-4 accent-olive" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        {hint && <span className="block text-xs text-mute">{hint}</span>}
      </span>
    </label>
  );
}

export function PageHeader({ kicker, title, children }) {
  const words = title.split(" ");
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker && <p className="mb-2 text-sm text-mute">{kicker}</p>}
        <h1 className="font-display text-3xl leading-tight text-ink sm:text-4xl">
          {words.map((w, i) => (
            <span key={i}>
              <span className="word" style={{ "--i": i }}>{w}</span>{" "}
            </span>
          ))}
        </h1>
      </div>
      {children}
    </header>
  );
}

export function Card({ className = "", children, as: Tag = "section", ...rest }) {
  return <Tag className={`card p-5 ${className}`} {...rest}>{children}</Tag>;
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-mute" role="status">
      <Spinner /> {label}
    </div>
  );
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  const msg = error instanceof ApiError || error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-clay/30 bg-clay/10 px-4 py-3 text-sm text-clay">
      <span>{msg}</span>
      {onRetry && <Button variant="ghost" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Empty({ title, hint, action }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-paper px-6 py-10 text-center">
      <p className="font-display text-lg text-ink">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-md text-sm text-mute">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Stat({ label, value }) {
  return (
    <div className="rounded-md border border-line bg-paper px-4 py-3">
      <p className="tnum font-display text-2xl text-ink">{value}</p>
      <p className="text-xs text-mute">{label}</p>
    </div>
  );
}

export function ScoreBar({ label, value }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-mute">{label}</span>
        <span className="tnum font-medium text-ink">{fmtScore(value)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-sand" role="presentation">
        <div className="h-full rounded-full bg-olive" style={{ width: `${pct(value)}%` }} />
      </div>
    </div>
  );
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div role="group" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-lg border border-line bg-sand p-1">
      {options.map((o) => {
        const v = typeof o === "string" ? o : o.value;
        const l = typeof o === "string" ? o : o.label;
        const on = v === value;
        return (
          <button
            key={v}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(v)}
            className={`min-h-11 rounded-md px-3.5 text-sm font-medium transition duration-150 active:scale-[0.98] ${on ? "bg-card text-ink shadow-sm" : "text-mute hover:text-ink"}`}
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}

export function Check() {
  return (
    <svg viewBox="0 0 20 20" className="h-4 w-4 shrink-0" fill="none" aria-hidden="true">
      <path d="m4.5 10.5 3.5 3.5 7.5-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function List({ items, tone = "text-ink" }) {
  if (!items?.length) return null;
  return (
    <ul className={`space-y-1.5 text-sm ${tone}`}>
      {items.map((t, i) => (
        <li key={i} className="flex gap-2"><span aria-hidden="true">·</span><span>{t}</span></li>
      ))}
    </ul>
  );
}
