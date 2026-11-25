import { useEffect, useRef, useState } from "react";
import { createCompany, getCompany, researchCompany } from "../api/client";
import { useAction, useAsync } from "../lib/hooks";
import { asItems, countOf } from "../lib/format";
import { Button, Card, ErrorNote, Field, List, PageHeader, Stat } from "../components/ui";
import Facts from "../components/Facts";

const withScheme = (u) => (/^https?:\/\//i.test(u) ? u : `https://${u}`);

export default function CompanySetup({ company, focusToken, onCreated, onChanged }) {
  const [form, setForm] = useState({ name: "", website: "", industry: "", business_context: "" });
  const nameRef = useRef(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => { if (focusToken > 0) nameRef.current?.focus(); }, [focusToken]);

  const create = useAction(async () => {
    const body = { name: form.name.trim(), website: withScheme(form.website.trim()) };
    if (form.industry.trim()) body.industry = form.industry.trim();
    if (form.business_context.trim()) body.business_context = form.business_context.trim();
    const c = await createCompany(body);
    setForm({ name: "", website: "", industry: "", business_context: "" });
    onCreated(c);
    return c;
  });

  const id = company?.id;
  const detail = useAsync(() => getCompany(id), [id], !!id);
  const research = useAction(async () => {
    const r = await researchCompany(id);
    await detail.reload();
    onChanged?.();
    return r;
  });
  const meta = research.result?.crawl_metadata;
  const fetchErrors = asItems(meta?.fetch_errors);

  return (
    <>
      <PageHeader kicker="Step one" title="Company setup" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card aria-labelledby="new-company">
          <h2 id="new-company" className="mb-4 text-xl">New company</h2>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.run(); }}>
            <Field label="Company name"><input ref={nameRef} required className="input" value={form.name} onChange={set("name")} /></Field>
            <Field label="Website" hint="The crawler starts here."><input required className="input" placeholder="example.com" value={form.website} onChange={set("website")} /></Field>
            <Field label="Industry (optional)"><input className="input" value={form.industry} onChange={set("industry")} /></Field>
            <Field label="Business context (optional)" hint="What you already know. The interview will refine it."><textarea className="input" value={form.business_context} onChange={set("business_context")} /></Field>
            <ErrorNote error={create.error} />
            <Button type="submit" busy={create.busy}>Create company</Button>
          </form>
        </Card>

        <Card aria-labelledby="research">
          <h2 id="research" className="mb-1 text-xl">Initial research</h2>
          {company ? (
            <>
              <p className="mb-4 text-sm text-mute">Crawl {company.name}'s website and draft the intelligence profile.</p>
              <Button onClick={research.run} busy={research.busy}>{research.busy ? "Crawling the site…" : "Run initial research"}</Button>
              {research.busy && <p className="mt-3 text-sm text-mute" role="status">This can take a minute or two.</p>}
              <div className="mt-4"><ErrorNote error={research.error} /></div>
              {meta && (
                <div className="mt-5">
                  <div className="grid grid-cols-3 gap-3">
                    <Stat label="Pages visited" value={countOf(meta.pages_visited)} />
                    <Stat label="Fetch errors" value={countOf(meta.fetch_errors)} />
                    <Stat label="Characters extracted" value={(meta.extracted_chars ?? 0).toLocaleString()} />
                  </div>
                  {fetchErrors.length > 0 && (
                    <details className="mt-3 text-sm">
                      <summary className="min-h-11 cursor-pointer py-2 text-clay">Show fetch errors</summary>
                      <List items={fetchErrors} tone="text-mute" />
                    </details>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-mute">Create a company first, then research starts from its website.</p>
          )}
        </Card>
      </div>

      {company && (
        <div className="mt-10">
          <h2 className="mb-1 text-2xl">{company.name}: what we know</h2>
          {detail.data?.profile_summary && <p className="mb-5 max-w-3xl text-[15px] leading-relaxed text-mute">{detail.data.profile_summary}</p>}
          <ErrorNote error={detail.error} onRetry={detail.reload} />
          <Facts verified={detail.data?.verified_facts} assumptions={detail.data?.assumptions} />
        </div>
      )}
    </>
  );
}
