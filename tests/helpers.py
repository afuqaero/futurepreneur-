"""Test harness: boots the real server on a random port with a throwaway DB."""

import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    # -- cookies ---------------------------------------------------------
    def csrf(self):
        for cookie in self.jar:
            if cookie.name == "br_csrf":
                return cookie.value
        return ""

    def bootstrap(self):
        return self.request("GET", "/api/bootstrap")

    # -- requests --------------------------------------------------------
    def request(self, method, path, payload=None, csrf=True, token=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if method != "GET" and csrf:
            headers["X-CSRF-Token"] = self.csrf() if token is None else token
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=15) as res:
                return res.status, self._parse(res), dict(res.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, self._parse(exc), dict(exc.headers)

    @staticmethod
    def _parse(res):
        raw = res.read()
        ctype = res.headers.get("Content-Type", "")
        if "application/json" in ctype:
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return raw.decode("utf-8", "replace")
        return raw.decode("utf-8", "replace")

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, payload=None, **kwargs):
        return self.request("POST", path, payload, **kwargs)

    def put(self, path, payload=None, **kwargs):
        return self.request("PUT", path, payload, **kwargs)

    def patch(self, path, payload=None, **kwargs):
        return self.request("PATCH", path, payload, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

    # -- convenience -----------------------------------------------------
    def login(self, email, password):
        return self.post("/api/auth/login", {"email": email, "password": password})

    def register(self, name, email, password="Testing1234!"):
        return self.post("/api/auth/register", {"name": name, "email": email, "password": password})


class ServerCase(unittest.TestCase):
    tmpdir = None
    proc = None
    port = None
    base = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="bizready-test-")
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env.update({
            "BIZREADY_DATA_DIR": cls.tmpdir,
            "BIZREADY_SKIP_BACKUP": "1",
            "BIZREADY_QUIET": "1",
            "BIZREADY_SECURE_COOKIES": "0",
        })
        env.pop("BIZREADY_AI_KEY", None)
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "run.py"), "--port", str(cls.port)],
            cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise RuntimeError("server exited during startup:\n" + (cls.proc.stderr.read() or ""))
            try:
                with urllib.request.urlopen(cls.base + "/api/bootstrap", timeout=1) as res:
                    if res.status == 200:
                        return
            except Exception:
                time.sleep(0.15)
        raise RuntimeError("server did not become ready")

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
        for stream in (cls.proc.stdout, cls.proc.stderr) if cls.proc else ():
            try:
                if stream is cls.proc.stderr and os.environ.get("BIZREADY_TEST_DEBUG") == "1":
                    tail = stream.read()[-6000:]
                    if tail.strip():
                        print("\n--- server stderr ---\n" + tail + "\n--- end server stderr ---")
                stream.close()
            except Exception:
                pass
        if cls.tmpdir:
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # -- fixtures --------------------------------------------------------
    def client(self, bootstrap=True):
        client = Client(self.base)
        if bootstrap:
            client.bootstrap()
        return client

    def login_demo(self):
        client = self.client()
        status, body, _ = client.login("aina@demo.bizready.app", "Demo1234!")
        self.assertEqual(status, 200, body)
        return client

    def login_admin(self):
        client = self.client()
        status, body, _ = client.login("admin@bizready.app", "Admin1234!")
        self.assertEqual(status, 200, body)
        return client

    def register_fresh(self, tag="learner"):
        client = self.client()
        email = f"{tag}-{int(time.time() * 1000)}-{self.id().split('.')[-1][:12]}@test.local"
        status, body, _ = client.register("Test Learner", email)
        self.assertEqual(status, 201, body)
        return client, body

    def answers_from_db(self, kind, correct_count):
        """Return {question_id: chosen_index} with exactly correct_count right."""
        import sqlite3

        db = os.path.join(self.tmpdir, "bizready.db")
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, correct, options FROM questions WHERE kind = ? AND active = 1 ORDER BY position, id",
            (kind,),
        ).fetchall()
        conn.close()
        answers = {}
        for i, row in enumerate(rows):
            options = json.loads(row["options"])
            if i < correct_count:
                answers[str(row["id"])] = row["correct"]
            else:
                answers[str(row["id"])] = (row["correct"] + 1) % len(options)
        return answers, len(rows)
