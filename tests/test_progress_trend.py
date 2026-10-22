"""Phase 7: progress trend and module result data."""

import unittest

from helpers import ServerCase

PROFILE = {
    "business_name": "Trend Bakery",
    "sector": "Food & beverage",
    "stage": "Growing",
    "team_size": "2–5",
    "revenue_band": "RM20,000–RM50,000",
    "years": "3–5 years",
    "main_challenge": "I need evidence of what is improving.",
}


class ProgressTrendTests(ServerCase):
    def test_trend_is_chronological_with_attempt_evidence(self):
        learner, _ = self.register_fresh("trend")
        learner.put("/api/profile", PROFILE)

        status, quiz, _ = learner.get("/api/module/strategy/assessment/quiz/questions")
        self.assertEqual(status, 200, quiz)
        answers, total = self.answers_from_db("quiz", 9, "strategy")
        self.assertEqual(len(answers), total)
        status, out, _ = learner.post("/api/module/strategy/assessment/quiz/submit", {"answers": answers})
        self.assertEqual(status, 200, out)
        self.assertTrue(out["passed"])

        status, scenario, _ = learner.get("/api/module/strategy/assessment/scenario/questions")
        self.assertEqual(status, 200, scenario)
        answers, total = self.answers_from_db("scenario", 1, "strategy")
        status, out2, _ = learner.post("/api/module/strategy/assessment/scenario/submit", {"answers": answers})
        self.assertEqual(status, 200, out2)
        self.assertFalse(out2["passed"])

        status, progress, _ = learner.get("/api/progress")
        self.assertEqual(status, 200, progress)
        trend = progress["trend"]
        self.assertEqual([t["kind"] for t in trend], ["quiz", "scenario"])
        self.assertEqual([t["score"] for t in trend], [out["score"], out2["score"]])
        self.assertEqual([t["passed"] for t in trend], [True, False])
        self.assertTrue(all(t["module_title"] == "Business Strategy & Model" for t in trend))
        self.assertTrue(all("created_at" in t for t in trend))
        self.assertTrue(progress["modules"])
        strategy = next(m for m in progress["modules"] if m["id"] == "strategy")
        self.assertTrue(strategy["quiz_passed"])
        self.assertFalse(strategy["scenario_passed"])
        self.assertFalse(strategy["passed"])


if __name__ == "__main__":
    unittest.main()
