import { useState } from "react";
import { api } from "../api.js";
import { Button, PageHeader, useApp } from "../ui.jsx";

export default function About() {
  const { system, user } = useApp();
  const [busy, setBusy] = useState(false);
  const ai = system?.ai || {};
  const reset = async () => {
    if (!window.confirm("Reset the demo workspace for everyone using it right now? All drafts and changes are replaced with the original demo data.")) return;
    setBusy(true);
    await api("/demo/reset", { method: "POST" }).catch(() => {});
    window.location.hash = "/";
    window.location.reload();
  };
  return (
    <>
      <PageHeader title="How AI is used" lead="Proofmark tells you which findings come from code and which from AI." />
      <div className="prose">
        <p className="card">
          {ai.enabled
            ? <>AI is on. Provider: <strong>{ai.provider}</strong>, model: <strong>{ai.model}</strong>.</>
            : <>AI is off in this deployment. Findings come from exact checks and word lists, and the rewrite applies safe fixes only.</>}
        </p>
        <h2>What runs in each scan</h2>
        <ol>
          <li><strong>Exact checks</strong> run first: brand names, banned words, required phrases, numbers against approved facts, expired facts, confidential mentions, link text, alt text, capitals and readability. These are repeatable.</li>
          <li><strong>AI</strong> judges only the rules marked “AI” (tone and messaging). It must reply in strict JSON with the exact quoted words and a rule code.</li>
          <li><strong>The verifier</strong> drops any AI finding whose quote is not in the draft, and downgrades any finding that cites a rule not in the approved rulebook to “needs human judgement”.</li>
          <li><strong>Human checks</strong> (logo use, product photos) are never automated. The reviewer confirms them before approving.</li>
        </ol>
        <h2>What is sent to the AI</h2>
        <ul>
          <li>The draft, with email addresses and phone numbers masked first.</li>
          <li>The AI-checked rules and up to eight relevant approved facts.</li>
          <li>Never facts marked confidential ({system?.confidential_facts ?? 0} in this workspace).</li>
        </ul>
        <h2>What AI never does</h2>
        <ul>
          <li>Decide whether a number is right. Code compares every number.</li>
          <li>Change a draft without the creator accepting it. Every rewrite is re-scanned and shown as a diff first.</li>
          <li>Approve or reject content. Only a named reviewer can.</li>
        </ul>
        <p className="muted small">The demo brand, Volta Audio, and all its data are fictional.</p>
        {user.role === "owner" ? (
          <p><Button onClick={reset} busy={busy}>Reset demo workspace</Button></p>
        ) : null}
      </div>
    </>
  );
}
