import { useState } from "react";
import { api } from "../api.js";
import { Button, ErrorNote, Loading, Method, PageHeader, Severity, useApp, useAsync } from "../ui.jsx";

const CATEGORY_LABEL = {
  terminology: "Terminology",
  claims: "Claims",
  legal: "Legal",
  tone: "Tone",
  messaging: "Messaging",
  accessibility: "Accessibility",
  visual: "Visual",
};

function Compiler({ onDone }) {
  const { toast } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const loadSample = async () => {
    const d = await api("/rules/sample-guide");
    setText(d.text);
  };
  const compile = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api("/rules/compile", { method: "POST", body: { text } });
      toast(`${d.count} rules proposed${d.ambiguous ? `, ${d.ambiguous} marked unclear` : ""} (${d.mode === "ai" ? "AI" : "offline"} compiler)`);
      setText("");
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card compiler" aria-labelledby="compiler-title">
      <h2 id="compiler-title">Compile guidelines into rules</h2>
      <p className="muted">
        Paste guideline text. Proofmark splits it into single rules, decides how each one is checked, and marks vague
        sentences as unclear. Nothing is used until you approve it.
      </p>
      <textarea rows={7} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a section of your brand guidelines…" />
      <ErrorNote error={error} />
      <div className="row">
        <Button variant="primary" onClick={compile} busy={busy} disabled={!text.trim()}>
          Compile
        </Button>
        <Button onClick={loadSample}>Load sample guideline update</Button>
      </div>
    </section>
  );
}

function RuleRow({ r, owner, reload }) {
  const { toast } = useApp();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(r.text);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const patch = async (body, key, msg) => {
    setBusy(key);
    setError(null);
    try {
      await api(`/rules/${r.id}`, { method: "PATCH", body });
      toast(msg);
      setEditing(false);
      reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <li className={`rule ${r.ambiguous ? "rule-unclear" : ""} ${r.status === "disabled" ? "rule-off" : ""}`}>
      <div className="rule-meta">
        <span className="strong">{r.code}</span>
        <Method method={r.method} />
        <Severity level={r.severity} />
        <span className="muted small">{r.source}</span>
      </div>
      {editing ? (
        <div className="stack">
          <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <Button variant="primary" busy={busy === "text"} onClick={() => patch({ text }, "text", `${r.code} reworded`)}>
              Save wording
            </Button>
            <Button onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <p className="rule-text">{r.text}</p>
      )}
      {r.ambiguous ? <p className="unclear-note">Unclear: {r.ambiguity_reason}</p> : null}
      <ErrorNote error={error} />
      {owner ? (
        <div className="row">
          {r.status === "proposed" ? (
            <>
              <Button variant="primary" busy={busy === "approve"} onClick={() => patch({ status: "approved" }, "approve", `${r.code} approved`)}>
                Approve
              </Button>
              <Button busy={busy === "reject"} onClick={() => patch({ status: "rejected" }, "reject", `${r.code} rejected`)}>
                Reject
              </Button>
            </>
          ) : r.status === "approved" ? (
            <Button busy={busy === "off"} onClick={() => patch({ status: "disabled" }, "off", `${r.code} turned off`)}>
              Turn off
            </Button>
          ) : (
            <Button busy={busy === "on"} onClick={() => patch({ status: "approved" }, "on", `${r.code} turned on`)}>
              Turn on
            </Button>
          )}
          {!editing ? <button className="link-btn" onClick={() => setEditing(true)}>Reword</button> : null}
        </div>
      ) : null}
    </li>
  );
}

export default function Rulebook() {
  const { user } = useApp();
  const owner = user.role === "owner";
  const { data, loading, error, reload } = useAsync(() => api("/rules"), []);
  const rules = data?.rules || [];
  const proposed = rules.filter((r) => r.status === "proposed");
  const active = rules.filter((r) => r.status === "approved" || r.status === "disabled");
  const groups = {};
  active.forEach((r) => (groups[r.category] = [...(groups[r.category] || []), r]));
  const counts = { exact: 0, ai: 0, human: 0 };
  active.filter((r) => r.status === "approved").forEach((r) => counts[r.method]++);

  return (
    <>
      <PageHeader
        title="Rulebook"
        lead={`${active.filter((r) => r.status === "approved").length} approved rules: ${counts.exact} checked by code, ${counts.ai} judged by AI, ${counts.human} confirmed by a reviewer.`}
      />
      <ErrorNote error={error} />
      {owner ? <Compiler onDone={reload} /> : null}
      {loading ? <Loading /> : null}
      {proposed.length ? (
        <section className="section">
          <h2>Waiting for approval ({proposed.length})</h2>
          <ul className="rules">
            {proposed.map((r) => <RuleRow key={r.id} r={r} owner={owner} reload={reload} />)}
          </ul>
        </section>
      ) : null}
      {Object.keys(CATEGORY_LABEL).filter((c) => groups[c]).map((c) => (
        <section className="section" key={c}>
          <h2>{CATEGORY_LABEL[c]}</h2>
          <ul className="rules">
            {groups[c].map((r) => <RuleRow key={r.id} r={r} owner={owner} reload={reload} />)}
          </ul>
        </section>
      ))}
    </>
  );
}
