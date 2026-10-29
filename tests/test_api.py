"""End-to-end API tests: the full creator -> reviewer journey and role checks."""
import os
import tempfile
import unittest

os.environ["AI_DISABLED"] = "1"
from app import create_app  # noqa: E402
from app.seed import SAMPLE_DRAFTS  # noqa: E402


class ApiTests(unittest.TestCase):
    def setUp(self):
        os.environ["AI_DISABLED"] = "1"
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DB_PATH": os.path.join(self.tmp, "t.db"), "TESTING": True})

    def client_as(self, email):
        c = self.app.test_client()
        r = c.post("/api/auth/login", json={"demo_email": email})
        self.assertEqual(r.status_code, 200)
        return c

    def test_full_workflow(self):
        riya = self.client_as("riya@volta.demo")
        draft_id = riya.post("/api/drafts", json=SAMPLE_DRAFTS[0]).json["id"]
        d = riya.get(f"/api/drafts/{draft_id}").json
        issues = [f for f in d["findings"] if f["severity"] != "info"]
        self.assertGreaterEqual(len(issues), 10)
        fixable = [f["id"] for f in issues if f["suggestion"] is not None][:4]
        r = riya.post(f"/api/drafts/{draft_id}/apply-fixes", json={"accept": fixable})
        self.assertEqual(r.json["version"], 2)
        rw = riya.post(f"/api/drafts/{draft_id}/rewrite").json
        self.assertEqual(rw["mode"], "offline")
        riya.post(f"/api/drafts/{draft_id}/versions", json={"body": rw["text"]})
        self.assertEqual(riya.post(f"/api/drafts/{draft_id}/submit", json={}).status_code, 200)
        # locked while in review
        self.assertEqual(riya.post(f"/api/drafts/{draft_id}/versions", json={"body": "x"}).status_code, 409)

        arjun = self.client_as("arjun@volta.demo")
        d = arjun.get(f"/api/drafts/{draft_id}").json
        self.assertTrue(d["permissions"]["review"])
        open_issue = next(f for f in d["findings"] if f["status"] == "open" and f["severity"] != "info")
        self.assertEqual(arjun.post(f"/api/findings/{open_issue['id']}/dismiss", json={"reason": "nope"}).status_code, 400)
        self.assertEqual(arjun.post(f"/api/findings/{open_issue['id']}/dismiss",
                                    json={"reason": "Approved exception"}).status_code, 200)
        # approve blocked until human checks are confirmed
        self.assertEqual(arjun.post(f"/api/drafts/{draft_id}/review", json={"decision": "approve"}).status_code, 400)
        r = arjun.post(f"/api/drafts/{draft_id}/review",
                       json={"decision": "approve", "checks": {"VIS-01": True, "VIS-02": True}})
        self.assertEqual(r.status_code, 200)
        d = arjun.get(f"/api/drafts/{draft_id}").json
        self.assertEqual(d["draft"]["status"], "approved")
        self.assertEqual(d["current"]["locked"], 1)
        actions = [e["action"] for e in d["events"]]
        for a in ("created draft", "applied fixes", "submitted for review", "dismissed finding", "approved"):
            self.assertIn(a, actions)

    def test_request_changes_needs_comment_and_reopens(self):
        kabir_draft = 1  # seeded, in review
        arjun = self.client_as("arjun@volta.demo")
        self.assertEqual(arjun.post(f"/api/drafts/{kabir_draft}/review",
                                    json={"decision": "request_changes"}).status_code, 400)
        arjun.post(f"/api/drafts/{kabir_draft}/review", json={"decision": "request_changes", "comment": "Fix the claims."})
        kabir = self.client_as("kabir@agency.demo")
        self.assertTrue(kabir.get(f"/api/drafts/{kabir_draft}").json["permissions"]["edit"])

    def test_role_permissions(self):
        dev = self.client_as("dev@volta.demo")
        self.assertEqual(dev.post("/api/drafts", json=SAMPLE_DRAFTS[1]).status_code, 403)
        self.assertEqual(dev.post("/api/rules/compile", json={"text": "x"}).status_code, 403)
        riya = self.client_as("riya@volta.demo")
        self.assertEqual(riya.get("/api/drafts/1").status_code, 403)  # Kabir's draft
        self.assertEqual(riya.post("/api/drafts/1/review", json={"decision": "approve"}).status_code, 403)
        facts = riya.get("/api/facts").json["facts"]
        conf = [f for f in facts if f["confidential"]][0]
        self.assertNotIn("March", conf["statement"])
        anon = self.app.test_client()
        self.assertEqual(anon.get("/api/drafts").status_code, 401)

    def test_owner_compiles_and_approves_rules(self):
        meera = self.client_as("meera@volta.demo")
        r = meera.post("/api/rules/compile", json={"text": 'Never use "epic". Keep it nice where appropriate.'}).json
        self.assertEqual((r["count"], r["ambiguous"]), (2, 1))
        rules = meera.get("/api/rules").json["rules"]
        new = next(x for x in rules if x["code"] == r["codes"][0])
        self.assertEqual(new["status"], "proposed")
        meera.patch(f"/api/rules/{new['id']}", json={"status": "approved"})
        riya = self.client_as("riya@volta.demo")
        d = riya.post("/api/drafts", json={"title": "t", "content_type": "Blog post", "body": "An epic launch."}).json
        found = riya.get(f"/api/drafts/{d['id']}").json["findings"]
        self.assertIn(new["code"], {f["rule_code"] for f in found})

    def test_upload_rejects_bad_type(self):
        import io
        riya = self.client_as("riya@volta.demo")
        r = riya.post("/api/upload", data={"file": (io.BytesIO(b"x"), "a.exe")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        r = riya.post("/api/upload", data={"file": (io.BytesIO(b"Hello cheap world"), "a.txt")},
                      content_type="multipart/form-data")
        self.assertEqual(r.json["text"], "Hello cheap world")

    def test_insights(self):
        meera = self.client_as("meera@volta.demo")
        i = meera.get("/api/insights").json
        self.assertTrue(any(o["code"] == "TONE-03" and o["likely_unclear"] for o in i["most_overridden"]))


if __name__ == "__main__":
    unittest.main()
