"""Admin area: learner overview, rubric review, question bank, standards, content."""

import json
import re
import secrets

import content
from ..clock import iso
from ..content_service import get_module_content
from ..errors import ApiError, clean_text
from ..models import settings_public
from ..scoring import build_progress


def _require_admin(user):
    if user["role"] != "admin":
        raise ApiError(403, "Administrator access required.", "forbidden")


def handle(h, conn, method, path, user):
    if not path.startswith("/api/admin/"):
        return False
    _require_admin(user)

    if path == "/api/admin/overview" and method == "GET":
        learners = conn.execute(
            "SELECT u.id, u.name, u.email, u.role, u.created_at, p.business_name, p.sector FROM users u"
            " LEFT JOIN profiles p ON p.user_id = u.id WHERE u.role = 'learner' ORDER BY u.id"
        ).fetchall()
        out = []
        for learner in learners:
            prog = build_progress(conn, learner)
            out.append({
                "id": learner["id"], "name": learner["name"], "email": learner["email"],
                "business_name": learner["business_name"], "sector": learner["sector"],
                "overall_percent": prog["overall_percent"], "mastery": prog["mastery"]["level"],
                "module_passed": prog["module"]["passed"],
                "diagnostic": prog["diagnostic"]["overall"] if prog["diagnostic"] else None,
                "practical_status": (prog["module"]["practical"] or {}).get("status"),
                "created_at": learner["created_at"],
            })
        stats = {
            "learners": len(out),
            "profiles": conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0],
            "diagnostics": conn.execute("SELECT COUNT(*) FROM diagnostic_results").fetchone()[0],
            "passed": len([o for o in out if o["module_passed"]]),
            "pending_reviews": conn.execute("SELECT COUNT(*) FROM practical_submissions WHERE status = 'pending'").fetchone()[0],
        }
        h.send_json({"learners": out, "stats": stats})
        return True

    if path == "/api/admin/submissions" and method == "GET":
        rows = conn.execute(
            "SELECT ps.*, u.name AS learner_name, u.email FROM practical_submissions ps"
            " JOIN users u ON u.id = ps.user_id ORDER BY ps.status = 'reviewed', ps.id DESC"
        ).fetchall()
        submissions = [{
            "id": r["id"], "learner": r["learner_name"], "email": r["email"],
            "responses": json.loads(r["responses"]),
            "status": r["status"], "rubric": json.loads(r["rubric"]) if r["rubric"] else None,
            "average": r["average"], "passed": bool(r["passed"]),
            "reviewer_note": r["reviewer_note"], "created_at": r["created_at"],
            "reviewed_at": r["reviewed_at"],
        } for r in rows]
        h.send_json({"criteria": content.MODULE["practical"]["criteria"],
                     "prompts": content.MODULE["practical"]["prompts"],
                     "submissions": submissions,
                     "standards": settings_public(conn)})
        return True

    match = re.fullmatch(r"/api/admin/submissions/(\d+)/review", path)
    if match and method == "POST":
        sub_id = int(match.group(1))
        row = conn.execute("SELECT * FROM practical_submissions WHERE id = ?", (sub_id,)).fetchone()
        if not row:
            raise ApiError(404, "Submission not found.", "not_found")
        body = h.read_json()
        scores = body.get("scores")
        if not isinstance(scores, dict):
            raise ApiError(400, "Scores must be an object.", "invalid_input")
        s = settings_public(conn)
        rubric = {}
        for crit in content.MODULE["practical"]["criteria"]:
            try:
                val = int(scores.get(crit["id"]))
            except (TypeError, ValueError):
                raise ApiError(400, "Every criterion needs a score from 0 to 4.", "invalid_input")
            if val < 0 or val > 4:
                raise ApiError(400, "Every criterion needs a score from 0 to 4.", "invalid_input")
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
        h.send_json({"ok": True, "average": avg, "passed": passed, "standard": s["rubric_min"]})
        return True

    if path == "/api/admin/questions" and method == "GET":
        rows = conn.execute("SELECT * FROM questions ORDER BY kind, position, id").fetchall()
        h.send_json({"questions": [{
            "id": r["id"], "component": r["component"], "kind": r["kind"], "topic": r["topic"],
            "prompt": r["prompt"], "options": json.loads(r["options"]), "correct": r["correct"],
            "explanation": r["explanation"], "active": bool(r["active"]), "position": r["position"],
        } for r in rows], "components": content.COMPONENTS})
        return True

    if path == "/api/admin/questions" and method == "POST":
        body = h.read_json()
        item = validate_question(body)
        position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM questions").fetchone()[0]
        qid = "q-" + secrets.token_hex(5)
        conn.execute(
            "INSERT INTO questions (id, component, kind, topic, prompt, options, correct, explanation, active, position)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (qid, item["component"], item["kind"], item["topic"], item["prompt"],
             json.dumps(item["options"]), item["correct"], item["explanation"], item["active"], position),
        )
        conn.commit()
        h.send_json({"ok": True, "id": qid}, 201)
        return True

    qmatch = re.fullmatch(r"/api/admin/questions/([\w-]+)", path)
    if qmatch:
        qid = qmatch.group(1)
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
        if not row:
            raise ApiError(404, "Question not found.", "not_found")
        if method == "PUT":
            body = h.read_json()
            item = validate_question(body)
            conn.execute(
                "UPDATE questions SET component=?, kind=?, topic=?, prompt=?, options=?, correct=?,"
                " explanation=?, active=? WHERE id=?",
                (item["component"], item["kind"], item["topic"], item["prompt"], json.dumps(item["options"]),
                 item["correct"], item["explanation"], item["active"], qid),
            )
            conn.commit()
            h.send_json({"ok": True})
            return True
        if method == "DELETE":
            conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
            conn.commit()
            h.send_json({"ok": True})
            return True

    if path == "/api/admin/settings" and method == "PUT":
        body = h.read_json()
        values = {}
        for key, low, high in (("quiz_pass", 0, 100), ("scenario_pass", 0, 100),
                               ("rubric_min", 0, 4), ("rubric_floor", 0, 4)):
            try:
                val = float(body.get(key))
            except (TypeError, ValueError):
                raise ApiError(400, "Passing standards must be numbers.", "invalid_input")
            if val < low or val > high:
                raise ApiError(400, f"{key} must be between {low} and {high}.", "invalid_input")
            # Percentages and the rubric floor are whole numbers; the rubric
            # minimum keeps one decimal so 3.25 remains expressible.
            if key in ("quiz_pass", "scenario_pass", "rubric_floor"):
                values[key] = str(int(round(val)))
            else:
                values[key] = f"{val:.2f}".rstrip("0").rstrip(".") or "0"
        for key, val in values.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, val))
        conn.commit()
        h.send_json({"ok": True, "settings": settings_public(conn)})
        return True

    if path == "/api/admin/content" and method == "GET":
        module = get_module_content(conn)
        overrides = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM content_overrides").fetchall()}
        h.send_json({"module": module, "overrides": overrides})
        return True

    if path == "/api/admin/content" and method == "PUT":
        body = h.read_json()
        lesson_id = body.get("lesson_id")
        field = body.get("field")
        if field not in ("title", "summary", "explanation"):
            raise ApiError(400, "Editable fields are title, summary and explanation.", "invalid_input")
        if lesson_id not in [l["id"] for l in content.MODULE["lessons"]]:
            raise ApiError(404, "Lesson not found.", "not_found")
        value = clean_text(body.get("value"), 8000, "Content")
        if not value:
            raise ApiError(400, "Content cannot be empty.", "invalid_input")
        conn.execute(
            "INSERT INTO content_overrides (key, value, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (f"lesson:{lesson_id}:{field}", value, iso()),
        )
        conn.commit()
        h.send_json({"ok": True, "module": get_module_content(conn)})
        return True

    raise ApiError(404, "Admin route not found.", "not_found")


