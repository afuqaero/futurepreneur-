"""Phase 6: coach persistence, privacy, rate window and live provider config."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from helpers import ServerCase, free_port

PROFILE = {
    "business_name": "Test Kitchen",
    "sector": "Food & beverage",
    "stage": "Growing",
    "team_size": "2–5",
    "revenue_band": "RM20,000–RM50,000",
    "years": "3–5 years",
    "main_challenge": "Margins are thin and I do not know which menu items actually make money.",
}


class MockAIHandler(BaseHTTPRequestHandler):
    last_request = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}
        MockAIHandler.last_request = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "payload": payload,
        }
        body = json.dumps({
            "choices": [{"message": {"content": "Live mock answer: check contribution before discounting."}}]
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CoachPhase6Tests(ServerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mock_port = free_port()
        cls.mock = ThreadingHTTPServer(("127.0.0.1", cls.mock_port), MockAIHandler)
        cls.mock_thread = threading.Thread(target=cls.mock.serve_forever, daemon=True)
        cls.mock_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock.shutdown()
        cls.mock.server_close()
        super().tearDownClass()

    def setUp(self):
        MockAIHandler.last_request = None

    def test_conversation_persists_and_can_be_cleared(self):
        learner, _ = self.register_fresh("coach-save")
        status, first, _ = learner.post("/api/coach", {
            "mode": "teach", "message": "My prices are too low and I keep discounting.",
        })
        self.assertEqual(status, 200, first)
        self.assertTrue(first["demo"])
        self.assertIn("Demo mode", first["reply"])
        session_id = first["session_id"]

        status, listing, _ = learner.get("/api/coach/sessions")
        self.assertEqual(status, 200, listing)
        self.assertEqual(len(listing["sessions"]), 1)
        self.assertEqual(listing["sessions"][0]["id"], session_id)
        self.assertIn("prices", listing["sessions"][0]["title"])

        status, loaded, _ = learner.get(f"/api/coach/sessions/{session_id}")
        self.assertEqual(status, 200, loaded)
        self.assertEqual([m["role"] for m in loaded["messages"]], ["user", "assistant"])

        status, second, _ = learner.post("/api/coach", {
            "mode": "teach", "message": "Give me one next step.", "session_id": session_id,
        })
        self.assertEqual(status, 200, second)
        self.assertEqual(second["session_id"], session_id)
        status, loaded, _ = learner.get(f"/api/coach/sessions/{session_id}")
        self.assertEqual(len(loaded["messages"]), 4)

        status, _, _ = learner.delete(f"/api/coach/sessions/{session_id}")
        self.assertEqual(status, 200)
        status, listing, _ = learner.get("/api/coach/sessions")
        self.assertEqual(listing["sessions"], [])

    def test_conversations_are_private_to_the_owner(self):
        owner, _ = self.register_fresh("coach-owner")
        other, _ = self.register_fresh("coach-other")
        status, out, _ = owner.post("/api/coach", {"mode": "teach", "message": "My cash is tight this month."})
        self.assertEqual(status, 200, out)
        session_id = out["session_id"]
        status, _, _ = other.get(f"/api/coach/sessions/{session_id}")
        self.assertEqual(status, 404)
        status, listing, _ = other.get("/api/coach/sessions")
        self.assertEqual(listing["sessions"], [])

    def test_rate_limit_returns_429_with_retry_after(self):
        learner, _ = self.register_fresh("coach-rate")
        last = None
        for i in range(20):
            status, last, _ = learner.post("/api/coach", {"mode": "teach", "message": f"Short question {i}"})
            self.assertEqual(status, 200, last)
        status, out, headers = learner.post("/api/coach", {"mode": "teach", "message": "One too many"})
        self.assertEqual(status, 429, out)
        self.assertEqual(out.get("code"), "rate_limited")
        self.assertTrue(headers.get("Retry-After"))
        self.assertIn("Coach limit reached", out.get("error", ""))

    def test_admin_config_is_masked_and_live_coach_gets_context(self):
        admin = self.login_admin()
        learner, _ = self.register_fresh("coach-live")
        learner.put("/api/profile", PROFILE)

        base = f"http://127.0.0.1:{self.mock_port}/v1"
        status, saved, _ = admin.put("/api/admin/ai", {
            "base_url": base, "model": "mock-model", "api_key": "sk-secret-test",
        })
        self.assertEqual(status, 200, saved)
        self.assertTrue(saved["configured"])
        self.assertTrue(saved["key_set"])
        self.assertEqual(saved["key_source"], "database")

        status, admin_ai, _ = admin.get("/api/admin/ai")
        self.assertEqual(status, 200)
        self.assertTrue(admin_ai["configured"])
        self.assertNotIn("sk-secret-test", json.dumps(admin_ai))

        status, boot, _ = learner.get("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertNotIn("sk-secret-test", json.dumps(boot))
        self.assertTrue(boot["ai"]["configured"])

        status, out, _ = learner.post("/api/coach", {
            "mode": "solve", "message": "Should I discount my lunch sets to win an office contract?",
        })
        self.assertEqual(status, 200, out)
        self.assertFalse(out["demo"])
        self.assertEqual(out["reply"], "Live mock answer: check contribution before discounting.")
        self.assertIsNotNone(MockAIHandler.last_request)
        sent = MockAIHandler.last_request
        self.assertEqual(sent["path"], "/v1/chat/completions")
        self.assertEqual(sent["authorization"], "Bearer sk-secret-test")
        system = sent["payload"]["messages"][0]["content"]
        self.assertIn("Test Kitchen", system)
        self.assertIn("Safety rules", system)
        self.assertIn("Never treat the check-up as a verified score", system)
        self.assertEqual(sent["payload"]["model"], "mock-model")

        status, cleared, _ = admin.put("/api/admin/ai", {
            "base_url": base, "model": "mock-model", "clear_key": True,
        })
        self.assertEqual(status, 200, cleared)
        self.assertFalse(cleared["configured"])
        self.assertEqual(cleared["mode"], "demo")

    def test_learner_cannot_change_ai_config(self):
        learner, _ = self.register_fresh("coach-config")
        status, out, _ = learner.put("/api/admin/ai", {
            "base_url": "http://example.com/v1", "model": "x",
        })
        self.assertEqual(status, 403, out)

    def test_unknown_session_and_bad_mode(self):
        learner, _ = self.register_fresh("coach-bad")
        status, out, _ = learner.post("/api/coach", {"mode": "hack", "message": "hi"})
        self.assertEqual(status, 400)
        status, out, _ = learner.post("/api/coach", {"mode": "teach", "session_id": 999999, "message": "hi"})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
