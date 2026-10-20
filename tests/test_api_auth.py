"""Authentication, CSRF and role checks against the real HTTP server."""

import os
import sqlite3
import time
import unittest

from helpers import ServerCase


class AuthTests(ServerCase):
    def test_register_returns_session_and_progress(self):
        client, body = self.register_fresh("register")
        self.assertIn("user", body)
        self.assertEqual(body["user"]["role"], "learner")
        self.assertIn("progress", body)
        status, me, _ = client.get("/api/me")
        self.assertEqual(status, 200)
        self.assertEqual(me["user"]["email"], body["user"]["email"])

    def test_register_rejects_duplicate_email(self):
        client, body = self.register_fresh("dupe")
        status, out, _ = client.register("Another", body["user"]["email"])
        self.assertEqual(status, 409)
        self.assertEqual(out.get("code"), "email_taken")

    def test_register_rejects_bad_email_and_short_password(self):
        client = self.client()
        status, _, _ = client.register("A", "not-an-email", "Testing1234!")
        self.assertEqual(status, 400)
        status, _, _ = client.register("A Person", "a@b.co", "short")
        self.assertEqual(status, 400)

    def test_login_success_and_wrong_password(self):
        client, body = self.register_fresh("login")
        email = body["user"]["email"]

        wrong = self.client()
        status, _, _ = wrong.login(email, "WrongPassword1")
        self.assertEqual(status, 401)

        status, out, headers = client.login(email, "Testing1234!")
        self.assertEqual(status, 200)
        self.assertEqual(out["user"]["email"], email)
        self.assertIn("br_session=", headers.get("Set-Cookie", ""))
        self.assertIn("HttpOnly", headers.get("Set-Cookie", ""))

    def test_logout_invalidates_session(self):
        client, _ = self.register_fresh("logout")
        status, _, _ = client.post("/api/auth/logout")
        self.assertEqual(status, 200)
        status, _, _ = client.get("/api/me")
        self.assertEqual(status, 401)

    def test_csrf_missing_is_rejected(self):
        client = self.client()
        status, out, _ = client.post(
            "/api/auth/login",
            {"email": "aina@demo.bizready.app", "password": "Demo1234!"},
            csrf=False,
        )
        self.assertEqual(status, 403)
        self.assertEqual(out.get("code"), "csrf_invalid")

    def test_csrf_wrong_token_is_rejected(self):
        client = self.client()
        status, out, _ = client.post(
            "/api/auth/login",
            {"email": "aina@demo.bizready.app", "password": "Demo1234!"},
            token="0" * 32 + "." + "0" * 64,
        )
        self.assertEqual(status, 403)
        self.assertEqual(out.get("code"), "csrf_invalid")

    def test_login_rate_limit_blocks_sixth_attempt(self):
        client, body = self.register_fresh("ratelimit")
        email = body["user"]["email"]
        for _ in range(5):
            status, _, _ = client.login(email, "Definitely Wrong 1")
            self.assertEqual(status, 401)
        status, out, headers = client.login(email, "Testing1234!")
        self.assertEqual(status, 429, out)
        self.assertIn("Retry-After", headers)

    def test_password_is_hashed(self):
        client, body = self.register_fresh("hash")
        db = os.path.join(self.tmpdir, "bizready.db")
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT password_hash FROM users WHERE email = ?", (body["user"]["email"],)).fetchone()
        conn.close()
        self.assertTrue(row["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertNotIn("Testing1234!", row["password_hash"])

    def test_learner_cannot_use_admin_routes(self):
        client = self.login_demo()
        status, out, _ = client.get("/api/admin/overview")
        self.assertEqual(status, 403, out)

    def test_unauthenticated_progress_is_401(self):
        client = self.client()
        status, out, _ = client.get("/api/progress")
        self.assertEqual(status, 401)

    def test_admin_can_read_overview(self):
        client = self.login_admin()
        status, out, _ = client.get("/api/admin/overview")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(out["stats"]["learners"], 1)
        self.assertIn("learners", out)


if __name__ == "__main__":
    unittest.main()
