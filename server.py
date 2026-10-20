"""BizReady — a working entrepreneurial training platform.

Zero external dependencies: Python standard library + SQLite + static frontend.

Run:
    python server.py            # http://localhost:8000
    python server.py 8080

Optional AI coach configuration (server-side only), config.json:
    {"ai": {"provider": "openai", "api_key": "...", "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini"}}
or set BIZREADY_AI_KEY. Without a key the coach runs in a clearly labelled demo mode.
"""

import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import time
import traceback
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import content

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bizready.db"
CONFIG_PATH = BASE_DIR / "config.json"
SESSION_DAYS = 7
MAX_BODY = 1_000_000

DEFAULT_SETTINGS = {
    "quiz_pass": "80",
    "scenario_pass": "70",
    "rubric_min": "3.0",
    "rubric_floor": "2",
    "platform_name": "BizReady",
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def utcnow():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or utcnow()).isoformat(timespec="seconds").replace("+00:00", "Z")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'learner',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    business_name TEXT NOT NULL,
    sector TEXT NOT NULL,
    stage TEXT NOT NULL,
    team_size TEXT NOT NULL,
    revenue_band TEXT NOT NULL,
    years TEXT NOT NULL,
    main_challenge TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    kind TEXT NOT NULL,
    topic TEXT NOT NULL,
    prompt TEXT NOT NULL,
    options TEXT NOT NULL,
    correct INTEGER NOT NULL,
    explanation TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diagnostic_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    answers TEXT NOT NULL,
    component_scores TEXT NOT NULL,
    overall INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    component TEXT NOT NULL,
    score INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS practical_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    responses TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    rubric TEXT,
    average REAL,
    passed INTEGER NOT NULL DEFAULT 0,
    reviewer_note TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    due TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS content_overrides (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def hash_password(password):
    salt = secrets.token_bytes(16)
    iterations = 200_000
    digest = __import__("hashlib").pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = __import__("hashlib").pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def seed_questions(conn):
    if conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]:
        return
    rows = []
    pos = 0
    for item in content.DIAGNOSTIC_QUESTIONS + content.QUIZ_QUESTIONS + content.SCENARIO_QUESTIONS:
        pos += 1
        rows.append((
            item["id"], item["component"], item["kind"], item["topic"], item["prompt"],
            json.dumps(item["options"]), item["correct"], item["explanation"], 1, pos,
        ))
    conn.executemany(
        "INSERT INTO questions (id, component, kind, topic, prompt, options, correct, explanation, active, position)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)", rows,
    )


def seed_demo(conn):
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    now = utcnow()
    admin = conn.execute(
        "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
        ("Platform Admin", "admin@bizready.app", hash_password("Admin1234!"), "admin", iso(now)),
    ).lastrowid
    learner = conn.execute(
        "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
        ("Aina Rahman", "aina@demo.bizready.app", hash_password("Demo1234!"), "learner", iso(now - timedelta(days=21))),
    ).lastrowid

    conn.execute(
        "INSERT INTO profiles (user_id, business_name, sector, stage, team_size, revenue_band, years, main_challenge, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (learner, "Aina's Kitchen", "Food & beverage", "Growing", "2–5", "RM20,000–RM50,000", "3–5 years",
         "Profit is inconsistent from month to month, even when sales look busy.", iso(now - timedelta(days=19))),
    )

    scores = {"strategy": 75, "marketing": 62, "operations": 58, "finance": 50,
              "people": 67, "systems": 42, "legal": 54, "digital": 46}
    conn.execute(
        "INSERT INTO diagnostic_results (user_id, answers, component_scores, overall, created_at) VALUES (?,?,?,?,?)",
        (learner, "{}", json.dumps(scores), round(sum(scores.values()) / len(scores)), iso(now - timedelta(days=18))),
    )

    conn.executemany(
        "INSERT INTO lesson_progress (user_id, lesson_id, completed_at) VALUES (?,?,?)",
        [(learner, lid, iso(now - timedelta(days=15 - i))) for i, lid in enumerate(["l1", "l2", "l3", "l4"])],
    )

    conn.execute(
        "INSERT INTO attempts (user_id, kind, component, score, passed, detail, created_at) VALUES (?,?,?,?,?,?,?)",
        (learner, "quiz", "strategy", 90, 1, json.dumps({"correct": 9, "total": 10}), iso(now - timedelta(days=12))),
    )
    conn.execute(
        "INSERT INTO attempts (user_id, kind, component, score, passed, detail, created_at) VALUES (?,?,?,?,?,?,?)",
        (learner, "scenario", "strategy", 80, 1, json.dumps({"correct": 4, "total": 5}), iso(now - timedelta(days=10))),
    )
    conn.execute(
        "INSERT INTO practical_submissions (user_id, responses, status, rubric, average, passed, reviewer_note, created_at, reviewed_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (learner,
         json.dumps({
             "p1": "Busy office workers within 1km who need a reliable hot lunch in under 15 minutes. They currently queue at cafés, order delivery apps and wait 30–40 minutes, or skip lunch.",
             "p2": "For busy office workers nearby who need a reliable hot lunch, we provide a fixed-price set meal ready in five minutes, unlike cafés with long queues or delivery apps with uncertain arrival times.",
             "p3": "Set price RM12.00. Ingredients RM4.50, packaging RM0.80, delivery RM1.20 = RM6.50 direct cost, contribution RM5.50. Fixed costs RM1,650/month. Break-even 300 sets, about 14 working days at 22 sets.",
             "p4": "Priority 1: two corporate lunch accounts, target 18 sets/day by day 30, indicator five office visits and three samples per week. Priority 2: raise average order value from RM12 to RM14 by adding a drink bundle, indicator bundle take-up each Friday. Stop weekend market stall for 30 days.",
         }),
         "reviewed",
         json.dumps({"customer_clarity": 3, "differentiation": 3, "numbers": 4, "execution": 3}),
         3.25, 1,
         "Clear customer and solid arithmetic. Sharpen the value proposition by naming one concrete proof point (e.g. average wait time).",
         iso(now - timedelta(days=8)), iso(now - timedelta(days=6))),
    )

    plan = [
        ("Write a one-page business model", "Customer, promise, channels, revenue, direct costs, fixed costs on one page.", 1),
        ("Calculate break-even for lunch sets", "RM1,650 fixed costs ÷ RM5.50 contribution = 300 sets a month.", 1),
        ("Book a Friday 20-minute weekly review", "Check repeat orders and corporate account progress every Friday.", 0),
        ("Draft two corporate lunch offers", "One trial offer for offices within 1km; include delivery and a fixed monthly price.", 0),
    ]
    for i, (title, detail, done) in enumerate(plan):
        conn.execute(
            "INSERT INTO plan_items (user_id, title, detail, due, done, created_at, completed_at) VALUES (?,?,?,?,?,?,?)",
            (learner, title, detail, (now + timedelta(days=7 * (i + 1))).date().isoformat(), done,
             iso(now - timedelta(days=17 - i)), iso(now - timedelta(days=10)) if done else None),
        )
    conn.commit()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (key, value))
        seed_questions(conn)
        seed_demo(conn)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def settings_public(conn):
    s = get_settings(conn)
    return {
        "quiz_pass": int(s.get("quiz_pass", 80)),
        "scenario_pass": int(s.get("scenario_pass", 70)),
        "rubric_min": float(s.get("rubric_min", 3)),
        "rubric_floor": int(s.get("rubric_floor", 2)),
        "platform_name": s.get("platform_name", "BizReady"),
    }


