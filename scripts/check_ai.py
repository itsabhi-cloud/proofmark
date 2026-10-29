"""Check that the AI connection works before you deploy or demo.

    export LLM_API_KEY=your-key            (Mac / Linux)
    python scripts/check_ai.py

Prints the provider and model, sends one tiny test scan, and shows what the verifier kept.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.engine import ai  # noqa: E402
from app.engine.scan import scan_text  # noqa: E402
from app.seed import FACTS, RULES  # noqa: E402

cfg = ai.config()
if not cfg["enabled"]:
    print("AI is OFF: LLM_API_KEY is not set. Run:  export LLM_API_KEY=your-key")
    sys.exit(1)
print(f"Provider: {cfg['provider']}   Model: {cfg['model']}")
try:
    ai.call_json('Reply only with JSON: {"ok": true}', "Say ok.")
    print("Connection: OK")
except ai.AIUnavailable as e:
    print(f"Connection FAILED: {e}")
    print("Check: key copied fully, model name exists (try LLM_MODEL=gemini-3.5-flash-lite), free-tier limit not reached.")
    sys.exit(1)

rules = [{**r, "status": "approved"} for r in RULES]
text = "If you don't buy now you'll regret it forever. These buds slap, no cap."
findings, summary = scan_text(text, rules, FACTS, "Ad")
print(f"Scan mode: {summary['mode']}   Verifier: {summary['verifier']}")
for f in findings:
    if f["method"] == "ai":
        print(f"  AI finding [{f['rule_code']}] \"{f['quote']}\": {f['explanation']}")
if summary["mode"] != "exact+ai":
    print("AI did not run in the scan:", summary.get("ai_error"))
    sys.exit(1)
print("All good. AI is working.")
