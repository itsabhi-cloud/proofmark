"""Unit tests for the scan engine. Run: python -m unittest discover tests"""
import json
import os
import unittest
from datetime import date

from app.engine import ai
from app.engine.claims import numeric_claims, superlative_claims
from app.engine.compiler import heuristic_compile, _clean
from app.engine.scan import apply_fixes, scan_text
from app.engine.text_utils import mask_pii, find_span
from app.seed import FACTS, RULES

TODAY = date(2026, 10, 29)


def approved(rules):
    return [{**r, "status": "approved"} for r in rules]


RULESET = approved(RULES)
NUM_RULE = next(r for r in RULESET if r["kind"] == "numeric_claims")
SUP_RULE = next(r for r in RULESET if r["kind"] == "unbacked_claims")


def codes(findings):
    return {f["rule_code"] for f in findings if f["severity"] != "info"}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(self.payload)}]}}]}


def fake_post(payload):
    return lambda *a, **k: FakeResponse(payload)


class ClaimTests(unittest.TestCase):
    def state(self, text):
        return [(f["quote"], f["claim_state"], f["fact_code"]) for f in numeric_claims(text, NUM_RULE, FACTS, TODAY)]

    def test_overstated_battery_is_contradicted(self):
        self.assertEqual(self.state("Get 24 hours of battery."), [("24 hours", "Contradicted", "FACT-01")])

    def test_matching_claims_are_supported(self):
        out = self.state("Up to 10 hours of playback per charge, and up to 30 hours in total with the charging case.")
        self.assertEqual([s for _, s, _ in out], ["Supported", "Supported"])
        self.assertEqual([c for _, _, c in out], ["FACT-01", "FACT-02"])

    def test_wrong_price_is_contradicted_with_fix(self):
        f = numeric_claims("Now just ₹2,499!", NUM_RULE, FACTS, TODAY)[0]
        self.assertEqual((f["claim_state"], f["suggestion"]), ("Contradicted", "₹2,999"))

    def test_expired_fact_is_unbacked(self):
        f = numeric_claims("Get 20% off this week.", NUM_RULE, FACTS, TODAY)[0]
        self.assertEqual((f["claim_state"], f["fact_code"]), ("Unbacked", "FACT-07"))

    def test_number_without_fact_is_unbacked(self):
        self.assertEqual(self.state("Weighs only 4 g.")[0][1], "Unbacked")

    def test_superlative_unbacked(self):
        out = superlative_claims("The best earbuds in town.", SUP_RULE, FACTS)
        self.assertEqual(out[0]["claim_state"], "Unbacked")

    def test_confidential_facts_never_back_claims(self):
        conf = [{**FACTS[0], "confidential": 1}]
        self.assertEqual(numeric_claims("10 hours of battery", NUM_RULE, conf, TODAY)[0]["claim_state"], "Unbacked")


class ExactTests(unittest.TestCase):
    def scan(self, text, ctype="Social post"):
        return scan_text(text, RULESET, FACTS, ctype, use_ai=False, today=TODAY)

    def test_brand_name_case(self):
        f, _ = self.scan("Meet volta audio today.")
        hit = [x for x in f if x["rule_code"] == "TERM-01"][0]
        self.assertEqual((hit["quote"], hit["suggestion"]), ("volta audio", "Volta Audio"))

    def test_correct_name_not_flagged(self):
        f, _ = self.scan("Meet Volta Audio today.")
        self.assertNotIn("TERM-01", codes(f))

    def test_banned_word_with_replacement(self):
        f, _ = self.scan("Cheap and cheerful.")
        hit = [x for x in f if x["rule_code"] == "TERM-03"][0]
        self.assertEqual(hit["suggestion"], "Affordable")

    def test_required_phrase_only_when_offer(self):
        self.assertIn("LEGAL-01", codes(self.scan("Big sale this weekend.")[0]))
        self.assertNotIn("LEGAL-01", codes(self.scan("Sound for everyday life.")[0]))
        self.assertNotIn("LEGAL-01", codes(self.scan("Big sale this weekend.", "Blog post")[0]))

    def test_confidential_leak(self):
        f, _ = self.scan("A sneak peek of the Buds Air 2.")
        self.assertTrue(any(x["category"] == "confidentiality" and x["severity"] == "high" for x in f))

    def test_accessibility(self):
        f, _ = self.scan("Click here. ![](a.png) THIS IS LOUD TEXT", "Email")
        self.assertTrue({"A11Y-01", "A11Y-02", "A11Y-04"} <= codes(f))

    def test_clean_copy_has_no_issues(self):
        f, s = self.scan("Volta Buds Air give you up to 10 hours of playback per charge. Sound for everyday life.",
                         "Product page")
        self.assertEqual(codes(f), set())
        self.assertEqual(s["mode"], "exact+heuristic")

    def test_apply_fixes_right_to_left(self):
        text = "Hurry!! Volta audio is cheap."
        f, _ = self.scan(text)
        new, n = apply_fixes(text, [x for x in f if x["suggestion"] is not None])
        self.assertIn("Volta Audio", new)
        self.assertIn("affordable", new)
        self.assertNotIn("!!", new)
        self.assertGreaterEqual(n, 3)


