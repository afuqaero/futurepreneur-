"""Phase 3: Check-Up v2 — expanded profile, history, deltas, recommendations."""

import unittest

from helpers import ServerCase

PROFILE = {
    "business_name": "Retake Kitchen",
    "sector": "Food & beverage",
    "customer_type": "Consumers (B2C)",
    "stage": "Growing",
    "team_size": "2–5",
    "revenue_band": "RM20,000–RM50,000",
    "years": "3–5 years",
    "main_challenge": "Margins are thin and I do not know which menu items make money.",
}


class CheckupV2Tests(ServerCase):
    def test_profile_stores_customer_type(self):
        client, _ = self.register_fresh("profile-v2")
        status, out, _ = client.put("/api/profile", PROFILE)
        self.assertEqual(status, 200, out)
        status, checkup, _ = client.get("/api/checkup")
        self.assertEqual(status, 200)
        self.assertEqual(checkup["profile"]["customer_type"], "Consumers (B2C)")

    def test_retake_keeps_history_and_shows_delta(self):
        client, _ = self.register_fresh("retake")
        client.put("/api/profile", PROFILE)

        answers, _ = self.answers_from_db("diagnostic", 16)
        status, first, _ = client.post("/api/checkup/submit", {"answers": answers})
        self.assertEqual(status, 200, first)
        self.assertEqual(first["score"], 67)
        self.assertIsNone(first["change"])
        self.assertEqual(len(first["history"]), 1)
        self.assertEqual(len(first["strengths"]), 3)

        answers, _ = self.answers_from_db("diagnostic", 20)
        status, second, _ = client.post("/api/checkup/submit", {"answers": answers})
        self.assertEqual(status, 200, second)
        self.assertEqual(second["score"], 83)
        self.assertIsNotNone(second["change"])
        self.assertEqual(second["change"]["overall"], 16)
        self.assertEqual(second["previous"]["overall"], 67)
        self.assertEqual(len(second["history"]), 2)
        self.assertEqual(second["history"][1]["overall"], 67, "first result must be kept")

    def test_get_returns_priorities_with_links_after_reload(self):
        client, _ = self.register_fresh("results")
        client.put("/api/profile", PROFILE)
        answers, _ = self.answers_from_db("diagnostic", 18)
        client.post("/api/checkup/submit", {"answers": answers})

        status, data, _ = client.get("/api/checkup")
        self.assertEqual(status, 200)
        self.assertEqual(data["result"]["overall"], 75)
        self.assertGreaterEqual(len(data["priorities"]), 1)
        self.assertLessEqual(len(data["priorities"]), 3)
        self.assertEqual(len(data["strengths"]), 3)
        self.assertEqual(len(data["history"]), 1)
        self.assertIsNone(data["change"])
        scores = [pr["score"] for pr in data["priorities"]]
        self.assertEqual(scores, sorted(scores), "priorities must be ordered weakest first")
        for pr in data["priorities"]:
            self.assertIn("recommendation", pr)
            if pr["available"]:
                self.assertEqual(pr["module_id"], "strategy")
                self.assertIsInstance(pr["lessons"], list)
            else:
                self.assertIsNone(pr["module_id"])

    def test_history_ordering_is_newest_first(self):
        client, _ = self.register_fresh("order")
        client.put("/api/profile", PROFILE)
        for correct in (12, 16, 20):
            answers, _ = self.answers_from_db("diagnostic", correct)
            client.post("/api/checkup/submit", {"answers": answers})
        status, data, _ = client.get("/api/checkup")
        overalls = [h["overall"] for h in data["history"]]
        self.assertEqual(overalls, [83, 67, 50])
        self.assertEqual(data["change"]["overall"], 16)


if __name__ == "__main__":
    unittest.main()
