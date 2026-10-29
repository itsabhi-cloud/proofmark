import { Fragment, useEffect, useMemo, useState } from "react";
import { api, timeAgo, ROLE_LABEL } from "../api.js";
import {
  Button, ClaimState, DiffView, Empty, ErrorNote, Link, Loading, Method, Modal, Severity, Status, useApp, useAsync,
} from "../ui.jsx";

function buildSegments(text, marks) {
  const spans = marks
    .filter((m) => m.start !== null && m.end !== null && m.end > m.start)
    .sort((a, b) => a.start - b.start || b.end - a.end);
  const out = [];
  let pos = 0;
  for (const m of spans) {
    if (m.start < pos) continue; // overlapping mark: its card still lists it
    if (m.start > pos) out.push({ text: text.slice(pos, m.start) });
    out.push({ text: text.slice(m.start, m.end), mark: m });
    pos = m.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos) });
  return out;
}

function ProofSheet({ text, findings, numbers, active, onPick }) {
  const segments = useMemo(() => buildSegments(text, findings), [text, findings]);
  return (
    <div className="sheet" aria-label="Draft with highlighted findings">
      {segments.map((s, i) =>
        s.mark ? (
          <mark
            key={i}
            className={`m-${s.mark.claim_state === "Supported" ? "ok" : s.mark.severity} ${s.mark.status !== "open" ? "m-done" : ""} ${active === s.mark.id ? "m-active" : ""}`}
            onClick={() => onPick(s.mark.id)}
            tabIndex={0}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(s.mark.id)}
            aria-label={`Finding ${numbers[s.mark.id] || ""}: ${s.mark.explanation}`}
          >
            {s.text}
            {numbers[s.mark.id] ? <sup className="mark-no">{numbers[s.mark.id]}</sup> : null}
          </mark>
        ) : (
          <Fragment key={i}>{s.text}</Fragment>
        )
      )}
    </div>
  );
}

function fixLabel(f) {
  if (f.suggestion === null || f.suggestion === undefined) return null;
  if (f.start === f.end) return { verb: "Add", text: f.suggestion.trim() };
  if (f.suggestion === "") return { verb: "Remove", text: f.quote };
  return { verb: "Replace with", text: f.suggestion };
}

