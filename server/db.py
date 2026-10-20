"""Database access, migrations, backups and seed data."""

import json
import os
import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import content
from . import config
from .clock import iso, utcnow
from .security import hash_password


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def get_db():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def apply_migrations(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    for path in sorted(config.MIGRATIONS_DIR.glob("*.sql")):
        version = path.name
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?,?)",
            (version, iso()),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------


def backup_database(keep=5):
    if not config.DB_PATH.exists() or config.DB_PATH.stat().st_size == 0:
        return None
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%d-%H%M%S-%f")
    dest = config.BACKUP_DIR / f"bizready-{stamp}.db"
    shutil.copy2(config.DB_PATH, dest)
    backups = sorted(config.BACKUP_DIR.glob("bizready-*.db"))
    for old in backups[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def reset_database():
    backup_database()
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(config.DB_PATH) + suffix)
        if path.exists():
            path.unlink()
    return True


# ---------------------------------------------------------------------------
# Seed content
# ---------------------------------------------------------------------------


def seed_questions(conn):
    if conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]:
        return
    rows = []
    pos = 0
    for item in content.DIAGNOSTIC_QUESTIONS + content.QUIZ_QUESTIONS + content.SCENARIO_QUESTIONS:
        pos += 1
        module_id = "strategy" if item["kind"] in ("quiz", "scenario") else None
        rows.append(
            (
                item["id"], item["component"], module_id, item["kind"], item["topic"], item["prompt"],
                json.dumps(item["options"]), item["correct"], item["explanation"], 1, pos,
            )
        )
    conn.executemany(
        "INSERT INTO questions (id, component, module_id, kind, topic, prompt, options, correct,"
        " explanation, active, position) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def seed_demo(conn):
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    now = utcnow()
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
        ("Platform Admin", "admin@bizready.app", hash_password("Admin1234!"), "admin", iso(now)),
    )
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


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def seed_content(conn):
    """Copy the prototype's Python content into the database once."""
    if conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]:
        return
    module = content.MODULE
    now = iso()
    conn.execute(
        "INSERT INTO modules (id, component, title, tagline, level, hours, outcome, intro_json,"
        " practical_json, status, position, version, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?, 'published', 1, 1, ?)",
        (
            module["id"], module["component"], module["title"], module["tagline"], module["level"],
            module["hours"], module["outcome"], json.dumps(module["intro"], ensure_ascii=False),
            json.dumps(module["practical"], ensure_ascii=False), now,
        ),
    )
    for position, lesson in enumerate(module["lessons"], 1):
        body = {
            key: value for key, value in lesson.items()
            if key not in ("id", "number", "title", "minutes", "summary")
        }
        conn.execute(
            "INSERT INTO lessons (id, module_id, position, title, minutes, summary, body_json, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (lesson["id"], module["id"], position, lesson["title"], lesson["minutes"],
             lesson["summary"], json.dumps(body, ensure_ascii=False), now),
        )
    for position, template in enumerate(module["templates"], 1):
        conn.execute(
            "INSERT INTO templates (id, module_id, slug, title, description, format, filename, body, position, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"tpl-{module['id']}-{template['slug']}", module["id"], template["slug"], template["title"],
             template["description"], template["format"], template["filename"],
             content.TEMPLATE_FILES.get(template["slug"], ""), position, now),
        )
    conn.commit()


def init_db(seed=True):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if os.environ.get("BIZREADY_SKIP_BACKUP") != "1":
        backup_database()
    conn = get_db()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        apply_migrations(conn)
        for key, value in config.DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (key, value))
        if seed:
            seed_questions(conn)
            seed_demo(conn)
            seed_content(conn)
        conn.commit()
    finally:
        conn.close()
