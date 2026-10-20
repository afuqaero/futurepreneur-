"""Registration, login, logout and bootstrap."""

import re

import content
from .. import security
from ..clock import iso
from ..errors import ApiError, clean_text
from ..models import public_user, settings_public
from ..scoring import build_progress
from ..ai import ai_status


def handle(h, conn, method, path, query):
    if path == "/api/auth/register" and method == "POST":
        body = h.read_json()
        name = clean_text(body.get("name"), 80, "Name")
        email = clean_text(body.get("email"), 200, "Email").lower()
        password = body.get("password") or ""
        if len(name) < 2:
            raise ApiError(400, "Please enter your name.", "invalid_input")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise ApiError(400, "Please enter a valid email address.", "invalid_input")
        if not isinstance(password, str) or len(password) < 8:
            raise ApiError(400, "Password must be at least 8 characters.", "invalid_input")
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            raise ApiError(409, "An account with that email already exists.", "email_taken")
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
            (name, email, security.hash_password(password), "learner", iso()),
        )
        user_id = cur.lastrowid
        conn.commit()
        token = security.create_session(conn, user_id)
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        h.send_json(
            {"user": public_user(user), "progress": build_progress(conn, user)},
            201,
            security.session_cookie(token),
        )
        return True

    if path == "/api/auth/login" and method == "POST":
        body = h.read_json()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        retry = security.login_retry_after(h, email)
        if retry:
            raise ApiError(
                429,
                f"Too many sign-in attempts. Try again in {retry} seconds.",
                "rate_limited",
                {"Retry-After": str(retry)},
            )
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not security.verify_password(password, row["password_hash"]):
            security.note_login_failure(h, email)
            raise ApiError(401, "Email or password is incorrect.", "invalid_credentials")
        security.clear_login_failures(h, email)
        token = security.create_session(conn, row["id"])
        h.send_json(
            {"user": public_user(row), "progress": build_progress(conn, row)},
            200,
            security.session_cookie(token),
        )
        return True

    if path == "/api/auth/logout" and method == "POST":
        token = security.read_cookie(h, "br_session")
        if token:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        h.send_json({"ok": True}, 200, security.clear_session_cookie())
        return True

    if path == "/api/bootstrap" and method == "GET":
        user = security.current_user(conn, h)
        data = {
            "components": content.COMPONENTS,
            "settings": settings_public(conn),
            "ai": ai_status(),
            "user": public_user(user) if user else None,
        }
        if user:
            data["progress"] = build_progress(conn, user)
        _, cookie = security.ensure_csrf(h)
        h.send_json(data, 200, cookie)
        return True

    return False
