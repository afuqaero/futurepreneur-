"""Passwords, sessions, CSRF tokens, login throttling and response headers."""

import hashlib
import hmac
import math
import secrets
import threading
import time
from datetime import datetime, timedelta
from http.cookies import SimpleCookie

from . import config
from .clock import iso, utcnow
from .errors import ApiError

# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password):
    salt = secrets.token_bytes(16)
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cookies and sessions
# ---------------------------------------------------------------------------


def _cookie(name, value, max_age, http_only=True):
    parts = [f"{name}={value}", "Path=/", f"Max-Age={max_age}", "SameSite=Lax"]
    if http_only:
        parts.append("HttpOnly")
    if config.SECURE_COOKIES:
        parts.append("Secure")
    return "; ".join(parts)


def session_cookie(token):
    return _cookie("br_session", token, config.SESSION_DAYS * 86400)


def clear_session_cookie():
    return _cookie("br_session", "", 0)


def csrf_cookie(token):
    # Readable by JavaScript on purpose: the SPA echoes it in a header.
    return _cookie("br_csrf", token, config.SESSION_DAYS * 86400, http_only=False)


def read_cookie(handler, name):
    jar = SimpleCookie()
    try:
        jar.load(handler.headers.get("Cookie", ""))
    except Exception:
        return None
    morsel = jar.get(name)
    return morsel.value if morsel else None


def create_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, iso(now), iso(now + timedelta(days=config.SESSION_DAYS))),
    )
    conn.commit()
    return token


def current_user(conn, handler):
    token = read_cookie(handler, "br_session")
    if not token:
        return None
    row = conn.execute(
        "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    if not row:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if expires < utcnow():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return None
    except Exception:
        return None
    return row


def require_user(conn, handler):
    user = current_user(conn, handler)
    if not user:
        raise ApiError(401, "Please sign in to continue.", "unauthorized")
    return user


def require_admin(conn, handler):
    user = require_user(conn, handler)
    if user["role"] != "admin":
        raise ApiError(403, "Administrator access required.", "forbidden")
    return user


# ---------------------------------------------------------------------------
# CSRF: signed double-submit cookie
# ---------------------------------------------------------------------------

_secret_lock = threading.Lock()
_secret_cache = None


def _secret():
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    with _secret_lock:
        if _secret_cache:
            return _secret_cache
        try:
            raw = config.CSRF_SECRET_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            raw = ""
        if not raw:
            raw = secrets.token_hex(32)
            config.CSRF_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = config.CSRF_SECRET_PATH.with_suffix(".tmp")
            tmp.write_text(raw, encoding="utf-8")
            tmp.replace(config.CSRF_SECRET_PATH)
        _secret_cache = bytes.fromhex(raw)
        return _secret_cache


def new_csrf_token():
    nonce = secrets.token_hex(16)
    signature = hmac.new(_secret(), nonce.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def csrf_token_valid(token):
    if not isinstance(token, str) or "." not in token:
        return False
    nonce, _, signature = token.rpartition(".")
    expected = hmac.new(_secret(), nonce.encode("ascii"), hashlib.sha256).hexdigest()
    return secrets.compare_digest(signature, expected)


def ensure_csrf(handler):
    """Return (token, set_cookie_header_or_None)."""
    existing = read_cookie(handler, "br_csrf")
    if existing and csrf_token_valid(existing):
        return existing, None
    token = new_csrf_token()
    return token, csrf_cookie(token)


def require_csrf(handler):
    cookie = read_cookie(handler, "br_csrf")
    header = handler.headers.get("X-CSRF-Token")
    if not cookie or not header or not secrets.compare_digest(cookie, header) or not csrf_token_valid(header):
        raise ApiError(
            403,
            "Your security token expired. Reload the page and try again.",
            "csrf_invalid",
        )


# ---------------------------------------------------------------------------
# Login throttling (process-local; documented as such)
# ---------------------------------------------------------------------------

_login_failures = {}
_login_lock = threading.Lock()


def client_ip(handler):
    if config.TRUST_PROXY:
        forwarded = handler.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return handler.client_address[0]


def _rate_key(handler, email):
    return f"{client_ip(handler)}|{(email or '').strip().lower()}"


def _prune(bucket, now):
    while bucket and now - bucket[0] > config.LOGIN_WINDOW_SECONDS:
        bucket.pop(0)


def login_retry_after(handler, email):
    key = _rate_key(handler, email)
    now = time.monotonic()
    with _login_lock:
        bucket = _login_failures.get(key)
        if not bucket:
            return 0
        _prune(bucket, now)
        if len(bucket) < config.LOGIN_MAX_FAILURES:
            return 0
        return max(1, math.ceil(config.LOGIN_WINDOW_SECONDS - (now - bucket[0])))


def note_login_failure(handler, email):
    key = _rate_key(handler, email)
    now = time.monotonic()
    with _login_lock:
        bucket = _login_failures.setdefault(key, [])
        _prune(bucket, now)
        bucket.append(now)
        if len(_login_failures) > 5000:
            for stale in [k for k, v in _login_failures.items() if not v]:
                _login_failures.pop(stale, None)


def clear_login_failures(handler, email):
    with _login_lock:
        _login_failures.pop(_rate_key(handler, email), None)


# ---------------------------------------------------------------------------
# Response headers
# ---------------------------------------------------------------------------

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def security_headers():
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Content-Security-Policy": CSP,
    }
    if config.SECURE_COOKIES:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers
