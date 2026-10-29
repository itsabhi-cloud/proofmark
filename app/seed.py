"""Demo workspace for a fictional brand, Volta Audio.

Everything here is invented for the hackathon demo. No real company data.
"""
import json

from werkzeug.security import generate_password_hash

from .db import log_event, now_iso
from .services import add_version, create_draft, insert_rule, run_scan

DEMO_PASSWORD = "demo1234"

USERS = [
    ("Riya Sharma", "riya@volta.demo", "creator", "In-house marketing"),
    ("Kabir Mehta", "kabir@agency.demo", "creator", "Agency: Northwind"),
    ("Arjun Rao", "arjun@volta.demo", "reviewer", "Brand review"),
    ("Meera Iyer", "meera@volta.demo", "owner", "Brand office"),
    ("Dev Patel", "dev@volta.demo", "viewer", "Leadership"),
]

PRESSURE = ["hurry", "act now", "last chance", "don't miss out", "before it's gone", "only today", "limited time only", "grab it now"]
SLANG = ["lit", "bro", "insane", "crazy good", "OP", "fire"]

RULES = [
    dict(code="TERM-01", category="terminology", method="exact", kind="term_case", severity="high",
         text='Always write the brand name as "Volta Audio".',
         params={"canonical": "Volta Audio", "variants": ["VoltaAudio", "Volta-Audio"]}),
    dict(code="TERM-02", category="terminology", method="exact", kind="term_case", severity="medium",
         text='Write the product name as "Volta Buds Air".', params={"canonical": "Volta Buds Air"}),
    dict(code="TERM-03", category="terminology", method="exact", kind="banned", severity="medium",
         text='Never use "cheap"; say "affordable" instead.',
         params={"terms": ["cheap", "cheaply"], "replacement": "affordable"}),
    dict(code="TERM-04", category="terminology", method="exact", kind="banned", severity="high",
         text='"Volta Pods" was retired in 2025. Refer to the current product, "Volta Buds Air".',
         params={"terms": ["Volta Pods"], "replacement": "Volta Buds Air", "reason": '"Volta Pods" is a retired product name.'}),
    dict(code="TERM-05", category="terminology", method="exact", kind="banned", severity="low",
         text='Say "earbuds", not "earphones".', params={"terms": ["earphones"], "replacement": "earbuds"}),
    dict(code="CLM-01", category="claims", method="exact", kind="unbacked_claims", severity="high",
         text="Superlatives and guarantees (best, fastest, #1, guaranteed) need an approved fact.", params={}),
    dict(code="CLM-02", category="claims", method="exact", kind="numeric_claims", severity="high",
         text="Every number in a claim (hours, %, price, warranty) must match an approved, unexpired fact.", params={}),
    dict(code="CLM-03", category="claims", method="exact", kind="banned", severity="high",
         text='Volta Buds Air are splash-resistant (IPX4), not waterproof. Never say "waterproof".',
         params={"terms": ["waterproof", "water-proof"], "replacement": "splash-resistant",
                 "reason": '"Waterproof" overstates the IPX4 rating.'}),
    dict(code="LEGAL-01", category="legal", method="exact", kind="required", severity="high",
         text='Any ad or social post that mentions an offer or discount must include "T&C apply".',
         params={"phrase": "T&C apply", "content_types": ["Social post", "Ad"],
                 "when_any": ["off", "offer", "discount", "sale", "cashback", "deal"]}),
    dict(code="TONE-01", category="tone", method="ai", kind="tone", severity="medium",
         text="Sound calm, confident and helpful. Never use fear, pressure or false urgency to sell.",
         params={"pressure_words": PRESSURE,
                 "replacements": {"hurry": "", "act now": "order today", "grab it now": "order today",
                                  "last chance": "", "don't miss out": "", "only today": "today"}}),
    dict(code="TONE-02", category="tone", method="exact", kind="pattern", severity="low",
         text="Use at most one exclamation mark at a time.",
         params={"regex": "!{2,}", "message": "Use at most one exclamation mark at a time.", "replacement": "!"}),
    dict(code="TONE-03", category="tone", method="ai", kind="tone", severity="low",
         text="Speak to listeners as \"you\" in plain English; avoid slang such as \"lit\", \"bro\" or \"insane\".",
         params={"slang_words": SLANG}),
    dict(code="MSG-01", category="messaging", method="ai", kind="messaging", severity="low",
         text='Product posts should connect to our core message: "Sound for everyday life".', params={}),
    dict(code="A11Y-01", category="accessibility", method="exact", kind="link_text", severity="low",
         text='Avoid vague link text such as "click here".', params={}),
    dict(code="A11Y-02", category="accessibility", method="exact", kind="alt_text", severity="medium",
         text="Images in web pages and emails need alt text.", params={}),
    dict(code="A11Y-03", category="accessibility", method="exact", kind="readability", severity="low",
         text="Keep copy easy to read: sentences under 25 words and a reading-ease score of 50 or more.",
         params={"max_sentence_words": 25, "min_flesch": 50}),
    dict(code="A11Y-04", category="accessibility", method="exact", kind="all_caps", severity="low",
         text="Avoid runs of three or more ALL-CAPS words.", params={}),
    dict(code="VIS-01", category="visual", method="human", kind="human", severity="medium",
         text="Product photos show the real colours: Midnight, Sand or Ocean.", params={}),
    dict(code="VIS-02", category="visual", method="human", kind="human", severity="medium",
         text="The logo is never stretched, recoloured or placed on a busy background.", params={}),
]

