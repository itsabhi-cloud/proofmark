# Disclosures

Codex 48 rules ask teams to disclose AI assistance, templates, external services and reused material. This file is that disclosure.

## AI assistance in building the product

- Few parts of the source code (backend engine, API, React frontend, tests and documentation) were generated with **Claude (Anthropic)**, an AI assistant, during the Round 2 build window, from our Round 1 design.
- The team defined the product, workflow, rules and features in Round 1, and reviewed, ran, tested and deployed the code. Each member can explain the parts listed as theirs in `docs/CODE_GUIDE.md`.
- No templates or code written before the build window were used.

## AI inside the product

- Optional: Google Gemini API (default model `gemini-3.5-flash-lite`) or any OpenAI-compatible API, used only for tone and messaging checks, claim extraction, rewrites and rule compiling.
- Emails and phone numbers are masked, and confidential facts are removed, before any text is sent.
- Every AI finding is labelled "AI" and checked by the verifier. Without an API key, the product runs with no external AI at all.

## External services and libraries

| Item | Use | Licence |
| --- | --- | --- |
| Flask, Werkzeug | Web server | BSD-3 |
| Gunicorn | Production server | MIT |
| requests | AI API calls | Apache-2.0 |
| python-docx | Read .docx uploads | MIT |
| pdfplumber | Read .pdf uploads | MIT |
| React, React DOM | Interface | MIT |
| esbuild | Frontend bundler | MIT |
| IBM Plex Sans, Source Serif 4 (Google Fonts) | Typefaces | SIL Open Font Licence |
| Render | Hosting | Free plan |

## Data

The brand "Volta Audio", its people, products, facts and drafts are fictional and created for this demo. Survey figures in our proposal come from the third-party reports linked there.
