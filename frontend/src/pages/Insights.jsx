import { api } from "../api.js";
import { Empty, ErrorNote, Link, Loading, PageHeader, useAsync } from "../ui.jsx";

function Bars({ items, label, value = (i) => i.n, note }) {
  const max = Math.max(1, ...items.map(value));
  if (!items.length) return <p className="muted">No data yet.</p>;
  return (
    <ul className="bars">
      {items.map((i, k) => (
        <li key={k}>
          <span className="bar-label">{label(i)}</span>
          <span className="bar-track"><span className="bar" style={{ width: `${(value(i) / max) * 100}%` }} /></span>
          <span className="bar-n">{value(i)}</span>
          {note ? <span className="bar-note">{note(i)}</span> : null}
        </li>
      ))}
    </ul>
  );
}

export default function Insights() {
  const { data, loading, error } = useAsync(() => api("/insights"), []);
  if (loading) return <Loading />;
  if (error) return <ErrorNote error={error} />;
  const t = data.totals;
  return (
    <>
      <PageHeader title="Insights" lead="Where content goes off-brand, and which rules may be the real problem." />
      <dl className="stats">
        <div><dt>Drafts scanned</dt><dd>{t.scanned}</dd></div>
        <div><dt>Approved</dt><dd>{t.approved}</dd></div>
        <div><dt>Issues caught on first scan</dt><dd>{t.issues_at_first_scan}</dd></div>
        <div><dt>Average per draft at first scan</dt><dd>{t.avg_issues_first_scan}</dd></div>
      </dl>
      <div className="grid-2">
        <section className="card">
          <h2>Rules people keep overriding</h2>
          <p className="muted small">A rule overridden often, especially as “Rule unclear”, probably needs clearer wording.</p>
          {data.most_overridden.length === 0 ? <p className="muted">No overrides yet.</p> : (
            <ul className="plain stack">
              {data.most_overridden.map((o) => (
                <li key={o.code} className={o.likely_unclear ? "flag" : ""}>
                  <span className="strong">{o.code}</span> overridden {o.n} time{o.n > 1 ? "s" : ""}
                  <span className="muted small block">{o.text}</span>
                  <span className="small block">Unclear {o.unclear}, false alarm {o.false_alarm}, exception {o.exception}</span>
                  {o.likely_unclear ? <span className="unclear-note">Likely unclear guideline. <Link to="/rulebook">Reword it in the rulebook</Link>.</span> : null}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card">
          <h2>Most broken rules</h2>
          <Bars items={data.most_broken} label={(i) => i.code} note={(i) => i.text} />
        </section>
        <section className="card">
          <h2>Issues by category</h2>
          <Bars items={data.by_category} label={(i) => i.category} />
        </section>
        <section className="card">
          <h2>Issues at first scan, by team</h2>
          <Bars items={data.by_team} label={(i) => i.team} />
        </section>
        <section className="card">
          <h2>Claim receipts</h2>
          <Bars items={data.claims} label={(i) => i.state} />
        </section>
        <section className="card">
          <h2>Guidelines marked unclear</h2>
          {data.ambiguous_rules.length === 0 ? <p className="muted">None.</p> : (
            <ul className="plain stack">
              {data.ambiguous_rules.map((r) => (
                <li key={r.code}><span className="strong">{r.code}</span> <span className="muted small">({r.status})</span> {r.text}
                  <span className="muted small block">{r.ambiguity_reason}</span></li>
              ))}
            </ul>
          )}
        </section>
      </div>
      {t.scanned === 0 ? <Empty title="No scans yet">Insights appear after the first drafts are scanned.</Empty> : null}
    </>
  );
}
