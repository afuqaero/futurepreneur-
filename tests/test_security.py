"""Security headers, static serving and cookie behaviour."""

import unittest

from helpers import ServerCase


class SecurityTests(ServerCase):
    def test_security_headers_on_api(self):
        client = self.client()
        status, _, headers = client.get("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")
        self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))
        self.assertIn("script-src 'self'", headers.get("Content-Security-Policy", ""))

    def test_index_sets_csrf_cookie_readable_by_js(self):
        client = self.client(bootstrap=False)
        status, _, headers = client.get("/")
        self.assertEqual(status, 200)
        cookie = headers.get("Set-Cookie", "")
        self.assertIn("br_csrf=", cookie)
        self.assertNotIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertTrue(client.csrf())

    def test_static_traversal_is_blocked(self):
        client = self.client()
        for path in ("/static/../run.py", "/static/..%2frun.py", "/static/%2e%2e/server.py"):
            status, _, _ = client.get(path)
            self.assertEqual(status, 404, path)

    def test_unknown_api_route_is_json_404(self):
        client = self.login_demo()
        status, out, _ = client.get("/api/does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(out.get("code"), "not_found")

    def test_invalid_json_body_is_rejected(self):
        client = self.login_demo()
        status, out, _ = client.request("POST", "/api/plan", payload=None)
        # No body at all is treated as {} -> validation error, not a crash.
        self.assertIn(status, (400, 422), out)

    def test_oversized_body_declaration_is_rejected(self):
        client = self.login_demo()
        import http.client
        from urllib.parse import urlparse

        session = next((c.value for c in client.jar if c.name == "br_session"), "")
        parsed = urlparse(self.base)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
        conn.putrequest("POST", "/api/plan")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("X-CSRF-Token", client.csrf())
        conn.putheader("Cookie", f"br_csrf={client.csrf()}; br_session={session}")
        conn.putheader("Content-Length", str(2_000_000))
        conn.endheaders()
        res = conn.getresponse()
        self.assertEqual(res.status, 413)
        conn.close()


if __name__ == "__main__":
    unittest.main()
