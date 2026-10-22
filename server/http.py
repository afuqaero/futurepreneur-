"""HTTP plumbing: responses, static files and request dispatch."""

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

from . import config, security
from .db import get_db
from .errors import ApiError
from .routes import route as api_route

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "futurePreneur/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        if not config.QUIET:
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    # -- low level ---------------------------------------------------------

    def _write(self, body, ctype, status=200, cookies=None, headers=None, default_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in security.security_headers().items():
            self.send_header(key, value)
        for key, value in (default_headers or {}).items():
            self.send_header(key, value)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if isinstance(cookies, str):
            cookies = [cookies]
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=200, cookie=None, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._write(
            body,
            "application/json; charset=utf-8",
            status,
            cookies=cookie,
            headers=headers,
            default_headers={"Cache-Control": "no-store"},
        )

    def send_bytes(self, data, ctype, status=200, extra=None):
        self._write(data, ctype, status, headers=extra)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > config.MAX_BODY:
            raise ApiError(413, "Request too large.", "too_large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            raise ApiError(400, "Invalid JSON body.", "invalid_json")
        if not isinstance(data, dict):
            raise ApiError(400, "JSON body must be an object.", "invalid_json")
        return data

    def serve_static(self, path):
        index = path in ("/", "/index.html")
        if index:
            file = config.STATIC_DIR / "index.html"
        elif path.startswith("/static/"):
            rel = unquote(path[len("/static/"):])
            file = (config.STATIC_DIR / rel).resolve()
            if config.STATIC_DIR.resolve() not in file.parents:
                raise ApiError(404, "Not found.", "not_found")
        else:
            raise ApiError(404, "Not found.", "not_found")
        if not file.is_file():
            raise ApiError(404, "Not found.", "not_found")
        data = file.read_bytes()
        ctype = MIME.get(file.suffix.lower(), "application/octet-stream")
        if file.suffix.lower() in (".html", ".css", ".js"):
            # No-store: this app is edited in place, and stale CSS/JS during a
            # session is a real source of phantom bugs.
            extra = {"Cache-Control": "no-store"}
        else:
            extra = {"Cache-Control": "public, max-age=3600"}
        cookies = None
        if index:
            _, cookies = security.ensure_csrf(self)
        self._write(data, ctype, 200, cookies=cookies, headers=extra)

    # -- verbs -------------------------------------------------------------

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/"):
                if method in ("POST", "PUT", "PATCH", "DELETE"):
                    security.require_csrf(self)
                self.handle_api(method, path, parse_qs(parsed.query))
            elif method == "GET":
                self.serve_static(path)
            else:
                raise ApiError(404, "Not found.", "not_found")
        except ApiError as exc:
            payload = {"error": exc.message}
            if exc.code:
                payload["code"] = exc.code
            self.send_json(payload, exc.status, headers=exc.headers)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            try:
                self.send_json({"error": "Something went wrong on the server.", "code": "server_error"}, 500)
            except Exception:
                pass

    # -- api ---------------------------------------------------------------

    def handle_api(self, method, path, query):
        conn = get_db()
        try:
            api_route(self, conn, method, path, query)
        finally:
            conn.close()


def make_server(host=None, port=None):
    from http.server import ThreadingHTTPServer

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    return Server((host or config.HOST, config.PORT if port is None else port), Handler)