def public_user(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"], "created_at": row["created_at"]}


def create_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, iso(now), iso(now + timedelta(days=SESSION_DAYS))),
    )
    conn.commit()
    return token


def current_user(conn, handler):
    cookie = SimpleCookie()
    try:
        cookie.load(handler.headers.get("Cookie", ""))
    except Exception:
        return None
    morsel = cookie.get("br_session")
    if not morsel:
        return None
    row = conn.execute(
        "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (morsel.value,),
    ).fetchone()
    if not row:
        return None
    try:
        exp = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if exp < utcnow():
            conn.execute("DELETE FROM sessions WHERE token = ?", (morsel.value,))
            conn.commit()
            return None
    except Exception:
        return None
    return row


def require_user(conn, handler):
    user = current_user(conn, handler)
    if not user:
        raise ApiError(401, "Please sign in to continue.")
    return user


def require_admin(conn, handler):
    user = require_user(conn, handler)
    if user["role"] != "admin":
        raise ApiError(403, "Administrator access required.")
    return user


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def clean_text(value, max_len=5000, field="value"):
    if not isinstance(value, str):
        raise ApiError(400, f"{field} must be text.")
    value = value.strip()
    if len(value) > max_len:
        raise ApiError(400, f"{field} is too long.")
    return value


def get_module_content(conn):
    module = deepcopy(content.MODULE)
    overrides = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM content_overrides").fetchall()}
    for lesson in module["lessons"]:
        for field in ("title", "summary", "explanation"):
            key = f"lesson:{lesson['id']}:{field}"
            if key in overrides:
                lesson[field] = overrides[key].split("\n\n") if field == "explanation" else overrides[key]
    if "module:tagline" in overrides:
        module["tagline"] = overrides["module:tagline"]
    if "module:intro" in overrides:
        module["intro"] = overrides["module:intro"].split("\n\n")
    return module


# ---------------------------------------------------------------------------
# Scoring and progress
# ---------------------------------------------------------------------------

def mcq_rows(conn, kind):
    return conn.execute(
        "SELECT * FROM questions WHERE kind = ? AND active = 1 ORDER BY position, id", (kind,)
    ).fetchall()


def score_answers(questions, answers):
    detail = []
    correct = 0
    for q in questions:
        raw = answers.get(str(q["id"]), answers.get(q["id"]))
        try:
            chosen = int(raw)
        except (TypeError, ValueError):
            chosen = None
        ok = chosen == q["correct"]
        if ok:
            correct += 1
        detail.append({
            "id": q["id"],
            "prompt": q["prompt"],
            "options": json.loads(q["options"]),
            "chosen": chosen,
            "correct": q["correct"],
            "is_correct": ok,
            "explanation": q["explanation"],
            "topic": q["topic"],
        })
    total = len(questions)
    score = round(correct / total * 100) if total else 0
    return score, detail, correct, total


