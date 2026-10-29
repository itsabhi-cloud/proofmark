# Proofmark: Round 2 submission (team CODE TWINS)

Paste-ready answers for the Codex 48 Round 2 form and report.

## 1. Links

- **Live app:** https://proofmark-7972.onrender.com (no sign-up: pick a role on the sign-in screen; a "Start here" tour is on that screen)
- **Public repository:** https://github.com/itsabhi-cloud/proofmark
- **Team:** Abhi Shiktha Rudravaram (team lead), Puneet Sreevatsal Jagadam
- **Problem statement:** brand governance for marketing content (Inkloom AI)

## 2. Completed features (all working in the live app)

1. **Four roles with server-side permissions:** Creator, Reviewer, Brand owner, Viewer. Every write endpoint checks the role in the API (`login_required`), not just in the interface. Creators cannot open others' drafts; reviewers cannot approve their own; viewers are read-only.
2. **Draft intake:** paste text or upload `.docx`, `.pdf`, `.md`, `.txt`; three sample drafts for a quick demo.
3. **Exact checks (code):** brand-name spelling and casing, banned and retired terms, required disclaimers, vague link text ("click here"), missing image alt text, ALL-CAPS runs, readability, repeated exclamation marks.
4. **Claim Receipts:** every number, price and absolute claim ("best", "waterproof") is marked Supported, Contradicted or Unbacked against the approved facts library. Numbers are compared by code, never by AI. Expired facts count as unbacked.
5. **Confidentiality guard:** facts flagged confidential are never sent to the AI, are hidden from creators, and mentioning one in a draft is a high-severity finding.
6. **AI tone and messaging checks (Gemini):** only rules marked "AI" are sent to the model, which must reply in strict JSON. Emails and phone numbers are masked first.
7. **Verifier:** drops any AI finding whose quoted words are not in the draft, and downgrades findings citing an unknown rule to "needs human judgement". The scan strip shows what it kept and dropped.
8. **Evidence cards:** each finding shows the quote, explanation, rule or fact, severity, check method (exact / AI / word list) and confidence, with numbered highlights on the draft.
9. **Purpose-preserving fixes:** accept or keep each suggestion; accepted fixes are applied in one batch and re-scanned. "Rewrite with AI" (or "Fix everything automatically" when AI is off) re-scans the proposal before showing it, retries once if issues remain, and shows a word-level diff.
10. **Review workflow:** draft → in review (locked) → changes requested or approved (version locked). Overrides need a reason; human-only checks must be ticked before Approve; comments on each version.
11. **Version history and audit log:** every version saved, diff between any two versions, full activity log.
12. **Rulebook Compiler:** guideline text becomes individual rules, each marked exact, AI or human; vague sentences ("where appropriate") are flagged *Unclear*. The brand owner approves each proposed rule before it is used.
13. **Insights:** most-broken rules, most-overridden rules (a rule overridden 2+ times with a "Rule unclear" reason is flagged as a likely unclear guideline), issues by category and team, claim outcomes.
14. **Graceful AI fallback:** if the key is missing, the model is slow, or the free tier is rate-limited, the scan still completes with exact checks and word lists, and the interface says why and offers "Try the AI again".

## 3. Technology and implementation

| Layer | Choice |
| --- | --- |
| Frontend | React 19, bundled with esbuild into one file, hand-written CSS, hash routing |
| Backend | Python 3.12, Flask, Gunicorn (1 worker, 4 threads) |
| Database | SQLite, created and seeded with the fictional brand "Volta Audio" at start-up |
| AI | Google Gemini API, model `gemini-3.5-flash-lite`, called with `requests` (any OpenAI-compatible API also works) |
| File parsing | python-docx, pdfplumber |
| Hosting | Render free web service from `render.yaml`; UptimeRobot plus a GitHub Actions ping keep it awake |

**Scan pipeline:** `draft → exact rules → claim receipts → mask emails/phones → AI (tone, messaging) → verifier → findings`. Every finding stores the exact character offsets it points at, so the interface can highlight it and fixes can be applied safely (applied right-to-left so earlier edits never shift later offsets). When an exact finding and an AI finding cover the same words, the exact one wins.

**Demo seed:** 19 rules (14 exact, 3 AI, 2 human-only), 9 approved facts (1 confidential), 5 demo accounts.

