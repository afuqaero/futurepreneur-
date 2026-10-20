"""End-to-end workflow: check-up, lessons, assessments, practical, progress, coach."""

import unittest

from helpers import ServerCase

PROFILE = {
    "business_name": "Test Kitchen",
    "sector": "Food & beverage",
    "stage": "Growing",
    "team_size": "2–5",
    "revenue_band": "RM20,000–RM50,000",
    "years": "3–5 years",
    "main_challenge": "Margins are thin and I do not know which menu items actually make money.",
}


class WorkflowTests(ServerCase):
    def test_checkup_scores_and_seeds_plan(self):
        client, _ = self.register_fresh("checkup")
        status, out, _ = client.put("/api/profile", PROFILE)
        self.assertEqual(status, 200, out)

        status, checkup, _ = client.get("/api/checkup")
        self.assertEqual(status, 200)
        self.assertEqual(len(checkup["questions"]), 24)
        self.assertEqual(checkup["profile"]["business_name"], "Test Kitchen")

        answers, total = self.answers_from_db("diagnostic", 24)
        status, result, _ = client.post("/api/checkup/submit", {"answers": answers})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["score"], 100)
        self.assertEqual(len(result["strengths"]), 3)
        self.assertEqual(len(result["priorities"]), 0, "perfect scores leave no gaps")
        self.assertEqual(len(result["progress"]["plan"]), 3)
        self.assertEqual(result["progress"]["mastery"]["level"], "Beginner")

    def test_checkup_rejects_missing_answers(self):
        client, _ = self.register_fresh("checkup-bad")
        status, out, _ = client.post("/api/checkup/submit", {"answers": []})
        self.assertEqual(status, 400)

    def test_full_module_journey_to_structured(self):
        client, _ = self.register_fresh("journey")
        client.put("/api/profile", PROFILE)

        # Lessons
        for lesson in ("l1", "l2", "l3", "l4"):
            status, out, _ = client.post(f"/api/module/strategy/lesson/{lesson}/complete")
            self.assertEqual(status, 200, out)
        status, module, _ = client.get("/api/module/strategy")
        self.assertEqual(status, 200)
        self.assertEqual(module["state"]["lessons_done"], 4)
        self.assertEqual(len(module["module"]["lessons"]), 4)
        self.assertTrue(module["module"]["lessons"][0]["do"])

        # Quiz: 8/10 = 80 -> exactly at the pass mark
        answers, total = self.answers_from_db("quiz", 8)
        self.assertEqual(total, 10)
        status, quiz, _ = client.post("/api/assessment/quiz/submit", {"answers": answers})
        self.assertEqual(status, 200, quiz)
        self.assertEqual(quiz["score"], 80)
        self.assertTrue(quiz["passed"])

        # Scenario: 4/5 = 80 -> above 70
        answers, total = self.answers_from_db("scenario", 4)
        self.assertEqual(total, 5)
        status, scenario, _ = client.post("/api/assessment/scenario/submit", {"answers": answers})
        self.assertEqual(scenario["score"], 80)
        self.assertTrue(scenario["passed"])

        # Practical: pending until reviewed
        status, practical, _ = client.get("/api/practical")
        self.assertEqual(status, 200)
        responses = {p["id"]: f"My detailed answer for {p['id']} with real numbers and a next step." for p in practical["practical"]["prompts"]}
        status, submitted, _ = client.post("/api/practical/submit", {"responses": responses})
        self.assertEqual(status, 201, submitted)
        self.assertEqual(submitted["submission"]["status"], "pending")

        status, progress, _ = client.get("/api/progress")
        self.assertFalse(progress["module"]["passed"])
        self.assertEqual(progress["module"]["percent"], 75)

        # Reviewer gives one criterion below the floor -> fail despite 3.25 average
        admin = self.login_admin()
        sub_id = submitted["submission"]["id"]
        crit = [c["id"] for c in practical["practical"]["criteria"]]
        status, review, _ = admin.post(
            f"/api/admin/submissions/{sub_id}/review",
            {"scores": {crit[0]: 4, crit[1]: 4, crit[2]: 4, crit[3]: 1}, "note": "One criterion below the floor."},
        )
        self.assertEqual(status, 200, review)
        self.assertFalse(review["passed"])
        self.assertAlmostEqual(review["average"], 3.25)

        status, progress, _ = client.get("/api/progress")
        self.assertFalse(progress["module"]["passed"])
        self.assertEqual(progress["mastery"]["level"], "Developing")

        # Reviewer passes it
        status, review, _ = admin.post(
            f"/api/admin/submissions/{sub_id}/review",
            {"scores": {c: 3 for c in crit}, "note": "Meets the standard."},
        )
        self.assertTrue(review["passed"])

        status, progress, _ = client.get("/api/progress")
        self.assertTrue(progress["module"]["passed"])
        self.assertEqual(progress["mastery"]["level"], "Structured")
        self.assertEqual(progress["components"][0]["mastery"], "Structured")
        self.assertEqual(progress["overall_percent"], 75)

    def test_quiz_failure_lists_topics_and_retake_is_recorded(self):
        client, _ = self.register_fresh("quizfail")
        answers, _ = self.answers_from_db("quiz", 7)
        status, out, _ = client.post("/api/assessment/quiz/submit", {"answers": answers})
        self.assertEqual(out["score"], 70)
        self.assertFalse(out["passed"])
        self.assertEqual(len(out["wrong"]), 3)
        self.assertTrue(all(w["explanation"] for w in out["wrong"]))

        answers, _ = self.answers_from_db("quiz", 8)
        client.post("/api/assessment/quiz/submit", {"answers": answers})
        status, history, _ = client.get("/api/assessment/quiz/questions")
        self.assertEqual(len(history["history"]), 2)
        self.assertTrue(history["history"][0]["passed"])

    def test_pass_mark_change_applies_to_next_attempt(self):
        admin = self.login_admin()
        original = {"quiz_pass": 80, "scenario_pass": 70, "rubric_min": 3, "rubric_floor": 2}
        try:
            status, out, _ = admin.put("/api/admin/settings", {**original, "quiz_pass": 75, "scenario_pass": 70})
            self.assertEqual(status, 200, out)
            client, _ = self.register_fresh("mark")
            answers, _ = self.answers_from_db("quiz", 7)
            status, out, _ = client.post("/api/assessment/quiz/submit", {"answers": answers})
            self.assertEqual(out["score"], 70)
            self.assertFalse(out["passed"], "70 must fail a 75 mark")
            answers, _ = self.answers_from_db("quiz", 8)
            status, out, _ = client.post("/api/assessment/quiz/submit", {"answers": answers})
            self.assertEqual(out["score"], 80)
            self.assertTrue(out["passed"], "80 must pass a 75 mark")
        finally:
            admin.put("/api/admin/settings", original)

    def test_scenario_60_fails(self):
        client, _ = self.register_fresh("scenario")
        answers, _ = self.answers_from_db("scenario", 3)
        status, out, _ = client.post("/api/assessment/scenario/submit", {"answers": answers})
        self.assertEqual(out["score"], 60)
        self.assertFalse(out["passed"])

    def test_practical_requires_full_answers(self):
        client, _ = self.register_fresh("practical-bad")
        status, out, _ = client.post("/api/practical/submit", {"responses": {"p1": "too short"}})
        self.assertEqual(status, 400)

    def test_plan_crud(self):
        client, _ = self.register_fresh("plan")
        status, out, _ = client.post("/api/plan", {"title": "Call five suppliers", "detail": "Compare prices.", "due": "2026-11-01"})
        self.assertEqual(status, 201, out)
        item = [p for p in out["plan"] if p["title"] == "Call five suppliers"][0]
        status, out, _ = client.patch(f"/api/plan/{item['id']}", {"done": True, "detail": "Compared three."})
        self.assertEqual(status, 200)
        self.assertTrue([p for p in out["plan"] if p["id"] == item["id"]][0]["done"])
        status, out, _ = client.delete(f"/api/plan/{item['id']}")
        self.assertEqual(status, 200)
        self.assertNotIn(item["id"], [p["id"] for p in out.get("plan", [])] if out.get("plan") else [])

    def test_coach_demo_mode_is_labelled(self):
        client, _ = self.register_fresh("coach")
        status, out, _ = client.post("/api/coach", {"mode": "teach", "messages": [{"role": "user", "content": "My prices are too low"}]})
        self.assertEqual(status, 200, out)
        self.assertTrue(out["demo"])
        self.assertIn("Demo mode", out["reply"])
        self.assertIn("Simple explanation", out["reply"])

    def test_coach_rejects_unknown_mode(self):
        client, _ = self.register_fresh("coach-bad")
        status, out, _ = client.post("/api/coach", {"mode": "hack", "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(status, 400)

    def test_template_downloads(self):
        client, _ = self.register_fresh("template")
        status, body, headers = client.get("/api/templates/break-even-worksheet")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertGreater(len(body), 100)


if __name__ == "__main__":
    unittest.main()