class VerifierTests(unittest.TestCase):
    """The AI is faked: these tests prove what the verifier does with bad AI output."""

    def setUp(self):
        self._disabled = os.environ.pop("AI_DISABLED", None)
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_PROVIDER"] = "gemini"

    def tearDown(self):
        os.environ.pop("LLM_API_KEY", None)
        if self._disabled is not None:
            os.environ["AI_DISABLED"] = self._disabled

    def test_drops_invented_quotes_and_flags_unknown_rules(self):
        text = "Our sound is crazy loud and you will love it."
        payload = {"findings": [
            {"quote": "crazy loud", "rule_code": "TONE-03", "explanation": "Slang.", "severity": "low",
             "confidence": "High", "suggestion": "really clear"},
            {"quote": "words that are not in the draft", "rule_code": "TONE-01", "explanation": "x"},
            {"quote": "you will love it", "rule_code": "MADE-UP-9", "explanation": "x"},
        ]}
        findings, summary = scan_text(text, RULESET, FACTS, "Social post", today=TODAY, _post=fake_post(payload))
        v = summary["verifier"]
        self.assertEqual((v["ai_suggested"], v["kept"], v["dropped_quote_not_found"], v["needs_human"]), (3, 1, 1, 1))
        kept = [f for f in findings if f["method"] == "ai" and f["rule_code"] == "TONE-03"][0]
        self.assertEqual((kept["start"], kept["end"]), (13, 23))
        self.assertTrue(any(f["category"] == "needs human judgement" for f in findings))

    def test_retries_once_when_rate_limited(self):
        calls = []

        class Busy(FakeResponse):
            status_code = 429

            def raise_for_status(self):
                raise RuntimeError("429 Too Many Requests")

        def flaky(*a, **k):
            calls.append(1)
            return Busy({}) if len(calls) == 1 else FakeResponse({"findings": []})
        wait, ai.RETRY_WAIT = ai.RETRY_WAIT, 0
        try:
            _, summary = scan_text("Volta Buds Air are here.", RULESET, FACTS, "Ad", today=TODAY, _post=flaky)
        finally:
            ai.RETRY_WAIT = wait
        self.assertEqual(len(calls), 2)
        self.assertEqual(summary["mode"], "exact+ai")

    def test_ai_failure_falls_back_offline(self):
        def boom(*a, **k):
            raise ConnectionError("network down")
        findings, summary = scan_text("Hurry, last chance!", RULESET, FACTS, "Ad", today=TODAY, _post=boom)
        self.assertEqual(summary["mode"], "exact+heuristic")
        self.assertIn("ConnectionError", summary["ai_error"])
        self.assertTrue(any(f["method"] == "heuristic" for f in findings))

    def test_confidential_facts_not_sent_to_ai(self):
        sent = {}

        def capture(url, json=None, **k):
            sent["body"] = json
            return FakeResponse({"findings": []})
        scan_text("Volta Buds Air are here. Write to a@b.com", RULESET, FACTS, "Email", today=TODAY, _post=capture)
        prompt = str(sent["body"])
        self.assertNotIn("March 2027", prompt)
        self.assertNotIn("a@b.com", prompt)


class CompilerTests(unittest.TestCase):
    def test_heuristic_patterns(self):
        rules = heuristic_compile('Never use "epic"; say "great" instead. Always write our app name as "Volta Connect". '
                                  'Every email must include "Unsubscribe anytime". Keep it nice where appropriate.')
        kinds = [r["kind"] for r in rules]
        self.assertEqual(kinds[:3], ["banned", "term_case", "required"])
        self.assertEqual(rules[0]["params"], {"terms": ["epic"], "replacement": "great"})
        self.assertEqual(rules[2]["params"]["content_types"], ["Email"])
        self.assertEqual(rules[3]["ambiguous"], 1)

    def test_invalid_ai_rule_becomes_human(self):
        r = _clean({"text": "Ban words", "method": "exact", "kind": "banned", "params": {}})
        self.assertEqual((r["method"], r["kind"]), ("human", "human"))


class MaskTests(unittest.TestCase):
    def test_mask_keeps_length(self):
        text = "Mail riya@volta.demo or call 98765 43210 now"
        masked, n = mask_pii(text)
        self.assertEqual((len(masked), n), (len(text), 2))
        self.assertNotIn("riya@", masked)
        self.assertEqual(find_span(masked, "now"), (len(text) - 3, len(text)))


if __name__ == "__main__":
    unittest.main()
