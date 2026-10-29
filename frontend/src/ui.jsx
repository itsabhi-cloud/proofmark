import { createContext, useContext, useEffect, useState } from "react";
import { STATUS_LABEL } from "./api.js";

export const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

export function navigate(path) {
  window.location.hash = path;
}

export function Link({ to, children, className, ...rest }) {
  return (
    <a href={`#${to}`} className={className} {...rest}>
      {children}
    </a>
  );
}

const SEV_TEXT = { high: "High", medium: "Medium", low: "Low", info: "Info" };
const SEV_ICON = { high: "▲", medium: "◆", low: "●", info: "✓" };

export function Severity({ level }) {
  return (
    <span className={`sev sev-${level}`}>
      <span aria-hidden="true">{SEV_ICON[level]}</span> {SEV_TEXT[level] || level}
    </span>
  );
}

const METHOD_TEXT = {
  exact: "Exact check",
  ai: "AI",
  heuristic: "Word list",
  human: "Human",
};
const METHOD_HELP = {
  exact: "Found by a deterministic rule. Same input, same result.",
  ai: "Judged by the AI and confirmed by the verifier.",
  heuristic: "Matched a listed word. Used when AI is off.",
  human: "Only a person can check this.",
};

export function Method({ method }) {
  return (
    <span className={`method method-${method}`} title={METHOD_HELP[method]}>
      {METHOD_TEXT[method] || method}
    </span>
  );
}

export function Status({ status }) {
  return <span className={`status status-${status}`}>{STATUS_LABEL[status] || status}</span>;
}

export function ClaimState({ state }) {
  if (!state) return null;
  return <span className={`claim claim-${state.toLowerCase()}`}>{state}</span>;
}

export function Button({ variant = "secondary", busy, children, ...rest }) {
  return (
    <button className={`btn btn-${variant}`} disabled={busy || rest.disabled} {...rest}>
      {busy ? <span className="spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {children}
    </div>
  );
}

export function Loading({ label = "Loading" }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" /> {label}…
    </div>
  );
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return (
    <p className="error-note" role="alert">
      {error}
    </p>
  );
}

export function PageHeader({ title, lead, children }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {lead ? <p className="lead">{lead}</p> : null}
      </div>
      {children ? <div className="page-actions">{children}</div> : null}
    </header>
  );
}

export function Toasts() {
  const { toasts } = useApp();
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          {t.text}
        </div>
      ))}
    </div>
  );
}

export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => live && setState({ loading: false, data, error: null }))
      .catch((e) => live && setState({ loading: false, data: null, error: e.message }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload: () => setTick((t) => t + 1) };
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function DiffView({ segments }) {
  return (
    <div className="diff">
      {segments.map((s, i) =>
        s.op === "equal" ? (
          <span key={i}>{s.text}</span>
        ) : s.op === "insert" ? (
          <ins key={i}>{s.text}</ins>
        ) : (
          <del key={i}>{s.text}</del>
        )
      )}
    </div>
  );
}
