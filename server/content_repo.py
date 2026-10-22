"""Database-backed content: modules, lessons, templates, revisions, audit."""

import json
import re
import secrets

import content
from .clock import iso

DEFAULT_MODULE_ID = "strategy"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class ContentError(Exception):
    def __init__(self, message, code="invalid_content"):
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# Component availability
# ---------------------------------------------------------------------------


def components_public(conn):
    published = {
        row["component"]: row["id"]
        for row in conn.execute("SELECT component, id FROM modules WHERE status = 'published'")
    }
    out = []
    for comp in content.COMPONENTS:
        item = dict(comp)
        item["available"] = comp["id"] in published
        item["module_id"] = published.get(comp["id"])
        out.append(item)
    return out


def component_has_published(conn, component):
    return bool(
        conn.execute(
            "SELECT 1 FROM modules WHERE component = ? AND status = 'published' LIMIT 1", (component,)
        ).fetchone()
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _module_row(row):
    intro = json.loads(row["intro_json"] or "[]")
    practical = json.loads(row["practical_json"] or "{}")
    return {
        "id": row["id"],
        "component": row["component"],
        "title": row["title"],
        "tagline": row["tagline"],
        "level": row["level"],
        "hours": row["hours"],
        "outcome": row["outcome"],
        "intro": intro,
        "practical": practical,
        "status": row["status"],
        "position": row["position"],
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def _lesson_dict(row):
    body = json.loads(row["body_json"] or "{}")
    return {
        "id": row["id"],
        "number": row["position"],
        "title": row["title"],
        "minutes": row["minutes"],
        "summary": row["summary"],
        **body,
    }


def list_modules(conn, published_only=False):
    sql = "SELECT * FROM modules"
    args = ()
    if published_only:
        sql += " WHERE status = 'published'"
    sql += " ORDER BY position, title"
    return [_module_row(row) for row in conn.execute(sql, args)]


def get_module(conn, module_id=DEFAULT_MODULE_ID, published_only=False):
    row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
    if not row:
        return None
    if published_only and row["status"] != "published":
        return None
    module = _module_row(row)
    module["lessons"] = [
        _lesson_dict(r)
        for r in conn.execute(
            "SELECT * FROM lessons WHERE module_id = ? ORDER BY position, id", (module_id,)
        )
    ]
    module["templates"] = [
        {
            "slug": r["slug"],
            "title": r["title"],
            "description": r["description"],
            "format": r["format"],
            "filename": r["filename"],
        }
        for r in conn.execute(
            "SELECT * FROM templates WHERE module_id = ? ORDER BY position, title", (module_id,)
        )
    ]
    module["question_counts"] = question_counts(conn, module_id)
    return module


def question_counts(conn, module_id):
    rows = conn.execute(
        "SELECT kind, COUNT(*) AS n FROM questions WHERE module_id = ? AND active = 1 GROUP BY kind",
        (module_id,),
    ).fetchall()
    return {r["kind"]: r["n"] for r in rows}


def module_summaries(conn):
    out = []
    for module in list_modules(conn):
        counts = question_counts(conn, module["id"])
        out.append({
            "id": module["id"], "component": module["component"], "title": module["title"],
            "status": module["status"], "lessons": len(
                conn.execute("SELECT 1 FROM lessons WHERE module_id = ?", (module["id"],)).fetchall()
            ),
            "quiz": counts.get("quiz", 0), "scenario": counts.get("scenario", 0),
            "templates": conn.execute(
                "SELECT COUNT(*) FROM templates WHERE module_id = ?", (module["id"],)
            ).fetchone()[0],
            "updated_at": module["updated_at"],
        })
    return out


def get_lesson(conn, lesson_id):
    row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    return _lesson_dict(row) if row else None


def get_template(conn, slug):
    row = conn.execute("SELECT * FROM templates WHERE slug = ?", (slug,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"], "module_id": row["module_id"], "slug": row["slug"],
        "title": row["title"], "description": row["description"], "format": row["format"],
        "filename": row["filename"], "body": row["body"],
    }


def list_templates(conn, module_id):
    return conn.execute(
        "SELECT * FROM templates WHERE module_id = ? ORDER BY position, title", (module_id,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Revisions and audit
# ---------------------------------------------------------------------------


def save_revision(conn, entity, entity_id, action, snapshot, editor_id=None):
    conn.execute(
        "INSERT INTO content_revisions (entity, entity_id, action, snapshot_json, editor_id, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (entity, entity_id, action, json.dumps(snapshot, ensure_ascii=False), editor_id, iso()),
    )


def list_revisions(conn, entity=None, entity_id=None, limit=20):
    sql = "SELECT cr.*, u.name AS editor_name FROM content_revisions cr LEFT JOIN users u ON u.id = cr.editor_id"
    where, args = [], []
    if entity:
        where.append("cr.entity = ?")
        args.append(entity)
    if entity_id:
        where.append("cr.entity_id = ?")
        args.append(entity_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY cr.id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 100)))
    return [
        {
            "id": r["id"], "entity": r["entity"], "entity_id": r["entity_id"],
            "action": r["action"], "editor": r["editor_name"], "created_at": r["created_at"],
            "snapshot": json.loads(r["snapshot_json"]),
        }
        for r in conn.execute(sql, args)
    ]


def audit(conn, actor_id, action, entity, entity_id=None, detail=None):
    conn.execute(
        "INSERT INTO audit_log (actor_id, action, entity, entity_id, detail_json, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (actor_id, action, entity, entity_id, json.dumps(detail or {}, ensure_ascii=False), iso()),
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def create_module(conn, module_id, component, title, editor_id=None):
    if not SLUG_RE.match(module_id or ""):
        raise ContentError("Module id must be lowercase letters, numbers and dashes.")
    if component not in content.COMPONENT_BY_ID:
        raise ContentError("Choose a valid component.")
    if conn.execute("SELECT 1 FROM modules WHERE id = ?", (module_id,)).fetchone():
        raise ContentError("A module with that id already exists.", "conflict")
    if conn.execute("SELECT 1 FROM modules WHERE component = ?", (component,)).fetchone():
        raise ContentError("That component already has a module. Edit it instead.", "conflict")
    position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM modules").fetchone()[0]
    conn.execute(
        "INSERT INTO modules (id, component, title, tagline, level, hours, outcome, intro_json,"
        " practical_json, status, position, version, updated_at)"
        " VALUES (?,?,?,?,'Foundation','','','[]','{}','draft',?,1,?)",
        (module_id, component, title, "", position, iso()),
    )
    module = get_module(conn, module_id)
    save_revision(conn, "module", module_id, "create", module, editor_id)
    return module


def update_module(conn, module_id, fields, editor_id=None):
    row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
    if not row:
        raise ContentError("Module not found.", "not_found")
    allowed = ("title", "tagline", "level", "hours", "outcome")
    values = {k: fields[k] for k in allowed if k in fields}
    if "intro" in fields:
        values["intro_json"] = json.dumps(fields["intro"], ensure_ascii=False)
    if "practical" in fields:
        values["practical_json"] = json.dumps(fields["practical"], ensure_ascii=False)
    if not values:
        return get_module(conn, module_id)
    sets = ", ".join(f"{k} = ?" for k in values)
    conn.execute(
        f"UPDATE modules SET {sets}, version = version + 1, updated_at = ? WHERE id = ?",
        (*values.values(), iso(), module_id),
    )
    module = get_module(conn, module_id)
    save_revision(conn, "module", module_id, "update", module, editor_id)
    return module


def set_module_status(conn, module_id, status, editor_id=None):
    if status not in ("draft", "published"):
        raise ContentError("Status must be draft or published.")
    row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
    if not row:
        raise ContentError("Module not found.", "not_found")
    if status == "published":
        problems = publish_problems(conn, module_id)
        if problems:
            raise ContentError("Cannot publish: " + " ".join(problems), "not_ready")
    conn.execute(
        "UPDATE modules SET status = ?, version = version + 1, updated_at = ? WHERE id = ?",
        (status, iso(), module_id),
    )
    module = get_module(conn, module_id)
    save_revision(conn, "module", module_id, status, module, editor_id)
    audit(conn, editor_id, "module." + status, "module", module_id, {"title": module["title"]})
    return module


def publish_problems(conn, module_id):
    module = get_module(conn, module_id)
    problems = []
    if not module["lessons"]:
        problems.append("Add at least one lesson.")
    counts = module["question_counts"]
    if counts.get("quiz", 0) < 5:
        problems.append("Add at least 5 quiz questions.")
    if counts.get("scenario", 0) < 3:
        problems.append("Add at least 3 scenario questions.")
    practical = module["practical"] or {}
    if len(practical.get("criteria") or []) < 2:
        problems.append("Add the practical criteria.")
    if len(practical.get("prompts") or []) < 1:
        problems.append("Add at least one practical prompt.")
    return problems


def add_lesson(conn, module_id, editor_id=None):
    if not conn.execute("SELECT 1 FROM modules WHERE id = ?", (module_id,)).fetchone():
        raise ContentError("Module not found.", "not_found")
    position = conn.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM lessons WHERE module_id = ?", (module_id,)
    ).fetchone()[0]
    lesson_id = "l" + secrets.token_hex(4)
    conn.execute(
        "INSERT INTO lessons (id, module_id, position, title, minutes, summary, body_json, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (lesson_id, module_id, position, "New lesson", 10, "", "{}", iso()),
    )
    lesson = get_lesson(conn, lesson_id)
    save_revision(conn, "lesson", lesson_id, "create", lesson, editor_id)
    return lesson


def update_lesson(conn, lesson_id, data, editor_id=None):
    row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not row:
        raise ContentError("Lesson not found.", "not_found")
    body = json.loads(row["body_json"] or "{}")
    body.update(data.get("body") or {})
    conn.execute(
        "UPDATE lessons SET title = ?, minutes = ?, summary = ?, body_json = ?, updated_at = ? WHERE id = ?",
        (data["title"], data["minutes"], data["summary"], json.dumps(body, ensure_ascii=False), iso(), lesson_id),
    )
    lesson = get_lesson(conn, lesson_id)
    save_revision(conn, "lesson", lesson_id, "update", lesson, editor_id)
    return lesson


def delete_lesson(conn, lesson_id, editor_id=None):
    row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not row:
        raise ContentError("Lesson not found.", "not_found")
    module_id = row["module_id"]
    if conn.execute("SELECT COUNT(*) FROM lessons WHERE module_id = ?", (module_id,)).fetchone()[0] <= 1:
        raise ContentError("A module needs at least one lesson.")
    snapshot = get_lesson(conn, lesson_id)
    conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    save_revision(conn, "lesson", lesson_id, "delete", snapshot, editor_id)
    return True


def upsert_template(conn, module_id, data, editor_id=None):
    slug = data.get("slug") or ("tpl-" + secrets.token_hex(4))
    if not SLUG_RE.match(slug):
        raise ContentError("Template slug must be lowercase letters, numbers and dashes.")
    existing = conn.execute("SELECT * FROM templates WHERE slug = ?", (slug,)).fetchone()
    if existing and existing["module_id"] != module_id:
        raise ContentError("That template slug is already used by another module.", "conflict")
    if existing:
        conn.execute(
            "UPDATE templates SET title=?, description=?, format=?, filename=?, body=?, updated_at=?"
            " WHERE slug=?",
            (data["title"], data.get("description", ""), data.get("format", "Markdown"),
             data["filename"], data.get("body", ""), iso(), slug),
        )
        action = "update"
    else:
        position = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM templates WHERE module_id = ?", (module_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO templates (id, module_id, slug, title, description, format, filename, body, position, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"tpl-{secrets.token_hex(6)}", module_id, slug, data["title"], data.get("description", ""),
             data.get("format", "Markdown"), data["filename"], data.get("body", ""), position, iso()),
        )
        action = "create"
    snapshot = get_template(conn, slug)
    save_revision(conn, "template", slug, action, snapshot, editor_id)
    return snapshot


def delete_template(conn, slug, editor_id=None):
    row = conn.execute("SELECT * FROM templates WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise ContentError("Template not found.", "not_found")
    snapshot = get_template(conn, slug)
    conn.execute("DELETE FROM templates WHERE slug = ?", (slug,))
    save_revision(conn, "template", slug, "delete", snapshot, editor_id)
    return True
