import { useState } from "react";
import { api } from "../api.js";
import { Button, ErrorNote, Loading, PageHeader, useApp, useAsync } from "../ui.jsx";

const EMPTY = { statement: "", keywords: "", value: "", unit: "", comparison: "max", source: "", valid_until: "", confidential: false };

function AddFact({ onDone }) {
  const { toast } = useApp();
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const d = await api("/facts", { method: "POST", body: { ...f, keywords: f.keywords.split(",").map((k) => k.trim()).filter(Boolean) } });
      toast(`${d.code} added`);
      setF(EMPTY);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="card form-grid" onSubmit={save} aria-labelledby="addfact">
      <h2 id="addfact" className="span-2">Add an approved fact</h2>
      <label className="span-2">Fact, as it may be published
        <input value={f.statement} onChange={set("statement")} required maxLength={400} placeholder="Volta Buds Air weigh 4.5 g per bud." />
      </label>
      <label className="span-2">Keywords that signal a claim about it (comma separated)
        <input value={f.keywords} onChange={set("keywords")} required placeholder="weight, weighs, light" />
      </label>
      <label>Number (optional)<input value={f.value} onChange={set("value")} inputMode="decimal" placeholder="4.5" /></label>
      <label>Unit<input value={f.unit} onChange={set("unit")} placeholder="g, hour, percent, INR" /></label>
      <label>A claim passes when it is
        <select value={f.comparison} onChange={set("comparison")}>
          <option value="max">equal to or below this number</option>
          <option value="exact">exactly this number</option>
        </select>
      </label>
      <label>Valid until<input type="date" value={f.valid_until} onChange={set("valid_until")} /></label>
      <label className="span-2">Source<input value={f.source} onChange={set("source")} placeholder="Spec sheet v3" /></label>
      <label className="check span-2">
        <input type="checkbox" checked={f.confidential} onChange={set("confidential")} />
        <span>Confidential: never sent to AI, hidden from creators, and any mention in a draft is flagged.</span>
      </label>
      <ErrorNote error={error} />
      <div className="span-2"><Button variant="primary" type="submit" busy={busy}>Add fact</Button></div>
    </form>
  );
}

export default function Facts() {
  const { user, toast } = useApp();
  const owner = user.role === "owner";
  const { data, loading, error, reload } = useAsync(() => api("/facts"), []);
  const today = new Date().toISOString().slice(0, 10);
  const remove = async (fact) => {
    if (!window.confirm(`Remove ${fact.code}? Claims that relied on it will show as unbacked.`)) return;
    try {
      await api(`/facts/${fact.id}`, { method: "DELETE" });
      toast(`${fact.code} removed`);
      reload();
    } catch (e) {
      toast(e.message, "err");
    }
  };
  return (
    <>
      <PageHeader title="Approved facts" lead="Claim Receipts compare every number and absolute claim in a draft with these facts." />
      <ErrorNote error={error} />
      {loading ? <Loading /> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">Code</th><th scope="col">Fact</th><th scope="col">Checked as</th><th scope="col">Source</th><th scope="col">Valid until</th>{owner ? <th scope="col"><span className="sr-only">Actions</span></th> : null}</tr></thead>
            <tbody>
              {data.facts.map((f) => (
                <tr key={f.id} className={f.confidential ? "row-conf" : ""}>
                  <td className="strong">{f.code}</td>
                  <td>{f.statement}{f.confidential ? <span className="conf-tag">Confidential</span> : null}
                    <span className="muted small block">Keywords: {f.keywords.join(", ")}</span></td>
                  <td>{f.value !== null ? `${f.comparison === "max" ? "at most" : "exactly"} ${f.value} ${f.unit}` : <span className="muted">wording only</span>}</td>
                  <td>{f.source || <span className="muted">none</span>}</td>
                  <td>{f.valid_until ? <span className={f.valid_until < today ? "expired" : ""}>{f.valid_until}{f.valid_until < today ? " (expired)" : ""}</span> : <span className="muted">no expiry</span>}</td>
                  {owner ? <td><button className="link-btn" onClick={() => remove(f)}>Remove</button></td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {owner ? <AddFact onDone={reload} /> : null}
    </>
  );
}
