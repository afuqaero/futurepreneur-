"""Learning module reads and lesson completion."""

import content
from ..clock import iso
from ..content_service import get_module_content
from ..errors import ApiError
from ..scoring import module_state


def handle(h, conn, method, path, user):
    if path == "/api/module/strategy" and method == "GET":
        module = get_module_content(conn)
        rows = conn.execute("SELECT lesson_id FROM lesson_progress WHERE user_id = ?", (user["id"],)).fetchall()
        h.send_json({
            "module": module,
            "lessons_done": [r["lesson_id"] for r in rows],
            "state": module_state(conn, user["id"]),
        })
        return True

    if path.startswith("/api/module/strategy/lesson/") and path.endswith("/complete") and method == "POST":
        lesson_id = path[len("/api/module/strategy/lesson/"):-len("/complete")].strip("/")
        if lesson_id not in [l["id"] for l in content.MODULE["lessons"]]:
            raise ApiError(404, "Lesson not found.", "not_found")
        conn.execute(
            "INSERT OR REPLACE INTO lesson_progress (user_id, lesson_id, completed_at) VALUES (?,?,?)",
            (user["id"], lesson_id, iso()),
        )
        conn.commit()
        h.send_json({"ok": True, "state": module_state(conn, user["id"])})
        return True

    return False
