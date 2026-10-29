# Proofmark

**Every brand finding comes with proof.** Proofmark checks marketing drafts against a company's approved brand rules and facts before they are published, shows the evidence behind every issue, suggests fixes that keep the writer's goal, and leaves the final decision to a named reviewer.

Built by team **CODE TWINS** (Puneet Sreevatsal Jagadam, Abhi Shiktha Rudravaram) for Codex 48, problem statement by Inkloom AI.

**Live app:** https://proofmark-7972.onrender.com · **Repository:** https://github.com/itsabhi-cloud/proofmark · Demo brand: *Volta Audio* (fictional)

---

## Try it in two minutes (for judges)

No account needed. Open the link and pick a role on the sign-in screen.

1. **Creator (Riya Sharma)** → *New draft* → load the example **"Launch post with problems"** → **Create and scan**.
   You get about 13 numbered findings on the draft, each with the rule or approved fact that proves it.
   Tick **Accept fix** on a few cards → **Apply accepted fixes** (a new version is saved and re-scanned).
   Try **Fix everything automatically** (or **Rewrite with AI** when AI is on) to see a diff and the re-scan result, then **Submit for review**.
2. **Switch role → Reviewer (Arjun Rao)** → *Review queue* → open the draft.
   **Override** a finding (you must choose a reason), tick the two human-only checks, and **Approve**. The version is locked and logged.
3. **Switch role → Brand owner (Meera Iyer)** → *Rulebook* → **Load sample guideline update** → **Compile**.
   New rules appear as proposals; vague guidelines are marked *Unclear*. Approve one and it is used in the next scan.
   Open *Insights*: rule TONE-03 is flagged as a *likely unclear guideline* because reviewers keep overriding it.
4. **Viewer (Dev Patel)** can read every draft, version, decision and insight, but cannot change anything.

Every demo account also works with email + password `demo1234`. The brand owner can reset the demo from *How AI is used*.

---

## What it does

| Feature | What happens |
| --- | --- |
| Rulebook Compiler | Guideline text → individual rules, each marked *exact* (code checks it), *AI* (model judges it) or *human* (reviewer confirms). Vague sentences are flagged unclear. Owner approves each rule. |
| Approved facts library | Facts with a number, unit, source, expiry date and an optional *confidential* flag. |
| Multi-format intake | Paste text, or upload `.docx`, `.pdf`, `.md`, `.txt`. |
| Exact checks | Brand-name spelling, banned and retired terms, required disclaimers, link text, missing alt text, ALL-CAPS runs, readability, exclamation marks. |
| Claim Receipts | Every number, price and absolute claim is marked **Supported**, **Contradicted** or **Unbacked** against the facts. Expired facts count as unbacked. Numbers are compared by code, never by AI. |
| Confidentiality | Mentioning a confidential fact in a draft is a high-severity finding. Confidential facts are never sent to the AI and are hidden from creators. |
| AI tone and messaging | When an API key is set, the AI judges only the rules marked *AI* and must return strict JSON. |
| Verifier | Drops AI findings whose quoted words are not in the draft; downgrades findings citing unknown rules to *needs human judgement*. The scan strip shows the counts. |
| Evidence cards | Quote, explanation, rule or fact, severity, check method and confidence for every finding. |
| Purpose-preserving fixes | Accept or reject each fix; a full rewrite keeps the stated goal, is re-scanned before it is shown, and is retried once if issues remain. |
| Review workflow | Draft → in review (locked) → changes requested or approved (version locked). Overrides need a reason. Human-only checks must be ticked before approval. Comments. |
| Version history | Every version saved, word-level diff between any two versions, full activity log. |
| Insights | Most-broken rules, most-overridden rules (likely unclear guidelines), issues by category and team, claim outcomes, unclear rules. |
| Roles | Creator, Reviewer, Brand owner, Viewer. Enforced in the API, not just hidden in the interface. |

## How a scan works