function FindingCard({ f, n, active, onPick, choice, setChoice, canEdit, canDismiss, reasons, onDismissed }) {
  const [overriding, setOverriding] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const fix = fixLabel(f);
  const open = f.status === "open";

  const dismiss = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/findings/${f.id}/dismiss`, { method: "POST", body: { reason, note } });
      onDismissed();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <article
      id={`finding-${f.id}`}
      className={`card finding sevline-${f.severity} ${active ? "active" : ""} ${open ? "" : "decided"}`}
      onClick={() => onPick(f.id)}
    >
      <header className="finding-head">
        <span className="finding-no">{n}</span>
        <Severity level={f.severity} />
        <Method method={f.method} />
        <span className="muted small">{f.rule_code || (f.fact_code ? f.fact_code : "")}</span>
        {f.method === "ai" ? <span className="muted small">confidence {f.confidence}</span> : null}
      </header>
      {f.quote ? <p className="quote">“{f.quote}”</p> : <p className="quote muted">Whole draft</p>}
      <p className="explain">{f.explanation}</p>
      <p className="evidence">
        <span className="evidence-label">Evidence</span> {f.evidence}
      </p>
      {fix ? (
        <p className="fix">
          <span className="fix-verb">{fix.verb}</span> <span className="fix-text">“{fix.text}”</span>
        </p>
      ) : open && f.severity !== "info" ? (
        <p className="fix muted small">No safe word-for-word fix. Reword it yourself or use the full rewrite.</p>
      ) : null}

      {!open ? (
        <p className="decision small">
          {f.status === "accepted" && "Fix accepted"}
          {f.status === "rejected" && "Kept as written by the creator"}
          {f.status === "dismissed" && `Overridden: ${f.dismiss_reason}${f.dismiss_note ? `. “${f.dismiss_note}”` : ""}`}
          {f.decided_by_name ? ` by ${f.decided_by_name}` : ""}
        </p>
      ) : null}

      {open && canEdit && f.severity !== "info" ? (
        <div className="choice" role="group" aria-label="Your decision" onClick={(e) => e.stopPropagation()}>
          {fix ? (
            <button className={`chip ${choice === "accept" ? "chip-on" : ""}`} aria-pressed={choice === "accept"}
              onClick={() => setChoice(choice === "accept" ? null : "accept")}>
              Accept fix
            </button>
          ) : null}
          <button className={`chip ${choice === "reject" ? "chip-on" : ""}`} aria-pressed={choice === "reject"}
            onClick={() => setChoice(choice === "reject" ? null : "reject")}>
            Keep as written
          </button>
        </div>
      ) : null}

      {open && canDismiss && f.severity !== "info" ? (
        <div onClick={(e) => e.stopPropagation()}>
          {!overriding ? (
            <button className="link-btn" onClick={() => setOverriding(true)}>
              Override this finding
            </button>
          ) : (
            <div className="override">
              <fieldset>
                <legend>Why are you overriding it?</legend>
                {reasons.map((r) => (
                  <label key={r} className="radio">
                    <input type="radio" name={`reason-${f.id}`} checked={reason === r} onChange={() => setReason(r)} /> {r}
                  </label>
                ))}
              </fieldset>
              <label>
                Note (optional)
                <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
              </label>
              <ErrorNote error={error} />
              <div className="row">
                <Button variant="primary" onClick={dismiss} busy={busy} disabled={!reason}>
                  Override
                </Button>
                <Button onClick={() => setOverriding(false)}>Cancel</Button>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </article>
  );
}

// Turns the raw provider error into a sentence a user can act on.
function aiFallbackReason(err) {
  if (/429|Too Many/i.test(err)) return "The free Gemini plan hit its request limit";
  if (/503|overloaded|high demand/i.test(err)) return "Gemini was busy";
  if (/Timeout/i.test(err)) return "Gemini took too long to answer";
  return "The AI could not be reached";
}

function ScanStrip({ scan, version, onRescan, rescanning }) {
  if (!scan) return null;
  const s = scan.summary || {};
  const c = s.counts || {};
  const v = s.verifier;
  const aiFailed = s.mode !== "exact+ai" && s.ai?.enabled && s.ai_error;
  return (
    <div className="scanstrip" aria-label="Scan summary">
      <span className="scan-when">
        Scan of v{version}, {timeAgo(scan.created_at)}
      </span>
      <span className="scan-counts">
        <span className="tally tally-high">{c.high || 0} high</span>
        <span className="tally tally-med">{c.medium || 0} medium</span>
        <span className="tally tally-low">{c.low || 0} low</span>
      </span>
      <span>{s.rules_checked} rules checked</span>
      <span title="How findings were produced">
        {s.mode === "exact+ai"
          ? `Exact checks + AI (${s.ai?.model})`
          : aiFailed ? "Exact checks + word lists" : "Exact checks + word lists (AI off)"}
      </span>
      {v ? (
        <span className={`scan-verifier ${v.dropped_quote_not_found || v.needs_human ? "scan-verifier-caught" : ""}`}
          title="The verifier drops AI findings whose quoted words are not in the draft">
          <span aria-hidden="true">✓</span> Verifier kept {v.kept} of {v.ai_suggested} AI findings
          {v.dropped_quote_not_found ? `, dropped ${v.dropped_quote_not_found}` : ""}
          {v.needs_human ? `, ${v.needs_human} sent to a human` : ""}
        </span>
      ) : null}
      {s.masked_items ? <span>{s.masked_items} personal details masked before AI</span> : null}
      {aiFailed ? (
        <span className="warn">
          {aiFallbackReason(s.ai_error)}, so this scan used code checks and word lists only.
          {onRescan ? (
            <>
              {" "}
              <button className="link-btn" onClick={onRescan} disabled={rescanning}>
                {rescanning ? "Re-scanning…" : "Try the AI again"}
              </button>
            </>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}

function RewriteModal({ draftId, onClose, onUsed }) {
  const { toast, system } = useApp();
  const [state, setState] = useState({ loading: true });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api(`/drafts/${draftId}/rewrite`, { method: "POST" })
      .then((d) => setState({ loading: false, data: d }))
      .catch((e) => setState({ loading: false, error: e.message }));
  }, [draftId]);

  const use = async () => {
    setBusy(true);
    try {
      await api(`/drafts/${draftId}/versions`, {
        method: "POST",
        body: { body: state.data.text, note: state.data.mode === "ai" ? "Used AI rewrite" : "Applied all safe fixes" },
      });
      toast("New version saved and re-scanned");
      onUsed();
    } catch (e) {
      setState({ ...state, error: e.message });
      setBusy(false);
    }
  };

  const d = state.data;
  return (
    <Modal title={d?.mode === "offline" ? "Fix everything automatically" : "Rewrite with AI"} onClose={onClose} wide>
      {state.loading ? (
        <>
          <Loading label="Writing and re-scanning the proposal" />
          <p className="hint">This usually takes a few seconds, and can take up to a minute when the AI is busy.</p>
        </>
      ) : null}
      <ErrorNote error={state.error} />
      {d ? (
        <>
          <p className="muted">
            {d.mode === "ai"
              ? `The AI rewrote the draft to keep your goal, then Proofmark scanned the result again (${d.attempts} attempt${d.attempts > 1 ? "s" : ""}).`
              : `${system?.ai?.enabled ? "The AI could not answer just now" : "AI is off"}, so every safe suggested fix was applied word for word, then the result was scanned again.`}
          </p>
          <DiffView segments={d.diff} />
          <p className={d.goal_preserved ? "ok-note" : "warn"}>
            {d.goal_preserved ? "Goal kept." : "The goal may have changed."} {d.goal_reason}
          </p>
          {d.remaining.length ? (
            <div className="remaining">
              <p className="strong">Still needs you ({d.remaining.length})</p>
              <ul>
                {d.remaining.map((r, i) => (
                  <li key={i}>
                    <Severity level={r.severity} /> {r.quote ? `“${r.quote}”: ` : ""}
                    {r.explanation}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="ok-note">The re-scan found no high or medium issues.</p>
          )}
          <div className="row end">
            <Button onClick={onClose}>Discard</Button>
            <Button variant="primary" onClick={use} busy={busy}>
              Use this version
            </Button>
          </div>
        </>
      ) : null}
    </Modal>
  );
}

function History({ detail }) {
  const nums = detail.versions.map((v) => v.number);
  const [from, setFrom] = useState(nums.length > 1 ? nums[nums.length - 2] : nums[0]);
  const [to, setTo] = useState(nums[nums.length - 1]);
  const diff = useAsync(
    () => (from === to ? Promise.resolve({ segments: null }) : api(`/drafts/${detail.draft.id}/diff?from=${from}&to=${to}`)),
    [from, to, detail.current.id]
  );
  return (
    <div className="stack">
      {nums.length > 1 ? (
        <div className="card">
          <div className="row">
            <label className="inline">
              Compare v
              <select value={from} onChange={(e) => setFrom(Number(e.target.value))}>
                {nums.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label className="inline">
              with v
              <select value={to} onChange={(e) => setTo(Number(e.target.value))}>
                {nums.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
          {diff.data?.segments ? <DiffView segments={diff.data.segments} /> : <p className="muted small">Pick two different versions.</p>}
        </div>
      ) : null}
      <ol className="timeline">
        {detail.events.map((e) => (
          <li key={e.id}>
            <span className="strong">{e.user_name || "System"}</span> {e.action}
            {e.detail ? <span className="muted">: {e.detail}</span> : null}
            <span className="muted small block">{new Date(e.created_at).toLocaleString()}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Comments({ detail, canComment, reload }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/drafts/${detail.draft.id}/comments`, { method: "POST", body: { body: text } });
      setText("");
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack">
      {detail.comments.length === 0 ? <p className="muted">No comments yet.</p> : null}
      {detail.comments.map((c) => (
        <div key={c.id} className="comment">
          <p className="small">
            <span className="strong">{c.author}</span> <span className="muted">({ROLE_LABEL[c.author_role]}) on v{c.version_number}, {timeAgo(c.created_at)}</span>
          </p>
          <p>{c.body}</p>
        </div>
      ))}
      {canComment ? (
        <form onSubmit={add} className="stack">
          <label>
            Add a comment
            <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} required maxLength={1000} />
          </label>
          <ErrorNote error={error} />
          <Button type="submit" busy={busy}>Post comment</Button>
        </form>
      ) : null}
    </div>
  );
}

