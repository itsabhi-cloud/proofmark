import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, ROLE_LABEL } from "./api.js";
import { AppContext, Button, ErrorNote, Link, Loading, Toasts } from "./ui.jsx";
import Drafts from "./pages/Drafts.jsx";
import NewDraft from "./pages/NewDraft.jsx";
import Workspace from "./pages/Workspace.jsx";
import Rulebook from "./pages/Rulebook.jsx";
import Facts from "./pages/Facts.jsx";
import Insights from "./pages/Insights.jsx";
import Activity from "./pages/Activity.jsx";
import About from "./pages/About.jsx";

function useHash() {
  const [hash, setHash] = useState(window.location.hash.slice(1) || "/");
  useEffect(() => {
    const on = () => setHash(window.location.hash.slice(1) || "/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

const NAV = [
  { to: "/drafts", label: "Drafts", roles: ["creator", "reviewer", "owner", "viewer"] },
  { to: "/new", label: "New draft", roles: ["creator", "owner"] },
  { to: "/review", label: "Review queue", roles: ["reviewer", "owner"] },
  { to: "/rulebook", label: "Rulebook", roles: ["creator", "reviewer", "owner", "viewer"] },
  { to: "/facts", label: "Approved facts", roles: ["creator", "reviewer", "owner", "viewer"] },
  { to: "/insights", label: "Insights", roles: ["reviewer", "owner", "viewer"] },
  { to: "/activity", label: "Activity log", roles: ["creator", "reviewer", "owner", "viewer"] },
  { to: "/about", label: "How AI is used", roles: ["creator", "reviewer", "owner", "viewer"] },
];

const ROLE_INTRO = {
  creator: "Write a draft, scan it, accept fixes, submit for review.",
  reviewer: "Open the review queue, override findings with a reason, approve or send back.",
  owner: "Compile guidelines into rules, manage approved facts, see insights.",
  viewer: "Read-only: every version, decision and insight.",
};

function Login({ onLogin }) {
  const [accounts, setAccounts] = useState([]);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    api("/demo-accounts").then((d) => setAccounts(d.accounts)).catch((e) => setError(e.message));
  }, []);

  const signIn = async (payload, key) => {
    setBusy(key);
    setError(null);
    try {
      const d = await api("/auth/login", { method: "POST", body: payload });
      onLogin(d.user);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="login">
      <section className="login-intro">
        <p className="wordmark-lg">
          <span className="mark" aria-hidden="true">¶</span>Proofmark
        </p>
        <h1>Check every draft against your brand before it goes out.</h1>
        <p className="login-lead">
          Proofmark compares content with approved brand rules and facts, shows the evidence for every issue,
          suggests fixes that keep the writer’s goal, and leaves the final approval to a person.
        </p>
        <div className="sample-proof" aria-hidden="true">
          <p>
            <mark className="m-high">Hurry!!</mark> Our earbuds give you <mark className="m-high">24 hours</mark> of
            battery, <mark className="m-med">the best in India</mark>.
          </p>
          <p className="sample-note">
            Approved fact FACT-01: up to 10 hours per charge. Suggested fix: “up to 10 hours”.
          </p>
        </div>
      </section>

      <section className="login-panel" aria-labelledby="signin-title">
        <h2 id="signin-title">Try the demo workspace</h2>
        <p className="muted">
          Volta Audio is a fictional brand. Pick a role to sign in; you can switch roles at any time.
        </p>
        <div className="start-here">
          <p className="start-title">Start here: the 2-minute tour</p>
          <ol>
            <li><strong>Creator</strong>: New draft → load “Launch post with problems” → Create and scan. Accept a few fixes, apply them, then Submit for review.</li>
            <li><strong>Reviewer</strong>: Review queue → open the draft → override one finding with a reason, tick the human checks, Approve.</li>
            <li><strong>Brand owner</strong>: Rulebook → Load sample guideline update → Compile, approve a rule. Then open Insights.</li>
            <li><strong>Viewer</strong>: can read everything but change nothing.</li>
          </ol>
          <p className="hint">Use “Switch role” at the bottom of the menu to move between steps.</p>
        </div>
        <ErrorNote error={error} />
        <ul className="role-list">
          {accounts.map((a) => (
            <li key={a.email}>
              <button
                className="role-card"
                onClick={() => signIn({ demo_email: a.email }, a.email)}
                disabled={!!busy}
              >
                <span className="role-name">
                  {ROLE_LABEL[a.role]}
                  {busy === a.email ? <span className="spinner" aria-hidden="true" /> : null}
                </span>
                <span className="role-who">
                  {a.name} · {a.team}
                </span>
                <span className="role-what">{ROLE_INTRO[a.role]}</span>
              </button>
            </li>
          ))}
        </ul>
        <details className="pw-login">
          <summary>Sign in with email and password</summary>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              signIn({ email, password }, "pw");
            }}
          >
            <label>
              Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </label>
            <label>
              Password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <p className="hint">Demo accounts use the password demo1234.</p>
            <Button variant="primary" type="submit" busy={busy === "pw"}>
              Sign in
            </Button>
          </form>
        </details>
      </section>
    </main>
  );
}

function Shell({ user, system, route, onLogout, children }) {
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [route]);
  return (
    <div className="shell">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="sidebar-top">
          <Link to="/drafts" className="wordmark">
            <span className="mark" aria-hidden="true">¶</span>Proofmark
          </Link>
          <button className="icon-btn menu-btn" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Menu">
            ☰
          </button>
        </div>
        <p className="brand-line">
          {system?.brand?.name} <span className="muted">workspace</span>
        </p>
        <nav aria-label="Main">
          {NAV.filter((n) => n.roles.includes(user.role)).map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={`nav-item ${route.startsWith(n.to) ? "active" : ""}`}
              aria-current={route.startsWith(n.to) ? "page" : undefined}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ai-pill" title="How findings are produced right now">
          {system?.ai?.enabled ? (
            <>
              AI on: <strong>{system.ai.model}</strong>
            </>
          ) : (
            <>AI off: exact checks and word lists only</>
          )}
        </div>
        <div className="user-card">
          <p className="user-name">{user.name}</p>
          <p className="user-role">
            {ROLE_LABEL[user.role]} · {user.team}
          </p>
          <button className="link-btn" onClick={onLogout}>
            Switch role
          </button>
        </div>
      </aside>
      <main id="main" className="main" tabIndex={-1}>
        {children}
      </main>
      <Toasts />
    </div>
  );
}

function Router({ route, user }) {
  const m = route.match(/^\/drafts\/(\d+)/);
  if (m) return <Workspace id={Number(m[1])} />;
  if (route.startsWith("/new")) return <NewDraft />;
  if (route.startsWith("/review")) return <Drafts reviewQueue />;
  if (route.startsWith("/rulebook")) return <Rulebook />;
  if (route.startsWith("/facts")) return <Facts />;
  if (route.startsWith("/insights")) return <Insights />;
  if (route.startsWith("/activity")) return <Activity />;
  if (route.startsWith("/about")) return <About />;
  return <Drafts />;
}

function App() {
  const route = useHash();
  const [user, setUser] = useState(undefined);
  const [system, setSystem] = useState(null);
  const [toasts, setToasts] = useState([]);

  const toast = useCallback((text, kind = "ok") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  useEffect(() => {
    api("/auth/me").then((d) => setUser(d.user)).catch(() => setUser(null));
    api("/system").then(setSystem).catch(() => {});
  }, []);

  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    setUser(null);
    window.location.hash = "/";
  };

  if (user === undefined)
    return (
      <div className="stack" style={{ padding: "2rem" }}>
        <Loading label="Opening Proofmark" />
        <p className="hint">The free server sleeps when nobody uses it. If it was asleep, the first visit can take up to a minute.</p>
      </div>
    );
  if (!user)
    return (
      <Login
        onLogin={(u) => {
          setUser(u);
          window.location.hash = u.role === "reviewer" ? "/review" : u.role === "owner" ? "/rulebook" : "/drafts";
        }}
      />
    );

  return (
    <AppContext.Provider value={{ user, system, toast, setUser, toasts }}>
      <Shell user={user} system={system} route={route} onLogout={logout}>
        <Router route={route} user={user} />
      </Shell>
    </AppContext.Provider>
  );
}

createRoot(document.getElementById("root")).render(<App />);
