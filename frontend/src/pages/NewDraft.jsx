import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Button, ErrorNote, PageHeader, navigate, useApp } from "../ui.jsx";

export default function NewDraft() {
  const { system, toast } = useApp();
  const types = system?.content_types || ["Social post"];
  const [form, setForm] = useState({ title: "", content_type: "Social post", goal: "", body: "" });
  const [samples, setSamples] = useState([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    api("/drafts/samples").then((d) => setSamples(d.samples)).catch(() => {});
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const d = await api("/upload", { method: "POST", form: fd });
      setForm((f) => ({ ...f, body: d.text, title: f.title || file.name.replace(/\.[^.]+$/, "") }));
      toast(d.truncated ? `Imported ${d.filename} (first 12,000 characters)` : `Imported ${d.filename}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const d = await api("/drafts", { method: "POST", body: form });
      navigate(`/drafts/${d.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="New draft"
        lead="Paste your copy or upload a file. Tell Proofmark the goal so suggested fixes keep it."
      />
      {samples.length ? (
        <div className="samples">
          <p className="small muted">No draft handy? Load an example:</p>
          {samples.map((s) => (
            <button key={s.title} className="chip" onClick={() => setForm({ ...s })}>
              {s.title}
            </button>
          ))}
        </div>
      ) : null}
      <form className="form-grid" onSubmit={submit}>
        <label>
          Title
          <input value={form.title} onChange={set("title")} maxLength={120} required placeholder="Launch post for Instagram" />
        </label>
        <label>
          Content type
          <select value={form.content_type} onChange={set("content_type")}>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="span-2">
          Goal of this piece
          <input value={form.goal} onChange={set("goal")} maxLength={200} placeholder="Drive pre-orders" />
          <span className="hint">Suggested fixes are written to keep this goal.</span>
        </label>
        <label className="span-2">
          Draft text
          <textarea value={form.body} onChange={set("body")} rows={10} required maxLength={12000}
            placeholder="Paste the copy you want to publish…" />
          <span className="hint">{form.body.length.toLocaleString()} / 12,000 characters</span>
        </label>
        <div className="span-2 form-actions">
          <input ref={fileRef} type="file" accept=".txt,.md,.docx,.pdf" hidden onChange={(e) => upload(e.target.files[0])} />
          <Button type="button" onClick={() => fileRef.current?.click()} busy={uploading}>
            Upload .docx, .pdf, .md or .txt
          </Button>
          <Button variant="primary" type="submit" busy={busy}>
            {busy ? "Scanning" : "Create and scan"}
          </Button>
        </div>
        {busy ? (
          <p className="hint span-2" role="status">
            Checking rules and claims{system?.ai?.enabled ? ", then asking the AI about tone and messaging" : ""}.
            This usually takes a few seconds{system?.ai?.enabled ? " and can take up to 30 when the AI is busy" : ""}.
          </p>
        ) : null}
        <ErrorNote error={error} />
      </form>
    </>
  );
}