```
draft ──► exact rules ──► claim receipts ──► mask emails/phones ──► AI (tone, messaging) ──► verifier ──► findings
             code              code              code                  optional                 code
```

If the AI key is missing, the provider fails or the quota runs out, the scan continues with exact checks and word lists, and the interface says so. The core workflow never depends on the AI being available.

## Tech stack

| Layer | Tool |
| --- | --- |
| Frontend | React 19, bundled with esbuild, hand-written CSS |
| Backend | Python 3.12, Flask, Gunicorn |
| Database | SQLite (auto-created and seeded with the demo brand) |
| AI | Google Gemini API (`gemini-3.5-flash-lite` by default) or any OpenAI-compatible API (e.g. Groq), via `requests` |
| Files | python-docx, pdfplumber |
| Hosting | Render (free web service) |

## Run locally

```bash
pip install -r requirements.txt
python wsgi.py                       # http://localhost:5050
```

Optional AI: get a free key from Google AI Studio, then
`LLM_API_KEY=your-key python wsgi.py` (Windows PowerShell: `$env:LLM_API_KEY="your-key"; python wsgi.py`).

The frontend is already built into `app/static/app.js`. To change it:

```bash
cd frontend && npm install && npm run build
```

## Deploy on Render

1. Push this repository to GitHub (public).
2. On render.com: **New → Blueprint** → pick the repo. Render reads `render.yaml`.
3. In the service's **Environment** tab, set `LLM_API_KEY` (optional).
4. Open the `.onrender.com` link. Check `/healthz` returns `{"ok": true}`.

Free Render services sleep after 15 minutes with no visitors; the next visit then waits about a minute. Keep it awake:

- **Uptime monitor (main):** create a free monitor at uptimerobot.com (or cron-job.org) that requests `https://your-app.onrender.com/healthz` every 5 minutes.
- **GitHub Actions (backup):** `.github/workflows/keep-alive.yml` pings every 10 minutes once you add a repository variable `RENDER_URL` (Settings → Secrets and variables → Actions → Variables).

Render gives each workspace 750 free instance hours a month, enough for one service running all month. Other free services in the same Render workspace share those hours, so do not keep a second free service awake at the same time. The SQLite file is reset when the service restarts, so the demo always starts from the same clean data.

## Tests and accuracy

```bash
python -m unittest discover tests     # 29 tests: engine, verifier with a faked AI, AI retry, full API workflow, roles
python scripts/benchmark.py           # planted-error benchmark → BENCHMARK.md
```

The benchmark runs 30 drafts through the real pipeline. See `BENCHMARK.md` for results and its limits.

## Project structure

```
app/
  __init__.py        app factory, security headers, serves the React app
  api.py             all JSON endpoints and role checks
  db.py              SQLite schema and helpers
  services.py        drafts, versions, scans, diff, insights
  seed.py            fictional Volta Audio demo data
  engine/
    exact.py         deterministic rule checks
    claims.py        Claim Receipts (numbers, prices, superlatives)
    ai.py            AI providers, prompts and the verifier
    scan.py          the pipeline, safe fixes and rewrite loop
    compiler.py      Rulebook Compiler
    parse.py         .docx / .pdf / text extraction
    text_utils.py    sentences, readability, PII masking, retrieval
  static/            built frontend (index.html, app.js, styles.css)
frontend/src/        React source (pages/, ui.jsx, main.jsx)
tests/               unit + API tests, benchmark_set.json
scripts/benchmark.py
docs/CODE_GUIDE.md   file-by-file explanation for the team
```

## Known limitations

- Personal names are not masked before AI calls (emails and phone numbers are).
- Numbers written as words ("twenty hours") are only caught in AI mode.
- Images are accepted only as references in text (alt-text check); visual checks are planned for Round 3.
- Demo data lives in SQLite and resets on restart; Round 3 moves to Postgres.

## Disclosures

See [DISCLOSURES.md](DISCLOSURES.md) for AI assistance, external services and libraries.
