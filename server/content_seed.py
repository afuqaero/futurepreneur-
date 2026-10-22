"""Seed modules from content/seed/*.json.

The JSON files are the authoring source for new modules; once seeded, the
database is the source of truth and admins edit there.
"""

import json

from . import config
from .clock import iso


def seed_json_modules(conn):
    seed_dir = config.ROOT / "content" / "seed"
    if not seed_dir.exists():
        return 0
    added = 0
    now = iso()
    for path in sorted(seed_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        module_id = data.get("id")
        if not module_id:
            continue
        if conn.execute("SELECT 1 FROM modules WHERE id = ?", (module_id,)).fetchone():
            continue
        position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM modules").fetchone()[0]
        conn.execute(
            "INSERT INTO modules (id, component, title, tagline, level, hours, outcome, intro_json,"
            " practical_json, status, position, version, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)",
            (module_id, data["component"], data["title"], data.get("tagline", ""),
             data.get("level", "Foundation"), data.get("hours", ""), data.get("outcome", ""),
             json.dumps(data.get("intro", []), ensure_ascii=False),
             json.dumps(data.get("practical", {}), ensure_ascii=False),
             "published", position, now),
        )
        for index, lesson in enumerate(data.get("lessons", []), 1):
            body = {
                key: value for key, value in lesson.items()
                if key not in ("id", "title", "minutes", "summary")
            }
            conn.execute(
                "INSERT INTO lessons (id, module_id, position, title, minutes, summary, body_json, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (lesson["id"], module_id, index, lesson["title"], lesson.get("minutes", 10),
                 lesson.get("summary", ""), json.dumps(body, ensure_ascii=False), now),
            )
        for index, template in enumerate(data.get("templates", []), 1):
            conn.execute(
                "INSERT INTO templates (id, module_id, slug, title, description, format, filename, body, position, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"tpl-{module_id}-{template['slug']}", module_id, template["slug"],
                 template["title"], template.get("description", ""), template.get("format", "Markdown"),
                 template["filename"], template.get("body", ""), index, now),
            )
        pos = conn.execute("SELECT COALESCE(MAX(position), 0) FROM questions").fetchone()[0]
        for question in data.get("questions", []):
            pos += 1
            conn.execute(
                "INSERT INTO questions (id, component, module_id, kind, topic, prompt, options, correct,"
                " explanation, active, position) VALUES (?,?,?,?,?,?,?,?,?,1,?)",
                (question["id"], data["component"], module_id, question["kind"], question["topic"],
                 question["prompt"], json.dumps(question["options"]), question["correct"],
                 question["explanation"], pos),
            )
        added += 1
    conn.commit()
    return added