function ReviewPanel({ detail, reload }) {
  const { toast } = useApp();
  const [checks, setChecks] = useState({});
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const decide = async (decision) => {
    setBusy(decision);
    setError(null);
    try {
      await api(`/drafts/${detail.draft.id}/review`, { method: "POST", body: { decision, comment, checks } });
      toast(decision === "approve" ? "Approved and locked" : "Sent back to the creator");
      reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };
  const allChecked = detail.human_checks.every((h) => checks[h.code]);
  return (
    <section className="card review-panel" aria-labelledby="review-title">
      <h2 id="review-title">Your decision</h2>
      {detail.human_checks.length ? (
        <fieldset>
          <legend>Human-only checks</legend>
          {detail.human_checks.map((h) => (
            <label key={h.code} className="check">
              <input type="checkbox" checked={!!checks[h.code]} onChange={(e) => setChecks({ ...checks, [h.code]: e.target.checked })} />
              <span><span className="muted small">{h.code}</span> {h.text}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
      <label>
        Comment for the creator
        <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000}
          placeholder="Required when you request changes" />
      </label>
      <ErrorNote error={error} />
      <div className="row">
        <Button variant="primary" onClick={() => decide("approve")} busy={busy === "approve"} disabled={!allChecked}
          title={allChecked ? "" : "Tick the human checks first"}>
          Approve
        </Button>
        <Button onClick={() => decide("request_changes")} busy={busy === "request_changes"} disabled={!comment.trim()}>
          Request changes
        </Button>
      </div>
      {!allChecked ? <p className="hint">Tick each human check to enable Approve.</p> : null}
    </section>
  );
}

export default function Workspace({ id }) {
  const { system, toast } = useApp();
  const { data: detail, loading, error, reload } = useAsync(() => api(`/drafts/${id}`), [id]);
  const [tab, setTab] = useState("issues");
  const [active, setActive] = useState(null);
  const [choices, setChoices] = useState({});
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [rewriting, setRewriting] = useState(false);
  const [busy, setBusy] = useState(null);
  const [actionError, setActionError] = useState(null);

  useEffect(() => {
    setChoices({});
    setEditing(false);
  }, [detail?.current?.id, detail?.scan?.id]);

  if (loading && !detail) return <Loading label="Opening draft" />;
  if (error)
    return (
      <div className="stack">
        <ErrorNote error={error} />
        <p><Link to="/drafts">← Back to drafts</Link></p>
      </div>
    );

  const { draft, current, scan, findings, permissions: can } = detail;
  const issues = findings.filter((f) => f.severity !== "info");
  const claims = findings.filter((f) => f.claim_state);
  const numbers = {};
  issues.forEach((f, i) => (numbers[f.id] = i + 1));
  const accepted = Object.entries(choices).filter(([, v]) => v === "accept").map(([k]) => Number(k));
  const rejected = Object.entries(choices).filter(([, v]) => v === "reject").map(([k]) => Number(k));
  const openHigh = issues.filter((f) => f.status === "open" && f.severity === "high").length;

  const pick = (fid) => {
    setActive(fid);
    const f = findings.find((x) => x.id === fid);
    setTab(f && f.severity === "info" ? "claims" : "issues");
    setTimeout(() => document.getElementById(`finding-${fid}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 30);
  };

  const run = async (key, fn, okText) => {
    setBusy(key);
    setActionError(null);
    try {
      await fn();
      if (okText) toast(okText);
      reload();
    } catch (e) {
      setActionError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const applyChoices = () =>
    run("apply", () => api(`/drafts/${id}/apply-fixes`, { method: "POST", body: { accept: accepted, reject: rejected } }),
      accepted.length ? `Applied ${accepted.length} fix${accepted.length > 1 ? "es" : ""} and re-scanned` : "Decisions saved");

  const tabs = [
    ["issues", `Issues (${issues.filter((f) => f.status === "open").length})`],
    ["claims", `Claim receipts (${claims.length})`],
    ["checks", `Human checks (${detail.human_checks.length})`],
    ["history", "History"],
    ["comments", `Comments (${detail.comments.length})`],
  ];

  return (
    <div className="workspace">
      <header className="ws-head">
        <div>
          <p className="muted small">
            {draft.content_type} by {draft.creator_name}, {draft.creator_team}
          </p>
          <h1>{draft.title}</h1>
          <p className="goal">
            <span className="muted">Goal:</span> {draft.goal || "not stated"}
          </p>
        </div>
        <div className="ws-status">
          <Status status={draft.status} />
          <span className="muted small">Version {current.number}{current.locked ? ", locked" : ""}</span>
        </div>
      </header>

      <ScanStrip scan={scan} version={current.number} rescanning={busy === "rescan"}
        onRescan={can.edit ? () => run("rescan", () => api(`/drafts/${id}/scan`, { method: "POST" }), "Re-scanned") : null} />
      <ErrorNote error={actionError} />

      <div className="ws-grid">
        <section className="ws-sheet" aria-label="Draft">
          {editing ? (
            <div className="stack">
              <label>
                Edit the draft
                <textarea className="sheet-edit" rows={14} value={editText} onChange={(e) => setEditText(e.target.value)} />
              </label>
              <div className="row">
                <Button variant="primary" busy={busy === "save"}
                  onClick={() => run("save", () => api(`/drafts/${id}/versions`, { method: "POST", body: { body: editText, note: "Edited by hand" } }), "Saved as a new version and re-scanned")}>
                  Save and re-scan
                </Button>
                <Button onClick={() => setEditing(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <ProofSheet text={current.body} findings={findings} numbers={numbers} active={active} onPick={pick} />
          )}
          <div className="legend small">
            <span><mark className="m-high">high</mark></span>
            <span><mark className="m-medium">medium</mark></span>
            <span><mark className="m-low">low</mark></span>
            <span><mark className="m-ok">supported claim</mark></span>
          </div>

          {can.edit && !editing ? (
            <div className="actions">
              <Button variant="primary" onClick={applyChoices} busy={busy === "apply"} disabled={!accepted.length && !rejected.length}>
                {accepted.length ? `Apply ${accepted.length} accepted fix${accepted.length > 1 ? "es" : ""}` : "Save decisions"}
              </Button>
              <Button onClick={() => setRewriting(true)} disabled={!issues.some((f) => f.status === "open")}>
                {system?.ai?.enabled ? "Rewrite with AI" : "Fix everything automatically"}
              </Button>
              <Button onClick={() => { setEditText(current.body); setEditing(true); }}>Edit text</Button>
              <Button variant="dark" busy={busy === "submit"} disabled={accepted.length + rejected.length > 0}
                onClick={() => run("submit", () => api(`/drafts/${id}/submit`, { method: "POST", body: {} }), "Submitted for review")}>
                Submit for review
              </Button>
              {accepted.length + rejected.length > 0 ? (
                <p className="hint">
                  You have {accepted.length + rejected.length} unsaved choice{accepted.length + rejected.length > 1 ? "s" : ""}.
                  Click “{accepted.length ? "Apply" : "Save decisions"}” first, or untick them, before submitting.
                </p>
              ) : null}
              {openHigh ? <p className="hint">{openHigh} high-severity issue{openHigh > 1 ? "s are" : " is"} still open. You can still submit; the reviewer decides.</p> : null}
            </div>
          ) : null}
          {draft.status === "in_review" && !can.review ? (
            <p className="note">This draft is with a reviewer. It is locked until they approve it or ask for changes.</p>
          ) : null}
          {draft.status === "approved" ? (
            <p className="ok-note">Approved. Version {current.number} is locked and the decision is logged.</p>
          ) : null}
          {can.review ? <ReviewPanel detail={detail} reload={reload} /> : null}
        </section>

        <section className="ws-side" aria-label="Findings and history">
          <div className="tabs" role="tablist">
            {tabs.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>
                {label}
              </button>
            ))}
          </div>

          {tab === "issues" ? (
            issues.length === 0 ? (
              <Empty title="No issues found">
                <p>Every approved rule passed. Submit it for review when you are ready.</p>
              </Empty>
            ) : (
              <div className="stack">
                {issues.map((f) => (
                  <FindingCard key={f.id} f={f} n={numbers[f.id]} active={active === f.id} onPick={setActive}
                    choice={choices[f.id]} setChoice={(c) => setChoices({ ...choices, [f.id]: c })}
                    canEdit={can.edit} canDismiss={can.dismiss} reasons={system?.dismiss_reasons || []}
                    onDismissed={() => { toast("Override recorded with your reason"); reload(); }} />
                ))}
              </div>
            )
          ) : null}

          {tab === "claims" ? (
            claims.length === 0 ? (
              <Empty title="No claims found">
                <p>Numbers, prices and absolute words such as “best” or “guaranteed” appear here with their evidence.</p>
              </Empty>
            ) : (
              <ul className="receipts">
                {claims.map((f) => (
                  <li key={f.id} id={`finding-${f.id}`} className={`receipt ${active === f.id ? "active" : ""}`} onClick={() => setActive(f.id)}>
                    <ClaimState state={f.claim_state} />
                    <p className="quote">“{f.quote}”</p>
                    <p className="small">{f.explanation}</p>
                    <p className="evidence small">
                      <span className="evidence-label">Source</span> {f.fact_code ? f.evidence : "No approved fact covers this claim."}
                    </p>
                  </li>
                ))}
              </ul>
            )
          ) : null}

          {tab === "checks" ? (
            <div className="stack">
              <p className="muted">These rules cannot be checked by software. The reviewer confirms each one before approving.</p>
              <ul className="plain">
                {detail.human_checks.map((h) => (
                  <li key={h.code} className="card"><span className="muted small">{h.code}</span> {h.text}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {tab === "history" ? <History detail={detail} /> : null}
          {tab === "comments" ? <Comments detail={detail} canComment={can.comment} reload={reload} /> : null}
        </section>
      </div>

      {rewriting ? (
        <RewriteModal draftId={id} onClose={() => setRewriting(false)} onUsed={() => { setRewriting(false); reload(); }} />
      ) : null}
    </div>
  );
}