FACTS = [
    dict(code="FACT-01", statement="Volta Buds Air give up to 10 hours of playback per charge.",
         keywords=["battery", "battery life", "playback", "per charge", "single charge", "listening"],
         value=10, unit="hour", comparison="max", source="Spec sheet v3", valid_until="2027-03-31"),
    dict(code="FACT-02", statement="With the charging case, total playback is up to 30 hours.",
         keywords=["case", "charging case", "in total", "total"],
         value=30, unit="hour", comparison="max", source="Spec sheet v3", valid_until="2027-03-31"),
    dict(code="FACT-03", statement="Launch price of Volta Buds Air is ₹2,999.",
         keywords=["price", "priced", "costs", "cost", "for just", "at just", "only", "launch"],
         value=2999, unit="INR", comparison="exact", source="Pricing sheet, Oct 2026", valid_until="2026-12-31"),
    dict(code="FACT-04", statement="10 minutes of charging gives 2 hours of playback.",
         keywords=["charging", "quick charge", "fast charge", "minutes of charging", "charge for"],
         value=10, unit="minute", comparison="exact", source="Spec sheet v3", valid_until="2027-03-31"),
    dict(code="FACT-05", statement="Volta Buds Air carry a 1-year warranty.",
         keywords=["warranty", "guarantee"], value=1, unit="year", comparison="exact",
         source="Warranty policy 2026", valid_until="2027-12-31"),
    dict(code="FACT-06", statement="Volta Buds Air use 12 mm drivers.", keywords=["driver", "drivers"],
         value=12, unit="mm", comparison="exact", source="Spec sheet v3", valid_until="2027-03-31"),
    dict(code="FACT-07", statement="Diwali 2025 offer: 20% off.",
         keywords=["diwali", "off", "discount", "festive"], value=20, unit="percent", comparison="exact",
         source="Campaign brief, Oct 2025", valid_until="2025-11-15"),
    dict(code="FACT-08", statement="Volta Buds Air are rated IPX4 for sweat and splash resistance.",
         keywords=["ipx4", "splash", "sweat"], value=None, unit=None, comparison="exact",
         source="Certification report", valid_until=None),
    dict(code="FACT-09", statement="Volta Buds Air 2 launch planned for March 2027.",
         keywords=["Buds Air 2", "next-gen buds", "Project Lyra"], value=None, unit=None, comparison="exact",
         source="Product roadmap (confidential)", valid_until=None, confidential=1),
]

SAMPLE_GUIDE_UPDATE = """Volta Audio brand guidelines, v2 update

Our voice is warm, clear and never pushy.
Never use the words "world-class" or "revolutionary"; say "carefully designed" instead.
Always write our app name as "Volta Connect".
Every email must include "Unsubscribe anytime".
Keep captions short and engaging where appropriate.
Photos should feel premium and modern.
Highlight our core message, Sound for everyday life, in every launch post.
Use emojis sometimes, but not too many."""

SAMPLE_DRAFTS = [
    {
        "title": "Launch post with problems",
        "content_type": "Social post",
        "goal": "Drive pre-orders for Volta Buds Air",
        "body": ("Hurry!! Volta audio's cheap new earbuds give you 24 hours of battery, the best in India. "
                 "They're totally waterproof, so take them anywhere. Grab it now for just ₹2,499 with 20% off. "
                 "Click here to pre-order before it's gone."),
    },
    {
        "title": "Product page intro",
        "content_type": "Product page",
        "goal": "Explain the main features to first-time buyers",
        "body": ("Meet Volta Buds Air from Volta Audio. Up to 10 hours of playback per charge, and up to 30 hours in "
                 "total with the charging case. Ten minutes of charging gives you two hours of music. "
                 "IPX4 splash resistance means rain and sweat are fine. Sound for everyday life, at ₹2,999."),
    },
    {
        "title": "Email with an image and a leak",
        "content_type": "Email",
        "goal": "Invite existing customers to the community event",
        "body": ("Hi there,\n\nYou're invited to the VOLTA LISTENING NIGHT in Bengaluru! Our team will share a sneak "
                 "peek of the Buds Air 2 and answer your questions.\n\n![](https://example.com/event.jpg)\n\n"
                 "Click here to save your seat. Questions? Write to events@volta.demo or call 98765 43210."),
    },
]


