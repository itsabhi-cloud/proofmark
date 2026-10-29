# Code guide for CODE TWINS

Read this before judging. Judges may ask either of you to explain your part, so each section says who presents it.

## The one-minute explanation

A draft goes through a pipeline: **exact checks → claim receipts → (optional) AI → verifier**. Every finding stores the exact characters it points at, so the interface can highlight it and a fix can be applied safely. Nothing is published or approved by software; a reviewer decides.

---

## Puneet: backend, engine, AI

| File | What it does | Things to be able to say |
| --- | --- | --- |
| `app/engine/exact.py` | One function per rule type (`banned`, `term_case`, `required`, `pattern`, `link_text`, `alt_text`, `all_caps`, `readability`) plus the confidential-leak check. Each returns findings with `start`/`end` character offsets. | `_flex_pattern` lets "Volta Audio" also match "volta-audio" and "VoltaAudio". `match_case` keeps capital letters when replacing. |
| `app/engine/claims.py` | Finds numbers with units (`NUMBER_UNIT_RE`), prices (`CURRENCY_RE`) and superlatives, then picks the approved fact with the same unit whose keywords best match the claim's **clause**, falling back to the sentence. | `max` facts: a claim may be lower, never higher. `exact` facts (prices, warranty) must match. Expired facts make the claim unbacked. AI never compares numbers. |
| `app/engine/ai.py` | `call_json` talks to Gemini or an OpenAI-compatible API and forces JSON output, retrying once on 429/503. `verify_findings` is the trust layer. | Verifier rules: quote must exist in the draft, else dropped; rule code must be an approved AI rule, else "needs human judgement". Tested with a fake AI in `tests/test_engine.py`. |
| `app/engine/scan.py` | `scan_text` runs the whole pipeline and dedupes (exact findings win over AI on the same words). `apply_fixes` applies suggestions right-to-left so offsets stay valid. `rewrite_draft` re-scans every proposal and retries once. | Why right-to-left: changing text at the start would shift every later offset. |
| `app/engine/compiler.py` | AI compiler with validation (`_clean`), and an offline regex compiler (`heuristic_compile`). | Any invalid AI rule becomes a safe "human" rule instead of breaking. Vague words list marks rules unclear. |
| `app/engine/text_utils.py` | Sentence splitting, Flesch reading ease, `mask_pii`, keyword retrieval. | Masking keeps the same length so AI offsets still line up with the original text. |
| `app/api.py` | Every endpoint. `login_required(*roles)` checks the role on the server. | Creators can't open others' drafts; reviewers can't approve their own; approval needs the human checks; drafts lock in review. |
| `app/db.py`, `app/services.py`, `app/seed.py` | Schema, business logic, demo data. | Insights "likely unclear" = a rule overridden 2+ times with at least one "Rule unclear" reason. |
| `tests/`, `scripts/benchmark.py` | 28 tests and the planted-error benchmark. | Be honest that the benchmark was written alongside the rules (see BENCHMARK.md). |

## Abhi: frontend, workflow, UX

| File | What it does | Things to be able to say |
| --- | --- | --- |
| `frontend/src/main.jsx` | App shell, hash router, sign-in screen with role cards, sidebar that shows only the pages a role can use. | Hash routing means the app works on any static host with no server config. |
| `frontend/src/pages/Workspace.jsx` | The core screen. `ProofSheet` turns findings into highlighted, numbered marks (`buildSegments`). `FindingCard` handles accept / keep / override. `RewriteModal`, `History` (diffs), `Comments`, `ReviewPanel`. | Fixes are chosen in batches and applied in one call, then re-scanned, so offsets never go stale. Approve is disabled until human checks are ticked. |
| `frontend/src/pages/Rulebook.jsx` | Compiler box, proposals to approve or reject, rules by category, reword and turn off. | Rewording a rule clears its unclear flag. |
| `frontend/src/pages/Facts.jsx` | Facts table and add form, confidential flag, expiry shown in red. | Creators see confidential facts only as "Confidential". |
| `frontend/src/pages/Insights.jsx`, `Activity.jsx`, `About.jsx`, `Drafts.jsx`, `NewDraft.jsx` | Dashboards, audit log, AI disclosure page, lists, new draft with upload and samples. | |
| `frontend/src/ui.jsx`, `app/static/styles.css` | Shared components and the design: a proofreader's desk, white proof sheet with a red margin line, severity shown by colour **and** icon and word. | Accessibility: keyboard focus rings, skip link, labelled controls, colour never the only signal, works on mobile. |

---

## Questions judges may ask

- **How do you stop the AI from making things up?** The verifier. Show the scan strip line "Verifier: kept X of Y" and the test `test_drops_invented_quotes_and_flags_unknown_rules`.
- **What if the AI is down?** The scan falls back to exact checks and word lists and says so. Test: `test_ai_failure_falls_back_offline`.
- **How is confidential data protected?** Confidential facts are never in the AI prompt (test `test_confidential_facts_not_sent_to_ai`), are hidden from creators, and mentioning one in a draft is flagged high.
- **Why not let AI check numbers?** Language models are unreliable at comparing figures; code is exact and repeatable.
- **What changed from Round 1?** See the Round 2 report: Flask instead of FastAPI, SQLite instead of Supabase, demo role sign-in instead of Supabase Auth, esbuild and plain CSS instead of Vite and Tailwind.