def validate_question(body):
    component = body.get("component")
    kind = body.get("kind")
    if component not in content.COMPONENT_BY_ID:
        raise ApiError(400, "Choose a valid component.", "invalid_input")
    if kind not in ("diagnostic", "quiz", "scenario"):
        raise ApiError(400, "Choose a valid assessment type.", "invalid_input")
    topic = clean_text(body.get("topic", "General"), 80, "Topic") or "General"
    prompt = clean_text(body.get("prompt"), 1000, "Question")
    if len(prompt) < 10:
        raise ApiError(400, "The question is too short.", "invalid_input")
    options = body.get("options")
    if not isinstance(options, list) or not (2 <= len(options) <= 6):
        raise ApiError(400, "Provide between 2 and 6 options.", "invalid_input")
    opts = []
    for option in options:
        val = clean_text(option, 300, "Option")
        if not val:
            raise ApiError(400, "Options cannot be empty.", "invalid_input")
        opts.append(val)
    try:
        correct = int(body.get("correct"))
    except (TypeError, ValueError):
        raise ApiError(400, "Choose the correct option.", "invalid_input")
    if correct < 0 or correct >= len(opts):
        raise ApiError(400, "Correct option is out of range.", "invalid_input")
    explanation = clean_text(body.get("explanation", ""), 1000, "Explanation")
    if len(explanation) < 10:
        raise ApiError(400, "Add a short explanation for the answer.", "invalid_input")
    return {"component": component, "kind": kind, "topic": topic, "prompt": prompt,
            "options": opts, "correct": correct, "explanation": explanation,
            "active": 1 if body.get("active", True) else 0}
