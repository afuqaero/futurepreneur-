"""Learning module reads and lesson completion (DB-backed modules)."""

import re

from .. import content_repo, template_files
from ..clock import iso
from ..content_service import get_module_content
from ..errors import ApiError
from ..scoring import module_state


def handle(h, conn, method, path, user):
    match = re.fullmatch(r"/api/module/([\w-]+)", path)
    if match and method == "GET":
        module = get_module_content(conn, match.group(1), published_only=True)
        if not module:
            raise ApiError(404, "Module not available.", "not_found")
        module = template_files.decorate(module)
        rows = conn.execute("SELECT lesson_id FROM lesson_progress WHERE user_id = ?", (user["id"],)).fetchall()
        h.send_json({
            "module": module,
            "lessons_done": [r["lesson_id"] for r in rows],
            "state": module_state(conn, user["id"], module["id"]),
        })
        return True

    match = re.fullmatch(r"/api/module/([\w-]+)/lesson/([\w-]+)/complete", path)
    if match and method == "POST":
        module = content_repo.get_module(conn, match.group(1), published_only=True)
        if not module:
            raise ApiError(404, "Module not available.", "not_found")
        lesson_id = match.group(2)
        if lesson_id not in [lesson["id"] for lesson in module["lessons"]]:
            raise ApiError(404, "Lesson not found.", "not_found")
        conn.execute(
            "INSERT OR REPLACE INTO lesson_progress (user_id, lesson_id, completed_at) VALUES (?,?,?)",
            (user["id"], lesson_id, iso()),
        )
        conn.commit()
        h.send_json({"ok": True, "state": module_state(conn, user["id"], module["id"])})
        return True

    return False
