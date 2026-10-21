"""Phase 5: module-scoped assessments, remediation and module-aware review."""

import unittest

from helpers import Client, ServerCase

MODULE_ID = "test-marketing"


class Phase5AssessmentTests(ServerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = Client(cls.base)
        cls.admin.bootstrap()
        status, body, _ = cls.admin.login("admin@futurepreneur.app", "Admin1234!")
        if status != 200:
            raise RuntimeError(f"admin login failed: {status} {body}")
        cls._build_module()

    @classmethod
    def _build_module(cls):
        status, body, _ = cls.admin.post("/api/admin/modules", {
            "id": MODULE_ID, "component": "marketing", "title": "Test Marketing Module",
        })
        if status not in (201, 409):
            raise RuntimeError(f"module create failed: {status} {body}")
        status, body, _ = cls.admin.post(f"/api/admin/modules/{MODULE_ID}/lessons")
        if status != 201:
            raise RuntimeError(f"lesson create failed: {status} {body}")
        lesson = body["lesson"]
        status, body, _ = cls.admin.put(f"/api/admin/lessons/{lesson['id']}", {
            "title": "Find the customer worth serving",
            "minutes": 8,
            "summary": "A narrow customer group makes every marketing decision cheaper.",
            "body": {
                "explanation": ["Specific beats broad when your budget is small."],
                "example": {"title": "A lunch stall", "text": "Office workers within 1km buy at 12pm."},
                "do": ["Name one group with a shared need."],
                "dont": ["Do not target everyone."],
                "why": "A clear group makes the offer and channel measurable.",
                "mistakes": ["Confusing a demographic with a need."],
                "exercise": {"prompt": "Describe your best customer group.", "steps": ["Name who, where and when."]},
            },
        })
        if status != 200:
            raise RuntimeError(f"lesson update failed: {status} {body}")

        # 5 quiz + 3 scenario, all with correct index 1.
        for i in range(5):
            status, body, _ = cls.admin.post("/api/admin/questions", {
                "component": "marketing", "kind": "quiz", "topic": f"Customer {i}",
                "prompt": f"Scoped marketing quiz question {i} with enough detail?",
                "options": ["Wrong one", "Right one", "Wrong two"], "correct": 1,
                "explanation": "The second option is the practical answer.",
            })
            if status != 201:
                raise RuntimeError(f"quiz create failed: {status} {body}")
        for i in range(3):
            status, body, _ = cls.admin.post("/api/admin/questions", {
                "component": "marketing", "kind": "scenario", "topic": f"Scenario {i}",
                "prompt": f"Scoped marketing scenario question {i} with enough detail?",
                "options": ["Wrong one", "Right one", "Wrong two"], "correct": 1,
                "explanation": "The second option is the sound response.",
            })
            if status != 201:
                raise RuntimeError(f"scenario create failed: {status} {body}")

        criteria = [
            {"id": "customer_clarity", "label": "Customer clarity", "hint": "One group, specific enough to contact."},
            {"id": "offer_strength", "label": "Offer strength", "hint": "An outcome, a price and proof."},
            {"id": "numbers", "label": "Numbers", "hint": "Cost per enquiry and per order."},
            {"id": "execution", "label": "Execution", "hint": "A dated test with a stop rule."},
        ]
        prompts = [
            {"id": "p1", "criterion": "customer_clarity", "label": "Who is your customer?", "placeholder": "Specific."},
            {"id": "p2", "criterion": "offer_strength", "label": "What is your offer?", "placeholder": "Outcome, price, proof."},
            {"id": "p3", "criterion": "numbers", "label": "What are the numbers?", "placeholder": "Cost per enquiry."},
            {"id": "p4", "criterion": "execution", "label": "What will you test?", "placeholder": "A 14-day test."},
        ]
        status, body, _ = cls.admin.put(f"/api/admin/modules/{MODULE_ID}", {
            "practical": {"title": "A 14-day marketing test", "intro": "Use your own business.", "criteria": criteria, "prompts": prompts},
        })
        if status != 200:
            raise RuntimeError(f"practical save failed: {status} {body}")
        status, body, _ = cls.admin.post(f"/api/admin/modules/{MODULE_ID}/status", {"status": "published"})
        if status != 200:
            raise RuntimeError(f"publish failed: {status} {body}")

    # -- helpers ---------------------------------------------------------
    def marketing_answers(self, client, correct_count=5):
        status, body, _ = client.get(f"/api/module/{MODULE_ID}/assessment/quiz/questions")
        self.assertEqual(status, 200, body)
        ids = [q["id"] for q in body["questions"]]
        return {qid: (1 if i < correct_count else 0) for i, qid in enumerate(ids)}

    def scenario_answers(self, client, correct_count=3):
        status, body, _ = client.get(f"/api/module/{MODULE_ID}/assessment/scenario/questions")
        self.assertEqual(status, 200, body)
        ids = [q["id"] for q in body["questions"]]
        return {qid: (1 if i < correct_count else 0) for i, qid in enumerate(ids)}

    def complete_module_assessments(self, client):
        quiz = self.marketing_answers(client, 5)
        status, out, _ = client.post(f"/api/module/{MODULE_ID}/assessment/quiz/submit", {"answers": quiz})
        self.assertEqual(status, 200, out)
        self.assertTrue(out["passed"])
        scenario = self.scenario_answers(client, 3)
        status, out, _ = client.post(f"/api/module/{MODULE_ID}/assessment/scenario/submit", {"answers": scenario})
        self.assertEqual(status, 200, out)
        self.assertTrue(out["passed"])
        status, practical, _ = client.get(f"/api/module/{MODULE_ID}/practical")
        self.assertEqual(status, 200, practical)
        responses = {p["id"]: f"Detailed answer for {p['id']} with a real number and a dated next step." for p in practical["practical"]["prompts"]}
        status, submitted, _ = client.post(f"/api/module/{MODULE_ID}/practical/submit", {"responses": responses})
        self.assertEqual(status, 201, submitted)
        self.assertEqual(submitted["submission"]["status"], "pending")
        return submitted["submission"]["id"], practical

    # -- tests -----------------------------------------------------------
    def test_questions_are_scoped_and_answers_hidden(self):
        learner, _ = self.register_fresh("scope")
        status, body, _ = learner.get(f"/api/module/{MODULE_ID}/assessment/quiz/questions")
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body["questions"]), 5)
        self.assertTrue(all("correct" not in q and "explanation" not in q for q in body["questions"]))
        status, strategy, _ = learner.get("/api/assessment/quiz/questions")
        self.assertEqual(status, 200)
        self.assertEqual(len(strategy["questions"]), 10)
        self.assertNotEqual({q["id"] for q in body["questions"]}, {q["id"] for q in strategy["questions"]})

    def test_scoped_scoring_and_history_do_not_leak(self):
        learner, _ = self.register_fresh("score")
        answers = self.marketing_answers(learner, 5)
        status, out, _ = learner.post(f"/api/module/{MODULE_ID}/assessment/quiz/submit", {"answers": answers})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["score"], 100)
        self.assertTrue(out["passed"])
        self.assertEqual(out["module"]["id"], MODULE_ID)

        status, hist, _ = learner.get(f"/api/module/{MODULE_ID}/assessment/quiz/questions")
        self.assertEqual(len(hist["history"]), 1)
        self.assertTrue(hist["history"][0]["passed"])

        status, strategy_hist, _ = learner.get("/api/assessment/quiz/questions")
        self.assertEqual(strategy_hist["history"], [], "a marketing attempt must not appear in strategy history")

        status, progress, _ = learner.get("/api/progress")
        self.assertEqual(progress["modules_passed"], 0)
        marketing = next(m for m in progress["modules"] if m["id"] == MODULE_ID)
        self.assertTrue(marketing["quiz_passed"])
        self.assertFalse(marketing["scenario_passed"])
        self.assertFalse(marketing["passed"])

    def test_failed_attempt_lists_exact_lessons(self):
        learner, _ = self.register_fresh("remedy")
        answers = self.marketing_answers(learner, 0)
        status, out, _ = learner.post(f"/api/module/{MODULE_ID}/assessment/quiz/submit", {"answers": answers})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["score"], 0)
        self.assertTrue(out["remediation"], "wrong answers must point at lessons")
        lesson = out["remediation"][0]
        self.assertIn("id", lesson)
        self.assertIn("title", lesson)
        self.assertTrue(all(w["lesson"] for w in out["wrong"]))

    def test_practical_is_module_specific_and_review_uses_its_rubric(self):
        learner, _ = self.register_fresh("practical")
        sub_id, practical = self.complete_module_assessments(learner)
        self.assertEqual(practical["module"]["id"], MODULE_ID)

        status, progress, _ = learner.get("/api/progress")
        marketing = next(m for m in progress["modules"] if m["id"] == MODULE_ID)
        self.assertFalse(marketing["passed"], "unreviewed practical cannot pass")
        self.assertEqual(marketing["practical"]["status"], "pending")

        admin = self.login_admin()
        status, queue, _ = admin.get("/api/admin/submissions")
        self.assertEqual(status, 200)
        row = next(s for s in queue["submissions"] if s["id"] == sub_id)
        self.assertEqual(row["module_id"], MODULE_ID)
        self.assertEqual(len(row["criteria"]), 4)
        self.assertEqual(len(row["prompts"]), 4)
        self.assertIn("customer_clarity", [c["id"] for c in row["criteria"]])

        # A strategy criterion is not accepted for this module.
        status, bad, _ = admin.post(f"/api/admin/submissions/{sub_id}/review", {
            "scores": {"customer_clarity": 3, "offer_strength": 3, "numbers": 3, "execution": 3, "differentiation": 3},
            "note": "wrong rubric",
        })
        self.assertEqual(status, 400)

        status, review, _ = admin.post(f"/api/admin/submissions/{sub_id}/review", {
            "scores": {"customer_clarity": 3, "offer_strength": 3, "numbers": 3, "execution": 3},
            "note": "Meets the marketing standard.",
        })
        self.assertEqual(status, 200, review)
        self.assertTrue(review["passed"])

        status, progress, _ = learner.get("/api/progress")
        marketing = next(m for m in progress["modules"] if m["id"] == MODULE_ID)
        self.assertTrue(marketing["passed"])
        self.assertEqual(progress["modules_passed"], 1)
        self.assertEqual(progress["mastery"]["level"], "Structured")

        status, strategy, _ = learner.get("/api/progress")
        strategy_module = next(m for m in strategy["modules"] if m["id"] == "strategy")
        self.assertFalse(strategy_module["passed"], "marketing pass must not pass strategy")

    def test_inactive_questions_never_appear(self):
        admin = self.login_admin()
        status, body, _ = admin.post("/api/admin/questions", {
            "component": "marketing", "kind": "quiz", "topic": "Hidden",
            "prompt": "This inactive question must never appear in an assessment?",
            "options": ["A", "B"], "correct": 0,
            "explanation": "It is inactive.", "active": False,
        })
        self.assertEqual(status, 201, body)
        learner, _ = self.register_fresh("inactive")
        status, out, _ = learner.get(f"/api/module/{MODULE_ID}/assessment/quiz/questions")
        self.assertEqual(len(out["questions"]), 5)
        self.assertNotIn("This inactive question must never appear in an assessment?",
                         [q["prompt"] for q in out["questions"]])


if __name__ == "__main__":
    unittest.main()
