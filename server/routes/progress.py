"""Progress dashboard and the personal action plan."""

import re

from ..clock import iso
from ..errors import ApiError, clean_text
from ..scoring import build_progress


def _plan(conn, user_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM plan_items WHERE user_id = ? ORDER BY done, id", (user_id,)
    ).fetchall()]


def handle(h, conn, method, path, user):
    if path == "/api/me" and method == "GET":
        h.send_json({"user": {"id": user["id"], "name": user["name"], "email": user["email"],
                              "role": user["role"], "created_at": user["created_at"]},
                     "progress": build_progress(conn, user)})
        return True

    if path == "/api/progress" and method == "GET":
        h.send_json(build_progress(conn, user))
        return True

    if path == "/api/plan" and method == "POST":
        body = h.read_json()
        title = clean_text(body.get("title"), 200, "Title")
        if len(title) < 4:
            raise ApiError(400, "Please give the action a clear title.", "invalid_input")
        detail = clean_text(body.get("detail", ""), 1000, "Detail")
        due = clean_text(body.get("due", ""), 20, "Due date")
        if due and not re.match(r"^\d{4}-\d{2}-\d{2}$", due):
            raise ApiError(400, "Due date must be YYYY-MM-DD.", "invalid_input")
        conn.execute(
            "INSERT INTO plan_items (user_id, title, detail, due, done, created_at) VALUES (?,?,?,?,0,?)",
            (user["id"], title, detail, due, iso()),
        )
        conn.commit()
        h.send_json({"ok": True, "plan": _plan(conn, user["id"])}, 201)
        return True

    match = re.fullmatch(r"/api/plan/(\d+)", path)
    if match:
        item_id = int(match.group(1))
        row = conn.execute("SELECT * FROM plan_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
        if not row:
            raise ApiError(404, "Action not found.", "not_found")
        if method == "PATCH":
            body = h.read_json()
            done = 1 if body.get("done") else 0
            detail = clean_text(body.get("detail", row["detail"]), 1000, "Detail")
            conn.execute(
                "UPDATE plan_items SET done = ?, detail = ?, completed_at = ? WHERE id = ?",
                (done, detail, iso() if done else None, item_id),
            )
            conn.commit()
            h.send_json({"ok": True, "plan": _plan(conn, user["id"])})
            return True
        if method == "DELETE":
            conn.execute("DELETE FROM plan_items WHERE id = ?", (item_id,))
            conn.commit()
            h.send_json({"ok": True})
            return True

    return False