def seed(conn):
    conn.execute("INSERT INTO brand (name, tagline, description, palette) VALUES (?,?,?,?)",
                 ("Volta Audio", "Sound for everyday life",
                  "Fictional consumer-audio brand used for the Proofmark demo.",
                  json.dumps(["#1F2A44", "#E9E4D8", "#2F7F86"])))
    ids = {}
    for name, email, role, team in USERS:
        cur = conn.execute("INSERT INTO users (name, email, pw_hash, role, team) VALUES (?,?,?,?,?)",
                           (name, email, generate_password_hash(DEMO_PASSWORD), role, team))
        ids[email.split("@")[0]] = cur.lastrowid
    for r in RULES:
        insert_rule(conn, r, status="approved", source="Brand guidelines v1")
    for f in FACTS:
        conn.execute("""INSERT INTO facts (code, statement, keywords, value, unit, comparison, source, valid_until,
                        confidential, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (f["code"], f["statement"], json.dumps(f["keywords"]), f["value"], f["unit"], f["comparison"],
                      f["source"], f["valid_until"], f.get("confidential", 0), now_iso()))
    # one proposed, ambiguous rule so the owner sees the approval step
    insert_rule(conn, dict(category="tone", method="ai", kind="tone", severity="low",
                           text="Captions should sound fun where appropriate.", params={},
                           ambiguous=1, ambiguity_reason='Uses vague wording ("where appropriate"): a writer cannot tell exactly what passes.'),
                status="proposed", source="Compiler (demo)")

    _history(conn, ids)
    conn.commit()


def _history(conn, ids):
    """Past drafts so the review queue, history and insights are not empty."""
    # 1. Agency post waiting for review (scanned, many findings)
    d1 = create_draft(conn, ids["kabir"], "Diwali-style launch teaser", "Social post",
                      "Build excitement and drive pre-orders",
                      "Last chance!! Volta Pods are back and better. The fastest earbuds ever, now 20% off. "
                      "This deal is insane, bro.")
    run_scan(conn, d1, ids["kabir"], use_ai=False)
    conn.execute("UPDATE drafts SET status='in_review' WHERE id=?", (d1,))
    log_event(conn, "submitted for review", ids["kabir"], d1)

    # 2. Approved email with two versions and a dismissed finding
    d2 = create_draft(conn, ids["riya"], "Welcome email for new owners", "Email", "Help new owners set up their earbuds",
                      "Welcome to Volta Audio! Your Volta Buds Air give you up to 10 hours of listening. "
                      "Pair them in seconds with the app. Click here to read the setup guide. This is lit.")
    run_scan(conn, d2, ids["riya"], use_ai=False)
    add_version(conn, d2,
                "Welcome to Volta Audio! Your Volta Buds Air give you up to 10 hours of listening. "
                "Pair them in seconds with the app. Read the setup guide to get started.", ids["riya"], "Applied 2 fixes")
    run_scan(conn, d2, ids["riya"], use_ai=False)
    conn.execute("UPDATE drafts SET status='approved' WHERE id=?", (d2,))
    conn.execute("UPDATE versions SET locked=1 WHERE draft_id=?", (d2,))
    log_event(conn, "submitted for review", ids["riya"], d2)
    log_event(conn, "approved", ids["arjun"], d2, "Clear and on-brand.")

    # 3. Two drafts where reviewers overrode TONE-03 as unclear: feeds the insights
    for title, body in [
        ("Gym playlist caption", "Volta Buds Air keep up with your workout. Our playlist is fire this week."),
        ("Weekend caption", "Rainy weekend? Volta Buds Air are splash-resistant. This sound is fire."),
    ]:
        d = create_draft(conn, ids["riya"], title, "Social post", "Engage followers", body)
        scan_id = run_scan(conn, d, ids["riya"], use_ai=False)
        conn.execute("""UPDATE findings SET status='dismissed', dismiss_reason='Rule unclear',
                        dismiss_note='Is "fire" slang? The rule does not say.', decided_by=?
                        WHERE scan_id=? AND rule_code='TONE-03'""", (ids["arjun"], scan_id))
        conn.execute("UPDATE drafts SET status='approved' WHERE id=?", (d,))
        log_event(conn, "dismissed finding", ids["arjun"], d, "TONE-03: Rule unclear")
        log_event(conn, "approved", ids["arjun"], d)
