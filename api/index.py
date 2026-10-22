"""Vercel entry point for the futurePreneur API.

All /api/* requests are rewritten to this function with the original route in
``?route=...`` (see vercel.json). The existing BaseHTTPRequestHandler does the
routing and validation, so the behaviour stays identical to local Python.
"""

import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server.db import init_db  # noqa: E402
from server.http import Handler  # noqa: E402

_ready = False
_lock = threading.Lock()


def _ensure_db():
    global _ready
    if _ready:
        return
    with _lock:
        if not _ready:
            init_db()
            _ready = True


class handler(Handler):
    def _prepare(self):
        try:
            _ensure_db()
        except Exception:
            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            body = b'{"error":"The service is starting up. Please retry.","code":"startup_failed"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False

        parsed = urlparse(self.path)
        route = parse_qs(parsed.query).get("route", [""])[0]
        if route:
            self.path = "/api/" + route.lstrip("/")
        elif parsed.path in ("/api/index", "/api/index.py"):
            self.path = "/api"
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parse_qs(parsed.query).get("route", [""])[0]
        if route.startswith("assets/"):
            rel = route[len("assets/"):].replace("..", "")
            target = os.path.join(ROOT, "static", rel)
            if os.path.isfile(target):
                types = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
                body = open(target, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", types.get(os.path.splitext(target)[1], "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
                return
        if self._prepare():
            super().do_GET()
    def do_POST(self):
        if self._prepare():
            super().do_POST()

    def do_PUT(self):
        if self._prepare():
            super().do_PUT()

    def do_PATCH(self):
        if self._prepare():
            super().do_PATCH()

    def do_DELETE(self):
        if self._prepare():
            super().do_DELETE()
