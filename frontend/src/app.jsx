import { useEffect, useState } from "react";
import { getHealth, listCompanies } from "./api/client";
import { clearFounderSession, getFounderSession, setFounderSession } from "./lib/auth";
import { useAsync } from "./lib/hooks";
import { Button, Empty, ErrorNote, Loading } from "./components/ui";
import CompanySetup from "./pages/CompanySetup";
import Profile from "./pages/Profile";
import Interview from "./pages/Interview";
import SignalStack from "./pages/SignalStack";
import SourceManager from "./pages/SourceManager";
import Feed from "./pages/Feed";
import Brief from "./pages/Brief";
import Settings from "./pages/Settings";

const VIEWS = [
  { id: "setup", label: "Company setup" },
  { id: "profile", label: "Intelligence profile" },
  { id: "interview", label: "Founder interview" },
  { id: "stack", label: "Signal stack" },
  { id: "sources", label: "Source manager" },
  { id: "feed", label: "Intelligence feed" },
  { id: "brief", label: "Monday brief" },
  { id: "settings", label: "Settings & runs" },
];

function Health() {
  const h = useAsync(getHealth, []);
  const ok = h.data && String(h.data.status).toLowerCase() === "ok";
  const providers = h.data?.available_free_llm_providers || [];
  return (
    <button
      type="button"
      onClick={h.reload}
      title={h.error ? h.error.message : `LLM providers: ${providers.join(", ") || "none"}`}
      className="inline-flex min-h-11 items-center gap-2 rounded-md px-2 text-sm text-mute transition duration-150 hover:bg-sand active:scale-[0.98]"
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${h.loading ? "bg-stone" : ok ? "bg-moss" : "bg-clay"}`} />
      {h.loading ? "Checking API" : ok ? `API online · ${providers.length} LLM provider${providers.length === 1 ? "" : "s"}` : "API offline"}
    </button>
  );
}

export default function App() {
  const [view, setView] = useState("setup");
  const [selected, setSelected] = useState(() => localStorage.getItem("signalstack.company") || "");
  const [focusToken, setFocusToken] = useState(0);
  const [session, setSession] = useState(() => getFounderSession());
  const [founderInput, setFounderInput] = useState(() => getFounderSession()?.founderId || "");
  const list = useAsync(listCompanies, [session?.founderId || ""]);
  const companies = list.data || [];
  const company = companies.find((c) => String(c.id) === String(selected)) || null;

  useEffect(() => {
    if (!list.data) return;
    if (!company && companies.length) setSelected(String(companies[0].id));
  }, [list.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (selected) localStorage.setItem("signalstack.company", selected); }, [selected]);
  useEffect(() => { if (list.data && !companies.length) setView("setup"); }, [list.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFounderSubmit = async (e) => {
    e.preventDefault();
    const cleanId = founderInput.trim();
    if (!cleanId) return;
    const next = setFounderSession({
      token: `${cleanId}-token`,
      founderId: cleanId,
      name: cleanId,
    });
    setSession(next);
    setSelected("");
    await list.reload();
  };

  const handleFounderSignOut = async () => {
    clearFounderSession();
    setSession(null);
    setFounderInput("");
    setSelected("");
    await list.reload();
  };

  const go = (v) => { setView(v); window.scrollTo({ top: 0 }); };
  const newCompany = () => { setView("setup"); setFocusToken((n) => n + 1); };
  const onCreated = async (c) => { await list.reload(); setSelected(String(c.id)); };
  const common = { company, go, onChanged: list.reload };

  let page = null;
  if (view === "setup") page = <CompanySetup key={company?.id ?? "none"} {...common} focusToken={focusToken} onCreated={onCreated} />;
  else if (!company) {
    page = list.loading && !list.data ? <Loading /> : (
      <Empty title="Choose a company" hint="Pick one from the selector above, or create your first company." action={<Button onClick={newCompany}>+ New company</Button>} />
    );
  } else {
    const P = { profile: Profile, interview: Interview, stack: SignalStack, sources: SourceManager, feed: Feed, brief: Brief, settings: Settings }[view];
    page = <P key={`${view}-${company.id}`} {...common} />;
  }

  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-5 py-3 sm:px-8">
          <p className="mr-2 font-display text-xl text-olive-deep">Signal Stack</p>
          <label className="flex items-center gap-2 text-sm">
            <span className="sr-only">Company</span>
            <select className="input w-56" value={company?.id ?? ""} onChange={(e) => setSelected(e.target.value)} disabled={!companies.length}>
              {!companies.length && <option value="">{list.loading ? "Loading…" : "No companies yet"}</option>}
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <Button variant="ghost" onClick={newCompany}>+ New company</Button>
          <form onSubmit={handleFounderSubmit} className="flex items-center gap-2 text-sm">
            <input
              type="text"
              value={founderInput}
              onChange={(e) => setFounderInput(e.target.value)}
              placeholder="Founder ID (e.g. founder-a)"
              aria-label="Founder ID"
              className="input w-44"
            />
            <Button type="submit" variant="ghost">{session ? "Switch founder" : "Sign in"}</Button>
            {session && (
              <Button type="button" variant="ghost" onClick={handleFounderSignOut}>
                Sign out ({session.founderId})
              </Button>
            )}
          </form>
          <div className="ml-auto"><Health /></div>
        </div>
        <nav aria-label="Sections" className="mx-auto max-w-6xl overflow-x-auto px-5 sm:px-8">
          <ul className="flex min-w-max gap-1">
            {VIEWS.map((v) => {
              const on = v.id === view;
              return (
                <li key={v.id}>
                  <button
                    type="button"
                    aria-current={on ? "page" : undefined}
                    onClick={() => go(v.id)}
                    className={`min-h-11 border-b-2 px-3 text-sm font-medium transition duration-150 hover:text-ink active:translate-y-px ${on ? "border-olive text-ink" : "border-transparent text-mute"}`}
                  >
                    {v.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
      <main id="main" className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        <div className="mb-6"><ErrorNote error={list.error} onRetry={list.reload} /></div>
        {page}
      </main>
      <footer className="mx-auto max-w-6xl px-5 pb-10 text-xs text-mute sm:px-8">Signal Stack · connected to the local FastAPI backend</footer>
    </>
  );
}