def diagnostic_summary(conn, user_id):
    row = conn.execute(
        "SELECT * FROM diagnostic_results WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    if not row:
        return None
    return {
        "overall": row["overall"],
        "components": json.loads(row["component_scores"]),
        "created_at": row["created_at"],
    }


def practical_latest(conn, user_id):
    row = conn.execute(
        "SELECT * FROM practical_submissions WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "responses": json.loads(row["responses"]),
        "status": row["status"],
        "rubric": json.loads(row["rubric"]) if row["rubric"] else None,
        "average": row["average"],
        "passed": bool(row["passed"]),
        "reviewer_note": row["reviewer_note"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
    }


def best_attempt(conn, user_id, kind):
    rows = conn.execute(
        "SELECT * FROM attempts WHERE user_id = ? AND kind = ? ORDER BY score DESC, id DESC", (user_id, kind)
    ).fetchall()
    if not rows:
        return None
    best = rows[0]
    return {
        "score": best["score"],
        "passed": bool(best["passed"]),
        "attempts": len(rows),
        "last_at": rows[0]["created_at"],
    }


def module_state(conn, user_id):
    s = settings_public(conn)
    lessons = content.MODULE["lessons"]
    done_rows = conn.execute(
        "SELECT lesson_id FROM lesson_progress WHERE user_id = ?", (user_id,)
    ).fetchall()
    done = {r["lesson_id"] for r in done_rows}
    lessons_done = len([l for l in lessons if l["id"] in done])
    quiz = best_attempt(conn, user_id, "quiz")
    scenario = best_attempt(conn, user_id, "scenario")
    practical = practical_latest(conn, user_id)

    quiz_passed = bool(quiz and quiz["passed"])
    scenario_passed = bool(scenario and scenario["passed"])
    practical_passed = bool(practical and practical["passed"])
    module_passed = quiz_passed and scenario_passed and practical_passed

    percent = (
        (lessons_done / len(lessons)) * 20
        + (30 if quiz_passed else 0)
        + (25 if scenario_passed else 0)
        + (25 if practical_passed else 0)
    )
    return {
        "id": "strategy",
        "lessons_done": lessons_done,
        "lessons_total": len(lessons),
        "quiz": quiz,
        "scenario": scenario,
        "practical": practical,
        "quiz_passed": quiz_passed,
        "scenario_passed": scenario_passed,
        "practical_passed": practical_passed,
        "passed": module_passed,
        "percent": round(percent),
        "standards": {"quiz_pass": s["quiz_pass"], "scenario_pass": s["scenario_pass"], "rubric_min": s["rubric_min"]},
    }


def mastery_level(score):
    if score is None:
        return "Not assessed"
    if score >= 85:
        return "Optimising"
    if score >= 70:
        return "Structured"
    if score >= 50:
        return "Developing"
    return "Beginner"


def build_progress(conn, user):
    uid = user["id"]
    diag = diagnostic_summary(conn, uid)
    profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (uid,)).fetchone()
    mod = module_state(conn, uid)
    plan_rows = conn.execute("SELECT * FROM plan_items WHERE user_id = ? ORDER BY done, id", (uid,)).fetchall()
    plan = [dict(r) for r in plan_rows]
    plan_done = len([p for p in plan if p["done"]])
    plan_fraction = (plan_done / len(plan)) if plan else 0

    overall = 0
    if profile:
        overall += 10
    if diag:
        overall += 20
    overall += (mod["lessons_done"] / mod["lessons_total"]) * 15
    if mod["quiz_passed"]:
        overall += 20
    if mod["scenario_passed"]:
        overall += 15
    if mod["practical_passed"]:
        overall += 15
    overall += plan_fraction * 5
    overall = round(overall)

    if mod["passed"]:
        practical_avg = (mod["practical"] or {}).get("average") or 0
        quiz_score = (mod["quiz"] or {}).get("score") or 0
        level = "Optimising" if (quiz_score >= 90 and practical_avg >= 3.5 and plan_done >= 2) else "Structured"
        basis = "Verified module results"
    elif mod["quiz_passed"] or mod["scenario_passed"] or (mod["practical"] and mod["practical"]["status"] == "reviewed"):
        level = "Developing"
        basis = "Partial assessment results"
    elif diag:
        level = "Beginner"
        basis = "Diagnostic only — no module assessment passed yet"
    else:
        level = "Not assessed"
        basis = "No verified assessment yet"

    components = []
    for comp in content.COMPONENTS:
        score = (diag or {}).get("components", {}).get(comp["id"])
        status = "not-started"
        source = None
        level_c = "Not assessed"
        if comp["id"] == "strategy" and mod["passed"]:
            status = "passed"
            level_c = "Optimising" if level == "Optimising" else "Structured"
            source = "Module verified"
        elif comp["id"] == "strategy" and (mod["quiz_passed"] or mod["scenario_passed"]):
            status = "in-progress"
            level_c = "Developing"
            source = "Partial module results"
        elif score is not None:
            status = "diagnostic"
            source = "Diagnostic only — module not assessed"
        components.append({
            "id": comp["id"], "name": comp["name"], "short": comp["short"],
            "available": comp["available"], "score": score, "status": status,
            "mastery": level_c, "source": source,
        })

    attempts = [
        dict(r) for r in conn.execute(
            "SELECT kind, component, score, passed, created_at FROM attempts WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (uid,),
        ).fetchall()
    ]
    for a in attempts:
        a["passed"] = bool(a["passed"])

    next_steps = []
    if not profile:
        next_steps.append({"title": "Create your business profile", "detail": "Five questions so the platform can tailor your results.", "route": "checkup"})
    if not diag:
        next_steps.append({"title": "Take the 24-question Business Check-Up", "detail": "Identify strengths and weaknesses across all eight areas.", "route": "checkup"})
    if mod["lessons_done"] < mod["lessons_total"]:
        nxt = mod["lessons_done"] + 1
        next_steps.append({"title": f"Continue lesson {nxt} of {mod['lessons_total']}", "detail": "About 10 minutes, with a practical exercise.", "route": "module"})
    if not mod["quiz_passed"]:
        next_steps.append({"title": "Pass the knowledge quiz", "detail": f"Score {mod['standards']['quiz_pass']}% or higher. Retries are unlimited.", "route": "test"})
    if not mod["scenario_passed"]:
        next_steps.append({"title": "Try the scenario test", "detail": f"Five real-world decisions; pass mark {mod['standards']['scenario_pass']}%.", "route": "test"})
    if not mod["practical"]:
        next_steps.append({"title": "Submit the practical assignment", "detail": "Apply the module to your own business.", "route": "test"})
    elif mod["practical"]["status"] == "pending":
        next_steps.append({"title": "Practical assignment awaiting review", "detail": "A reviewer will score it against the rubric.", "route": "test"})
    elif mod["practical"]["status"] == "reviewed" and not mod["practical"]["passed"]:
        next_steps.append({"title": "Revise the practical assignment", "detail": "Read the reviewer note and resubmit.", "route": "test"})
    if mod["passed"] and len(next_steps) == 0:
        next_steps.append({"title": "Turn results into action", "detail": "Pick one item in your action plan and finish it this week.", "route": "progress"})

    return {
        "user": public_user(user),
        "profile": dict(profile) if profile else None,
        "diagnostic": diag,
        "module": mod,
        "overall_percent": overall,
        "mastery": {"level": level, "basis": basis},
        "components": components,
        "attempts": attempts,
        "plan": plan,
        "plan_done": plan_done,
        "next_steps": next_steps,
        "settings": settings_public(conn),
        "ai": ai_status(),
    }


# ---------------------------------------------------------------------------
# AI coach
# ---------------------------------------------------------------------------

def ai_status():
    cfg = load_ai_config()
    configured = bool(cfg.get("api_key"))
    return {"configured": configured, "mode": "live" if configured else "demo", "model": cfg.get("model", "")}


def load_ai_config():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("ai", {})
        except Exception:
            cfg = {}
    env_key = os.environ.get("BIZREADY_AI_KEY", "").strip()
    if env_key:
        cfg["api_key"] = env_key
    cfg.setdefault("base_url", os.environ.get("BIZREADY_AI_BASE_URL", "https://api.openai.com/v1"))
    cfg.setdefault("model", os.environ.get("BIZREADY_AI_MODEL", "gpt-4o-mini"))
    cfg.setdefault("provider", "openai")
    return cfg


COACH_SYSTEM = {
    "teach": "You are BizReady's business coach for micro and small businesses. Teach one concept at a time in simple language. Use headings: Simple explanation, Example, What to do, What not to do, Why it matters, Your next step. Use a food, online-selling or service business example. Keep under 280 words and end with one question.",
    "solve": "You are BizReady's business coach. Diagnose the owner's real problem before prescribing. Ask at most two clarifying questions, list likely causes, then give numbered practical steps with the reasoning. Use simple language, reference their business type, and avoid generic advice. Keep under 300 words.",
    "test": "You are BizReady's business coach running a short knowledge check. Ask one multiple-choice question with three options (A, B, C), wait for the answer, then explain why the correct answer is right. Do not reveal the answer before they respond.",
}


def ai_chat(mode, messages):
    cfg = load_ai_config()
    key = (cfg.get("api_key") or "").strip()
    if not key:
        return None, "not_configured"
    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": cfg.get("model", "gpt-4o-mini"),
        "temperature": 0.4,
        "max_tokens": 650,
        "messages": [{"role": "system", "content": COACH_SYSTEM[mode]}]
        + [{"role": m["role"], "content": m["content"]} for m in messages[-8:]],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        return text, None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, str(exc)[:200]


COACH_TOPICS = {
    "pricing": {
        "keys": ["price", "pricing", "discount", "cheap", "margin", "cost", "raise price", "profit", "revenue"],
        "simple": "Price is not a number you copy from competitors. It is a decision about which customers you want, what you promise them, and what margin you need to keep the business healthy.",
        "example": "A home baker sells 60 cakes at RM45 with RM22 direct cost. Contribution is RM23. A café offers to buy 40 at RM32 — contribution falls to RM10, and the extra volume uses her only oven. The order looks big but leaves less money per hour of work.",
        "do": ["Calculate contribution per sale before and after any price change.", "Know your break-even volume.", "Test a new price with a small group or one product first.", "Explain the value, not just the number, when you raise a price."],
        "dont": ["Do not discount to win a customer you cannot serve profitably.", "Do not match a competitor without knowing their cost base.", "Do not raise prices and quietly reduce quality."],
        "why": "Small businesses usually have less room for error than large ones. A 10% price cut can require 50% more volume to stand still; knowing that prevents a slow, invisible loss.",
        "next": "Calculate contribution for your best-selling offer, then tell me the price, direct cost and monthly fixed costs — I will help you find your break-even.",
    },
    "cash": {
        "keys": ["cash", "cashflow", "cash flow", "late payment", "supplier", "owe", "loan", "run out"],
        "simple": "Profit is what is left after costs. Cash is what is in the bank today. You can be profitable and still unable to pay wages next Friday if customers pay late or you hold too much stock.",
        "example": "A caterer wins a RM24,000 contract, buys RM9,000 of stock, and is paid 45 days later. The job is profitable, but for six weeks the business is funding the client. Two late invoices at once can stop the whole operation.",
        "do": ["Forecast cash weekly for the next 13 weeks.", "Invoice immediately and state payment terms clearly.", "Collect deposits for large or custom orders.", "Negotiate supplier terms before you need them."],
        "dont": ["Do not use next month's customer deposits for this month's costs.", "Do not assume a signed contract means money is available.", "Do not hide a shortfall from yourself or your suppliers."],
        "why": "Cash problems close businesses faster than bad ideas. A short, honest forecast gives you time to act while options still exist.",
        "next": "List money coming in and going out for the next four weeks. If there is a gap, tell me the amounts and I will help you sequence the options.",
    },
    "customers": {
        "keys": ["customer", "marketing", "sales", "social media", "advert", "promote", "enquir", "audience"],
        "simple": "Marketing works when a specific person recognises a specific problem in your message. A clear customer, a clear offer and one channel you can measure beats being everywhere.",
        "example": "A tuition centre posts general 'enrol now' flyers with no response. It switches to a two-week 'exam readiness check' for parents of Form 5 students, promoted in two parent groups and followed by a WhatsApp call. Ten bookings come from 30 enquiries.",
        "do": ["Choose one primary customer group and one problem.", "Make one clear offer with a next step.", "Use one or two channels you can measure.", "Follow up within 24 hours."],
        "dont": ["Do not target everyone.", "Do not count likes as sales.", "Do not run several offers at once with no way to compare them."],
        "why": "Small budgets cannot afford vague marketing. Specific offers produce measurable responses, which let you improve instead of guessing.",
        "next": "Tell me your best-selling offer and who buys it most often. I will help you write one offer and choose a channel to test for two weeks.",
    },
    "staff": {
        "keys": ["staff", "employee", "team", "hire", "worker", "roster", "salary", "people"],
        "simple": "Most small-team problems are clarity problems before they are attitude problems. People need to know what good looks like, what they can decide, and what happens when something goes wrong.",
        "example": "A café owner complains that staff are 'not proactive'. The real issue: nobody has written down the opening checklist. A one-page checklist and a 15-minute handover cut missed tasks within a week.",
        "do": ["Write one page per role: tasks, standards, decisions.", "Train once, then observe and coach.", "Give feedback close to the event, in private.", "Review workload before assuming low effort."],
        "dont": ["Do not rely on hints or hope.", "Do not apply rules differently to different people.", "Do not add tasks without removing something."],
        "why": "Consistency protects quality and fairness. Clear standards also make it easier to reward good work and address poor work without guesswork.",
        "next": "Pick your most repeated task and write the steps someone else would need. Send them here and I will help you tighten the checklist.",
    },
    "operations": {
        "keys": ["operation", "process", "quality", "queue", "delay", "waste", "mistake", "stock", "inventory", "supplier"],
        "simple": "Operations is the repeatable path from customer request to delivery. When something goes wrong repeatedly, look for a missing standard, a missing check, or a capacity mismatch — not a person to blame.",
        "example": "A laundry service loses garments during pickup. Mapping the flow shows three handover points with no count. Adding a counted handover at each point removes almost all losses without new staff.",
        "do": ["Map the process on one page.", "Find the two points where errors occur.", "Add a simple check or count at those points.", "Measure the error rate for two weeks."],
        "dont": ["Do not add staff to fix a process problem.", "Do not write a 30-page manual nobody uses.", "Do not hide errors — log them so you can fix causes."],
        "why": "Reliable delivery protects repeat business and reduces costly rework. Simple checks are usually more effective than more people or more software.",
        "next": "Describe the step where mistakes happen most often, and what happens just before and after it. I will help you design one check.",
    },
    "online": {
        "keys": ["online", "website", "shopee", "tiktok", "ecommerce", "delivery app", "digital", "whatsapp"],
        "simple": "Selling online adds a channel, not a new business. The test is whether each order contributes after platform fees, delivery, packaging and returns — and whether customers come back.",
        "example": "An online seller makes RM28 revenue per order. Platform fee RM4, delivery RM6, packaging RM1.50, product RM9 → contribution RM7.50. Ads cost RM9 per order, so growth is losing money until repeat orders improve.",
        "do": ["Start with one channel.", "Track contribution after all fees.", "Measure repeat orders and cost per order.", "Use simple tools you will actually maintain."],
        "dont": ["Do not build an app before proving demand.", "Do not scale ads on a negative contribution.", "Do not store customer details in unsafe spreadsheets."],
        "why": "Digital channels make costs visible and comparable. That is their real advantage — not novelty.",
        "next": "Tell me your average order value and the fees you pay per order. I will help you calculate real online contribution.",
    },
    "growth": {
        "keys": ["grow", "growth", "expand", "second branch", "scale", "new product", "invest"],
        "simple": "Growth is a set of tested bets, not one big leap. The safest next step is the one that uses existing customers, existing skills and a measurable amount of money.",
        "example": "A florist wants a second outlet. Before signing a lease, she tests corporate weekly flowers for nearby offices. Three accounts cover 40% of the new rent, which lowers the risk of the larger commitment.",
        "do": ["Test demand before committing fixed costs.", "Use existing customers first.", "Set a stop rule before you start.", "Protect core service quality while testing."],
        "dont": ["Do not grow a model that is not profitable yet.", "Do not add fixed costs on optimism.", "Do not chase every opportunity that appears."],
        "why": "Fixed costs are hard to reverse. Small tests give you evidence at a fraction of the risk.",
        "next": "Tell me the growth idea and the fixed cost it requires. We will design a 30-day test with a clear stop rule.",
    },
    "general": {
        "keys": [],
        "simple": "Most business problems become manageable when you separate three things: the customer and promise, the numbers, and the process that delivers it. Fix the area with the clearest evidence first.",
        "example": "A small catering business feels 'busy but broke'. Sales are up 20%, but two large clients pay in 60 days and the menu added six low-margin items. Trimming the menu and invoicing earlier fixes more than another marketing push.",
        "do": ["Describe the problem in one sentence with numbers.", "Identify which of the three areas it sits in.", "Choose one small change and a way to measure it.", "Review after two weeks."],
        "dont": ["Do not change five things at once.", "Do not treat a cash problem as a sales problem by default.", "Do not skip the measurement step."],
        "why": "A structured diagnosis prevents expensive guessing and makes each decision a little more evidence-based than the last.",
        "next": "Tell me what is happening, what you have tried, and one number involved. I will help you narrow it down.",
    },
}


def detect_topic(text):
    low = text.lower()
    best = ("general", 0)
    for name, data in COACH_TOPICS.items():
        hits = sum(1 for k in data["keys"] if k in low)
        if hits > best[1]:
            best = (name, hits)
    return best[0]


TEST_BANK = [
    {"q": "A business sells 200 units at RM25. Variable cost is RM15 per unit and fixed costs are RM1,200. What is its profit?",
     "options": ["RM800", "RM2,000", "RM1,200"], "correct": 0,
     "explain": "Contribution is RM10 × 200 = RM2,000, minus RM1,200 fixed costs = RM800 profit."},
    {"q": "Which of these is a leading indicator for a small café?",
     "options": ["Monthly profit", "Repeat customers per week", "Last year's revenue"], "correct": 1,
     "explain": "Repeat customers per week moves early enough to act on. Profit and last year's revenue arrive too late."},
    {"q": "A supplier offers a 60-day payment term you cannot meet. What is the best response?",
     "options": ["Sign and pay late quietly", "Negotiate the term before signing", "Ignore the contract"], "correct": 1,
     "explain": "Negotiating before signing protects the relationship and avoids a cash crisis later."},
]


def demo_coach(mode, messages):
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    prefix = "**Demo mode** — scripted guidance, not a live AI. Connect an API key on the server for personalised coaching.\n\n"

    if mode == "test":
        prior_assistant = [m["content"] for m in messages if m["role"] == "assistant"]
        if prior_assistant:
            last = prior_assistant[-1]
            match = re.search(r"\[Q(\d+)\]", last)
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(TEST_BANK):
                    item = TEST_BANK[idx]
                    ans = last_user.strip().upper()
                    letter = re.match(r"^\(?([ABC])", ans)
                    picked = "ABC".index(letter.group(1)) if letter else None
                    if picked is None:
                        for i, opt in enumerate(item["options"]):
                            if opt.lower() in last_user.lower():
                                picked = i
                    if picked is None:
                        return prefix + "I did not catch which option you chose. Reply with **A**, **B** or **C**."
                    if picked == item["correct"]:
                        return prefix + f"**Correct.** {item['explain']}\n\nThat is the kind of reasoning the scenario test checks. Want another question, or shall we apply it to your business?"
                    return prefix + f"**Not quite.** The best answer is **{'ABC'[item['correct']]}** — {item['options'][item['correct']]}.\n\n{item['explain']}\n\nWant to try another one?"
        item_idx = len([m for m in messages if m["role"] == "assistant"]) % len(TEST_BANK)
        item = TEST_BANK[item_idx]
        opts = "\n".join(f"**{'ABC'[i]}.** {o}" for i, o in enumerate(item["options"]))
        return prefix + f"[Q{item_idx + 1}] {item['q']}\n\n{opts}\n\nReply with A, B or C and I will explain."

    topic = detect_topic(last_user)
    data = COACH_TOPICS[topic]
    if mode == "teach":
        reply = (
            f"**Simple explanation**\n{data['simple']}\n\n"
            f"**Example**\n{data['example']}\n\n"
            f"**What to do**\n" + "\n".join(f"• {x}" for x in data["do"]) + "\n\n"
            f"**What not to do**\n" + "\n".join(f"• {x}" for x in data["dont"]) + "\n\n"
            f"**Why it matters**\n{data['why']}\n\n"
            f"**Your next step**\n{data['next']}"
        )
    else:
        reply = (
            "**Let's diagnose it before prescribing**\n"
            "To give you something useful rather than generic advice, I need two details:\n"
            "1. What exactly happens, and when?\n"
            "2. What one number is involved (sales, cost, margin, hours, customers)?\n\n"
            f"**Likely causes**\n{data['simple']}\n\n"
            f"**What I would check, in order**\n" + "\n".join(f"{i+1}. {x}" for i, x in enumerate(data["do"])) + "\n\n"
            f"**What to avoid**\n" + "\n".join(f"• {x}" for x in data["dont"]) + "\n\n"
            f"**Why this order**\n{data['why']}\n\n"
            f"**Do this next**\n{data['next']}"
        )
    return prefix + reply


def coach_endpoint(messages, mode):
    if mode not in ("teach", "solve", "test"):
        raise ApiError(400, "Unknown coach mode.")
    cleaned = []
    for m in messages[-12:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        text = m.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        cleaned.append({"role": m["role"], "content": text.strip()[:4000]})
    if not cleaned or cleaned[-1]["role"] != "user":
        raise ApiError(400, "Send a message to the coach.")

    text, err = ai_chat(mode, cleaned)
    if text:
        return {"reply": text, "demo": False, "ai_error": None}
    if err == "not_configured":
        return {"reply": demo_coach(mode, cleaned), "demo": True, "ai_error": None}
    fallback = "The live AI request failed, so this is demo guidance instead.\n\n" + demo_coach(mode, cleaned)
    return {"reply": fallback, "demo": True, "ai_error": err}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

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
    server_version = "BizReady/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("BIZREADY_QUIET") != "1":
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- low level ---------------------------------------------------------
    def send_json(self, obj, status=200, cookie=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, data, ctype, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "Request too large.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            raise ApiError(400, "Invalid JSON body.")
        if not isinstance(data, dict):
            raise ApiError(400, "JSON body must be an object.")
        return data

    def serve_static(self, path):
        if path in ("/", "/index.html"):
            file = STATIC_DIR / "index.html"
        elif path.startswith("/static/"):
            rel = unquote(path[len("/static/"):])
            file = (STATIC_DIR / rel).resolve()
            if STATIC_DIR.resolve() not in file.parents:
                raise ApiError(404, "Not found.")
        else:
            raise ApiError(404, "Not found.")
        if not file.is_file():
            raise ApiError(404, "Not found.")
        data = file.read_bytes()
        ctype = MIME.get(file.suffix.lower(), "application/octet-stream")
        if file.suffix.lower() in (".html", ".css", ".js"):
            extra = {"Cache-Control": "no-cache"}
        else:
            extra = {"Cache-Control": "public, max-age=3600"}
        self.send_bytes(data, ctype, extra=extra)

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
                self.handle_api(method, path, parse_qs(parsed.query))
            elif method == "GET":
                self.serve_static(path)
            else:
                raise ApiError(404, "Not found.")
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            try:
                self.send_json({"error": "Something went wrong on the server."}, 500)
            except Exception:
                pass

    # -- api ---------------------------------------------------------------
    def handle_api(self, method, path, query):
        conn = get_db()
        try:
            self.route(conn, method, path, query)
        finally:
            conn.close()

    def route(self, conn, method, path, query):
        # Auth -----------------------------------------------------------------
        if path == "/api/auth/register" and method == "POST":
            body = self.read_json()
            name = clean_text(body.get("name"), 80, "Name")
            email = clean_text(body.get("email"), 200, "Email").lower()
            password = body.get("password") or ""
            if len(name) < 2:
                raise ApiError(400, "Please enter your name.")
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                raise ApiError(400, "Please enter a valid email address.")
            if not isinstance(password, str) or len(password) < 8:
                raise ApiError(400, "Password must be at least 8 characters.")
            if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                raise ApiError(409, "An account with that email already exists.")
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                (name, email, hash_password(password), "learner", iso()),
            )
            user_id = cur.lastrowid
            conn.commit()
            token = create_session(conn, user_id)
            cookie = f"br_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS*86400}"
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self.send_json({"user": public_user(user), "progress": build_progress(conn, user)}, 201, cookie)

        if path == "/api/auth/login" and method == "POST":
            body = self.read_json()
            email = (body.get("email") or "").strip().lower()
            password = body.get("password") or ""
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise ApiError(401, "Email or password is incorrect.")
            token = create_session(conn, row["id"])
            cookie = f"br_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS*86400}"
            return self.send_json({"user": public_user(row), "progress": build_progress(conn, row)}, 200, cookie)

        if path == "/api/auth/logout" and method == "POST":
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            morsel = cookie.get("br_session")
            if morsel:
                conn.execute("DELETE FROM sessions WHERE token = ?", (morsel.value,))
                conn.commit()
            return self.send_json({"ok": True}, 200, "br_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")

        if path == "/api/bootstrap" and method == "GET":
            user = current_user(conn, self)
            data = {
                "components": content.COMPONENTS,
                "settings": settings_public(conn),
                "ai": ai_status(),
                "user": public_user(user) if user else None,
            }
            if user:
                data["progress"] = build_progress(conn, user)
            return self.send_json(data)

        # Authenticated ---------------------------------------------------------
        user = require_user(conn, self)

        if path == "/api/me" and method == "GET":
            return self.send_json({"user": public_user(user), "progress": build_progress(conn, user)})

        if path == "/api/profile" and method == "PUT":
            body = self.read_json()
            fields = {}
            limits = {"business_name": 100, "sector": 60, "stage": 40, "team_size": 20,
                      "revenue_band": 40, "years": 20, "main_challenge": 600}
            for key, limit in limits.items():
                val = clean_text(body.get(key, ""), limit, key.replace("_", " ").title())
                if not val:
                    raise ApiError(400, "Please complete all profile fields.")
                fields[key] = val
            conn.execute(
                "INSERT INTO profiles (user_id, business_name, sector, stage, team_size, revenue_band, years, main_challenge, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET"
                " business_name=excluded.business_name, sector=excluded.sector, stage=excluded.stage,"
                " team_size=excluded.team_size, revenue_band=excluded.revenue_band, years=excluded.years,"
                " main_challenge=excluded.main_challenge, updated_at=excluded.updated_at",
                (user["id"], fields["business_name"], fields["sector"], fields["stage"], fields["team_size"],
                 fields["revenue_band"], fields["years"], fields["main_challenge"], iso()),
            )
            conn.commit()
            return self.send_json({"ok": True, "progress": build_progress(conn, user)})

        if path == "/api/checkup" and method == "GET":
            rows = mcq_rows(conn, "diagnostic")
            questions = [{
                "id": r["id"], "component": r["component"], "topic": r["topic"], "prompt": r["prompt"],
                "options": json.loads(r["options"]),
            } for r in rows]
            return self.send_json({
                "questions": questions,
                "profile": dict(conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],)).fetchone() or {}) or None,
                "result": diagnostic_summary(conn, user["id"]),
            })

        if path == "/api/checkup/submit" and method == "POST":
            body = self.read_json()
            answers = body.get("answers")
            if not isinstance(answers, dict):
                raise ApiError(400, "Answers must be an object.")
            rows = mcq_rows(conn, "diagnostic")
            if not rows:
                raise ApiError(400, "No diagnostic questions are available.")
            score, detail, correct, total = score_answers(rows, answers)
            per = {}
            counts = {}
            for d in detail:
                comp = next(r["component"] for r in rows if r["id"] == d["id"])
                counts.setdefault(comp, [0, 0])
                counts[comp][1] += 1
                if d["is_correct"]:
                    counts[comp][0] += 1
            for comp, (c, t) in counts.items():
                per[comp] = round(c / t * 100) if t else 0
            cur = conn.execute(
                "INSERT INTO diagnostic_results (user_id, answers, component_scores, overall, created_at) VALUES (?,?,?,?,?)",
                (user["id"], json.dumps(answers), json.dumps(per), score, iso()),
            )
            # Seed a starting action plan from the three weakest areas, once.
            if not conn.execute("SELECT id FROM plan_items WHERE user_id = ?", (user["id"],)).fetchone():
                weakest = sorted(per.items(), key=lambda kv: kv[1])[:3]
                for comp_id, comp_score in weakest:
                    comp = content.COMPONENT_BY_ID[comp_id]
                    conn.execute(
                        "INSERT INTO plan_items (user_id, title, detail, due, done, created_at) VALUES (?,?,?,?,?,?)",
                        (user["id"],
                         f"Improve {comp['name'].lower()}",
                         content.DIAGNOSTIC_RECOMMENDATIONS[comp_id],
                         (utcnow() + timedelta(days=14)).date().isoformat(), 0, iso()),
                    )
            conn.commit()
            result = diagnostic_summary(conn, user["id"])
            priorities = sorted(per.items(), key=lambda kv: kv[1])[:3]
            strengths = sorted(per.items(), key=lambda kv: kv[1], reverse=True)[:2]
            return self.send_json({
                "result": result,
                "score": score,
                "correct": correct,
                "total": total,
                "priorities": [{"component": c, "name": content.COMPONENT_BY_ID[c]["name"],
                                "score": s, "recommendation": content.DIAGNOSTIC_RECOMMENDATIONS[c],
                                "available": content.COMPONENT_BY_ID[c]["available"]} for c, s in priorities],
                "strengths": [{"component": c, "name": content.COMPONENT_BY_ID[c]["name"], "score": s} for c, s in strengths],
                "progress": build_progress(conn, user),
            })

        if path == "/api/module/strategy" and method == "GET":
            module = get_module_content(conn)
            rows = conn.execute("SELECT lesson_id FROM lesson_progress WHERE user_id = ?", (user["id"],)).fetchall()
            done = [r["lesson_id"] for r in rows]
            return self.send_json({
                "module": module,
                "lessons_done": done,
                "state": module_state(conn, user["id"]),
            })

        if path.startswith("/api/module/strategy/lesson/") and path.endswith("/complete") and method == "POST":
            lesson_id = path[len("/api/module/strategy/lesson/"):-len("/complete")].strip("/")
            if lesson_id not in [l["id"] for l in content.MODULE["lessons"]]:
                raise ApiError(404, "Lesson not found.")
            conn.execute(
                "INSERT OR REPLACE INTO lesson_progress (user_id, lesson_id, completed_at) VALUES (?,?,?)",
                (user["id"], lesson_id, iso()),
            )
            conn.commit()
            return self.send_json({"ok": True, "state": module_state(conn, user["id"])})

        if path.startswith("/api/assessment/") and path.endswith("/questions") and method == "GET":
            kind = path[len("/api/assessment/"):-len("/questions")].strip("/")
            if kind not in ("quiz", "scenario"):
                raise ApiError(404, "Assessment not found.")
            rows = mcq_rows(conn, kind)
            s = settings_public(conn)
            history = [dict(r) for r in conn.execute(
                "SELECT score, passed, created_at FROM attempts WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT 10",
                (user["id"], kind)).fetchall()]
            for h in history:
                h["passed"] = bool(h["passed"])
            return self.send_json({
                "kind": kind,
                "questions": [{"id": r["id"], "component": r["component"], "topic": r["topic"],
                               "prompt": r["prompt"], "options": json.loads(r["options"])} for r in rows],
                "pass_mark": s["quiz_pass"] if kind == "quiz" else s["scenario_pass"],
                "history": history,
            })

        if path.startswith("/api/assessment/") and path.endswith("/submit") and method == "POST":
            kind = path[len("/api/assessment/"):-len("/submit")].strip("/")
            if kind not in ("quiz", "scenario"):
                raise ApiError(404, "Assessment not found.")
            body = self.read_json()
            answers = body.get("answers")
            if not isinstance(answers, dict):
                raise ApiError(400, "Answers must be an object.")
            rows = mcq_rows(conn, kind)
            if not rows:
                raise ApiError(400, "No questions are available.")
            score, detail, correct, total = score_answers(rows, answers)
            s = settings_public(conn)
            pass_mark = s["quiz_pass"] if kind == "quiz" else s["scenario_pass"]
            passed = score >= pass_mark
            conn.execute(
                "INSERT INTO attempts (user_id, kind, component, score, passed, detail, created_at) VALUES (?,?,?,?,?,?,?)",
                (user["id"], kind, "strategy", score, 1 if passed else 0,
                 json.dumps({"detail": detail, "correct": correct, "total": total}), iso()),
            )
            conn.commit()
            wrong = [{"id": d["id"], "prompt": d["prompt"], "topic": d["topic"], "explanation": d["explanation"]}
                     for d in detail if not d["is_correct"]]
            return self.send_json({
                "kind": kind, "score": score, "correct": correct, "total": total,
                "passed": passed, "pass_mark": pass_mark, "detail": detail, "wrong": wrong,
                "progress": build_progress(conn, user),
            })

        if path == "/api/practical" and method == "GET":
            return self.send_json({
                "practical": content.MODULE["practical"],
                "submission": practical_latest(conn, user["id"]),
                "standards": settings_public(conn),
            })

        if path == "/api/practical/submit" and method == "POST":
            body = self.read_json()
            responses = body.get("responses")
            if not isinstance(responses, dict):
                raise ApiError(400, "Responses must be an object.")
            cleaned = {}
            for p in content.MODULE["practical"]["prompts"]:
                val = clean_text(responses.get(p["id"], ""), 4000, p["label"])
                if len(val) < 30:
                    raise ApiError(400, "Please give a fuller answer for every question (at least 30 characters).")
                cleaned[p["id"]] = val
            conn.execute(
                "INSERT INTO practical_submissions (user_id, responses, status, created_at) VALUES (?,?,?,?)",
                (user["id"], json.dumps(cleaned), "pending", iso()),
            )
            conn.commit()
            return self.send_json({
                "ok": True,
                "submission": practical_latest(conn, user["id"]),
                "message": "Submitted. A reviewer will score it against the rubric; your module is not marked passed until that review is complete.",
            }, 201)

        if path == "/api/progress" and method == "GET":
            return self.send_json(build_progress(conn, user))

        if path == "/api/plan" and method == "POST":
            body = self.read_json()
            title = clean_text(body.get("title"), 200, "Title")
            if len(title) < 4:
                raise ApiError(400, "Please give the action a clear title.")
            detail = clean_text(body.get("detail", ""), 1000, "Detail")
            due = clean_text(body.get("due", ""), 20, "Due date")
            if due and not re.match(r"^\d{4}-\d{2}-\d{2}$", due):
                raise ApiError(400, "Due date must be YYYY-MM-DD.")
            conn.execute(
                "INSERT INTO plan_items (user_id, title, detail, due, done, created_at) VALUES (?,?,?,?,0,?)",
                (user["id"], title, detail, due, iso()),
            )
            conn.commit()
            return self.send_json({"ok": True, "plan": [dict(r) for r in conn.execute(
                "SELECT * FROM plan_items WHERE user_id = ? ORDER BY done, id", (user["id"],)).fetchall()]}, 201)

        m = re.fullmatch(r"/api/plan/(\d+)", path)
        if m:
            item_id = int(m.group(1))
            row = conn.execute("SELECT * FROM plan_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
            if not row:
                raise ApiError(404, "Action not found.")
            if method == "PATCH":
                body = self.read_json()
                done = 1 if body.get("done") else 0
                detail = clean_text(body.get("detail", row["detail"]), 1000, "Detail")
                conn.execute(
                    "UPDATE plan_items SET done = ?, detail = ?, completed_at = ? WHERE id = ?",
                    (done, detail, iso() if done else None, item_id),
                )
                conn.commit()
                return self.send_json({"ok": True, "plan": [dict(r) for r in conn.execute(
                    "SELECT * FROM plan_items WHERE user_id = ? ORDER BY done, id", (user["id"],)).fetchall()]})
            if method == "DELETE":
                conn.execute("DELETE FROM plan_items WHERE id = ?", (item_id,))
                conn.commit()
                return self.send_json({"ok": True})

        if path == "/api/coach" and method == "POST":
            body = self.read_json()
            mode = body.get("mode", "teach")
            messages = body.get("messages") or []
            if not isinstance(messages, list):
                raise ApiError(400, "Messages must be a list.")
            result = coach_endpoint(messages, mode)
            return self.send_json(result)

        if path.startswith("/api/templates/") and method == "GET":
            slug = path[len("/api/templates/"):].strip("/")
            if slug not in content.TEMPLATE_FILES:
                raise ApiError(404, "Template not found.")
            meta = next((t for t in content.MODULE["templates"] if t["slug"] == slug), None)
            filename = meta["filename"] if meta else f"{slug}.txt"
            data = content.TEMPLATE_FILES[slug].encode("utf-8")
            return self.send_bytes(
                data, "text/plain; charset=utf-8",
                extra={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
            )

        # Admin -----------------------------------------------------------------
        if path.startswith("/api/admin/"):
            admin = require_admin(conn, self)
            if path == "/api/admin/overview" and method == "GET":
                learners = conn.execute(
                    "SELECT u.id, u.name, u.email, u.role, u.created_at, p.business_name, p.sector FROM users u"
                    " LEFT JOIN profiles p ON p.user_id = u.id WHERE u.role = 'learner' ORDER BY u.id"
                ).fetchall()
                out = []
                for l in learners:
                    prog = build_progress(conn, l)
                    out.append({
                        "id": l["id"], "name": l["name"], "email": l["email"],
                        "business_name": l["business_name"], "sector": l["sector"],
                        "overall_percent": prog["overall_percent"], "mastery": prog["mastery"]["level"],
                        "module_passed": prog["module"]["passed"],
                        "diagnostic": prog["diagnostic"]["overall"] if prog["diagnostic"] else None,
                        "practical_status": (prog["module"]["practical"] or {}).get("status"),
                        "created_at": l["created_at"],
                    })
                stats = {
                    "learners": len(out),
                    "profiles": conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0],
                    "diagnostics": conn.execute("SELECT COUNT(*) FROM diagnostic_results").fetchone()[0],
                    "passed": len([o for o in out if o["module_passed"]]),
                    "pending_reviews": conn.execute("SELECT COUNT(*) FROM practical_submissions WHERE status = 'pending'").fetchone()[0],
                }
                return self.send_json({"learners": out, "stats": stats})

            if path == "/api/admin/submissions" and method == "GET":
                rows = conn.execute(
                    "SELECT ps.*, u.name AS learner_name, u.email FROM practical_submissions ps"
                    " JOIN users u ON u.id = ps.user_id ORDER BY ps.status = 'reviewed', ps.id DESC"
                ).fetchall()
                submissions = []
                for r in rows:
                    submissions.append({
                        "id": r["id"], "learner": r["learner_name"], "email": r["email"],
                        "responses": json.loads(r["responses"]),
                        "status": r["status"], "rubric": json.loads(r["rubric"]) if r["rubric"] else None,
                        "average": r["average"], "passed": bool(r["passed"]),
                        "reviewer_note": r["reviewer_note"], "created_at": r["created_at"],
                        "reviewed_at": r["reviewed_at"],
                    })
                return self.send_json({"criteria": content.MODULE["practical"]["criteria"],
                                       "prompts": content.MODULE["practical"]["prompts"],
                                       "submissions": submissions,
                                       "standards": settings_public(conn)})

            m = re.fullmatch(r"/api/admin/submissions/(\d+)/review", path)
            if m and method == "POST":
                sub_id = int(m.group(1))
                row = conn.execute("SELECT * FROM practical_submissions WHERE id = ?", (sub_id,)).fetchone()
                if not row:
                    raise ApiError(404, "Submission not found.")
                body = self.read_json()
                scores = body.get("scores")
                if not isinstance(scores, dict):
                    raise ApiError(400, "Scores must be an object.")
                s = settings_public(conn)
                rubric = {}
                for crit in content.MODULE["practical"]["criteria"]:
                    try:
                        val = int(scores.get(crit["id"]))
                    except (TypeError, ValueError):
                        raise ApiError(400, "Every criterion needs a score from 0 to 4.")
                    if val < 0 or val > 4:
                        raise ApiError(400, "Every criterion needs a score from 0 to 4.")
                    rubric[crit["id"]] = val
                avg = round(sum(rubric.values()) / len(rubric), 2)
                passed = avg >= s["rubric_min"] and all(v >= s["rubric_floor"] for v in rubric.values())
                note = clean_text(body.get("note", ""), 1500, "Reviewer note")
                conn.execute(
                    "UPDATE practical_submissions SET status = 'reviewed', rubric = ?, average = ?, passed = ?,"
                    " reviewer_note = ?, reviewed_at = ? WHERE id = ?",
                    (json.dumps(rubric), avg, 1 if passed else 0, note, iso(), sub_id),
                )
                conn.commit()
                return self.send_json({"ok": True, "average": avg, "passed": passed, "standard": s["rubric_min"]})

            if path == "/api/admin/questions" and method == "GET":
                rows = conn.execute("SELECT * FROM questions ORDER BY kind, position, id").fetchall()
                return self.send_json({"questions": [{
                    "id": r["id"], "component": r["component"], "kind": r["kind"], "topic": r["topic"],
                    "prompt": r["prompt"], "options": json.loads(r["options"]), "correct": r["correct"],
                    "explanation": r["explanation"], "active": bool(r["active"]), "position": r["position"],
                } for r in rows], "components": content.COMPONENTS})

            if path == "/api/admin/questions" and method == "POST":
                body = self.read_json()
                item = self.validate_question(body, conn)
                position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM questions").fetchone()[0]
                qid = "q-" + secrets.token_hex(5)
                conn.execute(
                    "INSERT INTO questions (id, component, kind, topic, prompt, options, correct, explanation, active, position)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (qid, item["component"], item["kind"], item["topic"], item["prompt"],
                     json.dumps(item["options"]), item["correct"], item["explanation"], item["active"], position),
                )
                conn.commit()
                return self.send_json({"ok": True, "id": qid}, 201)

            qm = re.fullmatch(r"/api/admin/questions/([\w-]+)", path)
            if qm:
                qid = qm.group(1)
                row = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
                if not row:
                    raise ApiError(404, "Question not found.")
                if method == "PUT":
                    body = self.read_json()
                    item = self.validate_question(body, conn)
                    conn.execute(
                        "UPDATE questions SET component=?, kind=?, topic=?, prompt=?, options=?, correct=?,"
                        " explanation=?, active=? WHERE id=?",
                        (item["component"], item["kind"], item["topic"], item["prompt"], json.dumps(item["options"]),
                         item["correct"], item["explanation"], item["active"], qid),
                    )
                    conn.commit()
                    return self.send_json({"ok": True})
                if method == "DELETE":
                    conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
                    conn.commit()
                    return self.send_json({"ok": True})

            if path == "/api/admin/settings" and method == "PUT":
                body = self.read_json()
                values = {}
                for key, low, high in (("quiz_pass", 0, 100), ("scenario_pass", 0, 100),
                                       ("rubric_min", 0, 4), ("rubric_floor", 0, 4)):
                    try:
                        val = float(body.get(key))
                    except (TypeError, ValueError):
                        raise ApiError(400, "Passing standards must be numbers.")
                    if val < low or val > high:
                        raise ApiError(400, f"{key} must be between {low} and {high}.")
                    values[key] = str(int(val)) if key.endswith("pass") else str(round(val, 2))
                for key, val in values.items():
                    conn.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                 (key, val))
                conn.commit()
                return self.send_json({"ok": True, "settings": settings_public(conn)})

            if path == "/api/admin/content" and method == "GET":
                module = get_module_content(conn)
                overrides = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM content_overrides").fetchall()}
                return self.send_json({"module": module, "overrides": overrides})

            if path == "/api/admin/content" and method == "PUT":
                body = self.read_json()
                lesson_id = body.get("lesson_id")
                field = body.get("field")
                if field not in ("title", "summary", "explanation"):
                    raise ApiError(400, "Editable fields are title, summary and explanation.")
                if lesson_id not in [l["id"] for l in content.MODULE["lessons"]]:
                    raise ApiError(404, "Lesson not found.")
                value = clean_text(body.get("value"), 8000, "Content")
                if not value:
                    raise ApiError(400, "Content cannot be empty.")
                conn.execute(
                    "INSERT INTO content_overrides (key, value, updated_at) VALUES (?,?,?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    (f"lesson:{lesson_id}:{field}", value, iso()),
                )
                conn.commit()
                return self.send_json({"ok": True, "module": get_module_content(conn)})

            raise ApiError(404, "Admin route not found.")

        raise ApiError(404, "Not found.")

    def validate_question(self, body, conn):
        component = body.get("component")
        kind = body.get("kind")
        if component not in content.COMPONENT_BY_ID:
            raise ApiError(400, "Choose a valid component.")
        if kind not in ("diagnostic", "quiz", "scenario"):
            raise ApiError(400, "Choose a valid assessment type.")
        topic = clean_text(body.get("topic", "General"), 80, "Topic") or "General"
        prompt = clean_text(body.get("prompt"), 1000, "Question")
        if len(prompt) < 10:
            raise ApiError(400, "The question is too short.")
        options = body.get("options")
        if not isinstance(options, list) or not (2 <= len(options) <= 6):
            raise ApiError(400, "Provide between 2 and 6 options.")
        opts = []
        for o in options:
            val = clean_text(o, 300, "Option")
            if not val:
                raise ApiError(400, "Options cannot be empty.")
            opts.append(val)
        try:
            correct = int(body.get("correct"))
        except (TypeError, ValueError):
            raise ApiError(400, "Choose the correct option.")
        if correct < 0 or correct >= len(opts):
            raise ApiError(400, "Correct option is out of range.")
        explanation = clean_text(body.get("explanation", ""), 1000, "Explanation")
        if len(explanation) < 10:
            raise ApiError(400, "Add a short explanation for the answer.")
        return {"component": component, "kind": kind, "topic": topic, "prompt": prompt,
                "options": opts, "correct": correct, "explanation": explanation,
                "active": 1 if body.get("active", True) else 0}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed_reset():
    if DB_PATH.exists():
        backup = DB_PATH.with_suffix(".db.bak")
        shutil.copy2(DB_PATH, backup)
        DB_PATH.unlink()
        print(f"Existing database backed up to {backup}")


def main():
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Port must be a number.")
            return
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"\n  BizReady is running at http://localhost:{port}\n")
    print("  Demo learner : aina@demo.bizready.app / Demo1234!")
    print("  Admin        : admin@bizready.app / Admin1234!")
    print("  AI coach     : " + ("live API configured" if ai_status()["configured"] else "DEMO MODE (no API key configured)") + "\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
