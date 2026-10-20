"""Phase 2: database-backed content and admin authoring."""

import os
import sqlite3
import unittest

from helpers import ServerCase


def lesson_payload(lesson, **overrides):
    body = {key: lesson[key] for key in
            ("explanation", "example", "do", "dont", "why", "mistakes", "exercise")
            if key in lesson}
    payload = {
        "title": lesson["title"],
        "minutes": lesson["minutes"],
        "summary": lesson["summary"],
        "body": body,
    }
    payload.update(overrides)
    return payload


PRACTICAL = {
    "title": "Practical assignment",
    "intro": "Apply the module to your own business. A reviewer scores each criterion from 0 to 4.",
    "criteria": [
        {"id": "clarity", "label": "Clarity", "hint": "Specific enough to act on."},
        {"id": "numbers", "label": "Numbers", "hint": "Arithmetic is correct."},
    ],
    "prompts": [
        {"id": "p1", "criterion": "clarity", "label": "Describe your plan.", "placeholder": "Be specific."},
    ],
}


class ContentAdminTests(ServerCase):
    def admin(self):
        client = self.login_admin()
        return client

    def test_lesson_edit_reaches_learner_and_creates_revision(self):
        admin = self.admin()
        learner = self.login_demo()
        status, data, _ = learner.get("/api/module/strategy")
        self.assertEqual(status, 200, data)
        original = data["module"]["lessons"][0]

        new_title = "What a business model really is (edited)"
        try:
            status, out, _ = admin.put(f"/api/admin/lessons/{original['id']}", lesson_payload(original, title=new_title))
            self.assertEqual(status, 200, out)

            status, data, _ = learner.get("/api/module/strategy")
            self.assertEqual(data["module"]["lessons"][0]["title"], new_title)

            status, revs, _ = admin.get(f"/api/admin/revisions/lesson/{original['id']}")
            self.assertEqual(status, 200)
            self.assertGreaterEqual(len(revs["revisions"]), 1)
            self.assertEqual(revs["revisions"][0]["snapshot"]["title"], new_title)
        finally:
            admin.put(f"/api/admin/lessons/{original['id']}", lesson_payload(original))

    def test_invalid_lesson_payload_is_rejected(self):
        admin = self.admin()
        status, data, _ = admin.get("/api/module/strategy")
        lesson = data["module"]["lessons"][0]
        payload = lesson_payload(lesson)
        payload["body"]["explanation"] = []
        status, out, _ = admin.put(f"/api/admin/lessons/{lesson['id']}", payload)
        self.assertEqual(status, 400)
        self.assertEqual(out.get("code"), "invalid_input")

    def test_create_draft_module_is_hidden_until_published(self):
        admin = self.admin()
        learner = self.login_demo()
        module_id = "test-operations"

        status, out, _ = admin.post("/api/admin/modules", {
            "id": module_id, "component": "operations", "title": "Operations Foundations",
        })
        if status == 409:
            admin.post(f"/api/admin/modules/{module_id}/status", {"status": "draft"})
        else:
            self.assertEqual(status, 201, out)

        status, _, _ = learner.get(f"/api/module/{module_id}")
        self.assertEqual(status, 404)

        # Not ready: no lessons, questions or practical.
        status, out, _ = admin.post(f"/api/admin/modules/{module_id}/status", {"status": "published"})
        self.assertEqual(status, 400)
        self.assertEqual(out.get("code"), "not_ready")

        # Add a lesson.
        status, out, _ = admin.post(f"/api/admin/modules/{module_id}/lessons")
        self.assertEqual(status, 201, out)
        lesson = out["lesson"]
        status, out, _ = admin.put(f"/api/admin/lessons/{lesson['id']}", {
            "title": "Find your best customer",
            "minutes": 10,
            "summary": "A narrow customer group makes every marketing decision easier.",
            "body": {
                "explanation": ["Most small businesses describe their customer as everyone."],
                "example": {"title": "A warung near an office block", "text": "Lunch demand is predictable."},
                "do": ["Name one customer group."],
                "dont": ["Do not target everyone."],
                "why": "A narrow group makes the offer measurable.",
                "mistakes": ["Confusing a demographic with a need."],
                "exercise": {"prompt": "Write your customer group in one sentence.", "steps": ["Be specific."]},
            },
        })
        self.assertEqual(status, 200, out)

        # Add 5 quiz and 3 scenario questions.
        for i in range(5):
            status, out, _ = admin.post("/api/admin/questions", {
                "component": "operations", "kind": "quiz", "topic": "Customers",
                "prompt": f"Marketing quiz question {i} with enough detail?",
                "options": ["A", "B", "C"], "correct": 1,
                "explanation": "Because B is the practical answer.",
            })
            self.assertEqual(status, 201, out)
        for i in range(3):
            status, out, _ = admin.post("/api/admin/questions", {
                "component": "operations", "kind": "scenario", "topic": "Offer",
                "prompt": f"Marketing scenario question {i} with enough detail?",
                "options": ["A", "B", "C"], "correct": 0,
                "explanation": "Because A fits the scenario.",
            })
            self.assertEqual(status, 201, out)

        status, out, _ = admin.put(f"/api/admin/modules/{module_id}", {"practical": PRACTICAL})
        self.assertEqual(status, 200, out)

        status, out, _ = admin.post(f"/api/admin/modules/{module_id}/status", {"status": "published"})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["module"]["status"], "published")

        status, data, _ = learner.get(f"/api/module/{module_id}")
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data["module"]["lessons"]), 1)

        status, boot, _ = learner.get("/api/bootstrap")
        operations = next(c for c in boot["components"] if c["id"] == "operations")
        self.assertTrue(operations["available"])

    def test_unpublish_hides_module_from_learners(self):
        admin = self.admin()
        learner = self.login_demo()
        status, out, _ = admin.get("/api/admin/modules")
        ids = [m["id"] for m in out["modules"]]
        if "test-operations" not in ids:
            self.skipTest("depends on the published draft test")
        status, _, _ = admin.post("/api/admin/modules/test-operations/status", {"status": "draft"})
        self.assertEqual(status, 200)
        status, _, _ = learner.get("/api/module/test-operations")
        self.assertEqual(status, 404)
        admin.post("/api/admin/modules/test-operations/status", {"status": "published"})

    def test_template_crud_and_download(self):
        admin = self.admin()
        learner = self.login_demo()
        payload = {
            "slug": "test-template",
            "title": "Test template",
            "description": "Used by the test suite.",
            "format": "Markdown",
            "filename": "test-template.md",
            "body": "# Test template\n\nHello.",
        }
        status, out, _ = admin.put("/api/admin/modules/strategy/templates", payload)
        self.assertEqual(status, 200, out)

        status, body, headers = learner.get("/api/templates/test-template")
        self.assertEqual(status, 200)
        self.assertIn("Hello", body)
        self.assertIn("test-template.md", headers.get("Content-Disposition", ""))

        status, out, _ = admin.delete("/api/admin/templates/test-template")
        self.assertEqual(status, 200)
        status, _, _ = learner.get("/api/templates/test-template")
        self.assertEqual(status, 404)

    def test_settings_change_writes_audit_row(self):
        admin = self.admin()
        original = {"quiz_pass": 80, "scenario_pass": 70, "rubric_min": 3, "rubric_floor": 2}
        status, out, _ = admin.put("/api/admin/settings", {**original, "quiz_pass": 81})
        self.assertEqual(status, 200, out)
        admin.put("/api/admin/settings", original)

        db = os.path.join(self.tmpdir, "bizready.db")
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT detail_json FROM audit_log WHERE action = 'settings.update'"
        ).fetchall()
        conn.close()
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(any('"81"' in row["detail_json"] for row in rows))

    def test_module_slug_validation(self):
        admin = self.admin()
        status, out, _ = admin.post("/api/admin/modules", {
            "id": "Bad ID!", "component": "operations", "title": "Nope",
        })
        self.assertEqual(status, 400)

    def test_quiz_question_is_linked_to_module(self):
        admin = self.admin()
        status, out, _ = admin.post("/api/admin/questions", {
            "component": "strategy", "kind": "quiz", "topic": "Contribution",
            "prompt": "Which number pays for fixed costs and profit?",
            "options": ["Revenue", "Contribution", "Gross sales"], "correct": 1,
            "explanation": "Contribution is what remains after direct costs.",
        })
        self.assertEqual(status, 201, out)
        db = os.path.join(self.tmpdir, "bizready.db")
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT module_id FROM questions WHERE id = ?", (out["id"],)).fetchone()
        conn.close()
        self.assertEqual(row["module_id"], "strategy")


if __name__ == "__main__":
    unittest.main()