**Reliability details:** the AI call has a 25-second limit and one retry on HTTP 429/503, so a full AI rewrite (up to 4 calls) finishes inside Gunicorn's 120-second limit; any other AI error falls back to offline checks. Session cookies are HttpOnly, SameSite=Lax and Secure in production; security headers (nosniff, frame deny, same-origin referrer) are set on every response.

## 4. Changes from the Round 1 plan, and why

| Round 1 plan | Round 2 build | Why |
| --- | --- | --- |
| FastAPI | Flask | Smaller, synchronous code we could both read and explain line by line; the app has no need for async. |
| Supabase (Postgres) | SQLite | Zero setup, no external account, resets to clean demo data on every restart, which suits judging. Postgres is planned for Round 3. |
| Supabase Auth | Demo role sign-in (plus email + password) with server-side permission checks | Judges can try every role in one click without creating accounts; permissions are still enforced on the server. |
| Vite + Tailwind | esbuild + hand-written CSS | One build command, one output file served by Flask, no CSS framework to configure. |

**Changes made during final testing (29 Oct 2026):**
- The default model alias `gemini-flash-latest` had started pointing to a slower "thinking" model (42 to 72 seconds per scan, over our time limit), so AI scans were silently falling back. We pinned `gemini-3.5-flash-lite` (about 2 seconds per scan).
- Added one automatic retry when Gemini says it is rate-limited or busy, a shorter per-call timeout, and a unit test for the retry.
- Interface: a "Start here" tour on the sign-in screen, plain-language messages when the AI falls back with a "Try the AI again" button, waiting messages during scans and rewrites, a "Back to drafts" link on error pages, and a clearer warning on the demo reset.
- Bug fix: "Submit for review" is now blocked while the creator has unapplied fix choices (before, those choices were silently lost).
- Benchmark: added an AI-mode section next to the offline results.

## 5. Three improvements planned for Round 3

1. **Visual and accessibility review of images and PDFs:** check logo use, colours and contrast, and text inside images, and generate alt-text suggestions. Today images are only checked for missing alt text.
2. **Rulebook learning loop from overrides:** when reviewers keep overriding a rule, propose a reworded rule or a new exception to the brand owner, and measure whether overrides drop afterwards. Today Insights only flags such rules as likely unclear.
3. **Real teams and a publishing gate:** real accounts and invitations, Postgres, multiple brands per workspace, and an API that a CMS or scheduler can call to block publishing until a draft is approved.

## 6. Testing evidence and honest limits

- **Automated tests:** 28 passing (`python -m unittest discover tests`): 22 engine tests (claims, exact rules, fixes, compiler, verifier with a faked AI, AI fallback, AI retry, confidential facts not sent to the AI) and 6 API tests (full workflow and role permissions).
- **Planted-error benchmark** (30 drafts, see `BENCHMARK.md`):
  - Offline: 29/29 planted errors caught, 0 false alarms, 0/3 hard cases.
  - With AI (one run): 27/29 caught, 3 false alarms, 2/3 hard cases.
- **Limits:** the benchmark drafts were written by our team alongside the rules, so it mainly shows the checks work as designed; real drafts will score lower. AI results vary between runs. We have not yet tested with outside users. Personal names are not masked before AI calls; numbers written as words are only caught in AI mode; demo data resets when the server restarts.

## 7. Team contributions

- **Abhi Shiktha Rudravaram (team lead):** project lead and repository owner; deployment on Render and keep-awake setup; interface and workflow review (role journeys, usability fixes); Round 2 report.
- **Puneet Sreevatsal Jagadam:** backend engine (exact checks, Claim Receipts, scan pipeline), AI integration and verifier, tests and benchmark.

## 8. AI-assistance disclosure

Large parts of the source code (backend, React frontend, tests and documentation) were generated with Claude (Anthropic), an AI assistant, from our Round 1 design. Claude Code was also used in final testing to diagnose the Gemini model issue, make the fixes listed above and prepare this document. The team defined the product and workflow, reviewed and ran the code, tested it and deployed it. Inside the product, Google Gemini is used only for tone/messaging checks, rewrites and rule compiling, and every AI finding is labelled and verified. Full list of services and libraries: `DISCLOSURES.md`.
