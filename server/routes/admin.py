"""Admin area: learner overview, rubric review, question bank, standards, content."""

import json
import re
import secrets

import content
from .. import content_repo
from ..clock import iso
from ..errors import ApiError, clean_text
from ..models import settings_public
from ..scoring import build_progress


def _repo(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except content_repo.ContentError as exc:
        status = 404 if exc.code == "not_found" else 409 if exc.code == "conflict" else 400
        raise ApiError(status, exc.message, exc.code)


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
                "module_passed": prog["module"]["passed"] if prog["module"] else False,
                "modules_passed": prog["modules_passed"], "modules_total": prog["modules_total"],
                "diagnostic": prog["diagnostic"]["overall"] if prog["diagnostic"] else None,
                "practical_status": (prog["module"]["practical"] or {}).get("status") if prog["module"] else None,
                "created_at": learner["created_at"],
            })
        stats = {
            "learners": len(out),
            "profiles": conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0],
            "diagnostics": conn.execute("SELECT COUNT(*) FROM diagnostic_results").fetchone()[0],
            "passed": len([o for o in out if o["modules_passed"] > 0]),
            "pending_reviews": conn.execute("SELECT COUNT(*) FROM practical_submissions WHERE status = 'pending'").fetchone()[0],
        }
        h.send_json({"learners": out, "stats": stats})
        return True

    if path == "/api/admin/submissions" and method == "GET":
        rows = conn.execute(
            "SELECT ps.*, u.name AS learner_name, u.email, m.title AS module_title, m.practical_json"
            " FROM practical_submissions ps"
            " JOIN users u ON u.id = ps.user_id"
            " LEFT JOIN modules m ON m.id = ps.module_id"
            " ORDER BY ps.status = 'reviewed', ps.id DESC"
        ).fetchall()
        submissions = []
        for r in rows:
            practical = json.loads(r["practical_json"] or "{}")
            submissions.append({
                "id": r["id"], "learner": r["learner_name"], "email": r["email"],
                "module_id": r["module_id"], "module_title": r["module_title"] or "Unknown module",
                "responses": json.loads(r["responses"]),
                "status": r["status"], "rubric": json.loads(r["rubric"]) if r["rubric"] else None,
                "average": r["average"], "passed": bool(r["passed"]),
                "reviewer_note": r["reviewer_note"], "created_at": r["created_at"],
                "reviewed_at": r["reviewed_at"],
                "criteria": practical.get("criteria") or [],
                "prompts": practical.get("prompts") or [],
            })
        h.send_json({"submissions": submissions, "standards": settings_public(conn)})
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
        module = content_repo.get_module(conn, row["module_id"]) if row["module_id"] else None
        criteria = (module or {}).get("practical", {}).get("criteria") or content.MODULE["practical"]["criteria"]
        allowed = {c["id"] for c in criteria}
        if set(scores) - allowed:
            raise ApiError(400, "Scores contain a criterion that does not belong to this module.", "invalid_input")
        rubric = {}
        for crit in criteria:
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
        content_repo.audit(conn, user["id"], "practical.review", "practical", str(sub_id),
                           {"average": avg, "passed": passed, "module_id": row["module_id"]})
        conn.commit()
        h.send_json({"ok": True, "average": avg, "passed": passed, "standard": s["rubric_min"]})
        return True

    # -- content: modules ---------------------------------------------------
    if path == "/api/admin/modules" and method == "GET":
        h.send_json({
            "modules": content_repo.module_summaries(conn),
            "components": content_repo.components_public(conn),
        })
        return True

    if path == "/api/admin/modules" and method == "POST":
        body = h.read_json()
        module = _repo(
            content_repo.create_module, conn,
            clean_text(body.get("id", ""), 50, "Module id").lower(),
            body.get("component", ""),
            clean_text(body.get("title", ""), 120, "Title"),
            user["id"],
        )
        conn.commit()
        h.send_json({"ok": True, "module": module}, 201)
        return True

    match = re.fullmatch(r"/api/admin/modules/([\w-]+)/status", path)
    if match and method == "POST":
        body = h.read_json()
        module = _repo(content_repo.set_module_status, conn, match.group(1), body.get("status", ""), user["id"])
        conn.commit()
        h.send_json({"ok": True, "module": module})
        return True

    match = re.fullmatch(r"/api/admin/modules/([\w-]+)/lessons", path)
    if match and method == "POST":
        lesson = _repo(content_repo.add_lesson, conn, match.group(1), user["id"])
        conn.commit()
        h.send_json({"ok": True, "lesson": lesson}, 201)
        return True

    match = re.fullmatch(r"/api/admin/modules/([\w-]+)/templates", path)
    if match and method == "PUT":
        body = h.read_json()
        template = _repo(
            content_repo.upsert_template, conn, match.group(1),
            {
                "slug": clean_text(body.get("slug", ""), 50, "Slug").lower(),
                "title": clean_text(body.get("title", ""), 120, "Title"),
                "description": clean_text(body.get("description", ""), 400, "Description"),
                "format": clean_text(body.get("format", "Markdown"), 20, "Format"),
                "filename": clean_text(body.get("filename", ""), 120, "Filename"),
                "body": body.get("body", "") if isinstance(body.get("body", ""), str) else "",
            },
            user["id"],
        )
        conn.commit()
        h.send_json({"ok": True, "template": template})
        return True

    match = re.fullmatch(r"/api/admin/modules/([\w-]+)", path)
    if match:
        module_id = match.group(1)
        if method == "GET":
            module = content_repo.get_module(conn, module_id)
            if not module:
                raise ApiError(404, "Module not found.", "not_found")
            h.send_json({"module": module, "revisions": content_repo.list_revisions(conn, "module", module_id, 10)})
            return True
        if method == "PUT":
            fields = validate_module_fields(h.read_json())
            module = _repo(content_repo.update_module, conn, module_id, fields, user["id"])
            conn.commit()
            h.send_json({"ok": True, "module": module})
            return True

    match = re.fullmatch(r"/api/admin/lessons/([\w-]+)", path)
    if match:
        lesson_id = match.group(1)
        if method == "PUT":
            data = validate_lesson_payload(h.read_json())
            lesson = _repo(content_repo.update_lesson, conn, lesson_id, data, user["id"])
            conn.commit()
            h.send_json({"ok": True, "lesson": lesson})
            return True
        if method == "DELETE":
            _repo(content_repo.delete_lesson, conn, lesson_id, user["id"])
            conn.commit()
            h.send_json({"ok": True})
            return True

    match = re.fullmatch(r"/api/admin/templates/([\w-]+)", path)
    if match and method == "DELETE":
        _repo(content_repo.delete_template, conn, match.group(1), user["id"])
        conn.commit()
        h.send_json({"ok": True})
        return True

    if path == "/api/admin/revisions" and method == "GET":
        h.send_json({"revisions": content_repo.list_revisions(conn, limit=30)})
        return True

    match = re.fullmatch(r"/api/admin/revisions/([\w-]+)/([\w-]+)", path)
    if match and method == "GET":
        h.send_json({"revisions": content_repo.list_revisions(conn, match.group(1), match.group(2), 30)})
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
        module_id = conn.execute(
            "SELECT id FROM modules WHERE component = ? ORDER BY status = 'published' DESC, position LIMIT 1",
            (item["component"],),
        ).fetchone()
        module_id = module_id["id"] if module_id and item["kind"] in ("quiz", "scenario") else None
        conn.execute(
            "INSERT INTO questions (id, component, module_id, kind, topic, prompt, options, correct,"
            " explanation, active, position) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (qid, item["component"], module_id, item["kind"], item["topic"], item["prompt"],
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
            module_row = conn.execute(
                "SELECT id FROM modules WHERE component = ? ORDER BY status = 'published' DESC, position LIMIT 1",
                (item["component"],),
            ).fetchone()
            module_id = module_row["id"] if module_row and item["kind"] in ("quiz", "scenario") else None
            conn.execute(
                "UPDATE questions SET component=?, module_id=?, kind=?, topic=?, prompt=?, options=?, correct=?,"
                " explanation=?, active=? WHERE id=?",
                (item["component"], module_id, item["kind"], item["topic"], item["prompt"], json.dumps(item["options"]),
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
        content_repo.audit(conn, user["id"], "settings.update", "settings", None, values)
        conn.commit()
        h.send_json({"ok": True, "settings": settings_public(conn)})
        return True

    if path == "/api/admin/content" and method == "GET":
        modules = content_repo.module_summaries(conn)
        module = content_repo.get_module(conn, modules[0]["id"]) if modules else None
        h.send_json({
            "modules": modules,
            "module": module,
            "components": content_repo.components_public(conn),
        })
        return True

    if path == "/api/admin/content" and method == "PUT":
        body = h.read_json()
        lesson_id = body.get("lesson_id")
        field = body.get("field")
        if field not in ("title", "summary", "explanation"):
            raise ApiError(400, "Editable fields are title, summary and explanation.", "invalid_input")
        lesson = content_repo.get_lesson(conn, lesson_id)
        if not lesson:
            raise ApiError(404, "Lesson not found.", "not_found")
        value = clean_text(body.get("value"), 8000, "Content")
        if not value:
            raise ApiError(400, "Content cannot be empty.", "invalid_input")
        lesson_body = {
            key: lesson[key] for key in
            ("explanation", "example", "do", "dont", "why", "mistakes", "exercise")
            if key in lesson
        }
        if field == "explanation":
            lesson_body["explanation"] = [p.strip() for p in value.split("\n\n") if p.strip()]
        data = {
            "title": value if field == "title" else lesson["title"],
            "summary": value if field == "summary" else lesson["summary"],
            "minutes": lesson["minutes"],
            "body": lesson_body,
        }
        updated = _repo(content_repo.update_lesson, conn, lesson_id, data, user["id"])
        conn.commit()
        h.send_json({"ok": True, "lesson": updated})
        return True

    raise ApiError(404, "Admin route not found.", "not_found")


def validate_module_fields(body):
    out = {}
    for key, limit in (("title", 120), ("tagline", 300), ("level", 40), ("hours", 40), ("outcome", 400)):
        if key in body:
            val = clean_text(body[key], limit, key.title())
            if key == "title" and len(val) < 3:
                raise ApiError(400, "Module title is too short.", "invalid_input")
            out[key] = val
    if "intro" in body:
        intro = body["intro"]
        if not isinstance(intro, list):
            raise ApiError(400, "Intro must be a list of paragraphs.", "invalid_input")
        out["intro"] = [
            clean_text(item, 800, "Intro paragraph")
            for item in intro if isinstance(item, str) and item.strip()
        ][:20]
    if "practical" in body:
        practical = body["practical"]
        if not isinstance(practical, dict):
            raise ApiError(400, "Practical must be an object.", "invalid_input")
        criteria = []
        for item in practical.get("criteria") or []:
            if not isinstance(item, dict):
                raise ApiError(400, "Each criterion must be an object.", "invalid_input")
            cid = clean_text(item.get("id", ""), 40, "Criterion id").lower()
            if not re.match(r"^[a-z0-9_]{2,40}$", cid):
                raise ApiError(400, "Criterion ids use lowercase letters, numbers and underscores.", "invalid_input")
            criteria.append({
                "id": cid,
                "label": clean_text(item.get("label", ""), 120, "Criterion label"),
                "hint": clean_text(item.get("hint", ""), 300, "Criterion hint"),
            })
        criterion_ids = {c["id"] for c in criteria}
        prompts = []
        for item in practical.get("prompts") or []:
            if not isinstance(item, dict):
                raise ApiError(400, "Each prompt must be an object.", "invalid_input")
            pid = clean_text(item.get("id", ""), 20, "Prompt id").lower()
            if not re.match(r"^p[0-9]{1,3}$", pid):
                raise ApiError(400, "Prompt ids look like p1, p2, p3.", "invalid_input")
            criterion = item.get("criterion", "")
            if criterion not in criterion_ids:
                raise ApiError(400, "Each prompt must reference a criterion.", "invalid_input")
            prompts.append({
                "id": pid,
                "criterion": criterion,
                "label": clean_text(item.get("label", ""), 300, "Prompt label"),
                "placeholder": clean_text(item.get("placeholder", ""), 300, "Prompt placeholder"),
            })
        out["practical"] = {
            "title": clean_text(practical.get("title", ""), 200, "Practical title"),
            "intro": clean_text(practical.get("intro", ""), 800, "Practical intro"),
            "criteria": criteria,
            "prompts": prompts,
        }
    return out


def _text_list(value, field, max_items=20, max_len=500):
    if not isinstance(value, list):
        raise ApiError(400, f"{field} must be a list.", "invalid_input")
    items = [clean_text(item, max_len, field) for item in value if isinstance(item, str) and item.strip()]
    return items[:max_items]


def validate_lesson_payload(body):
    title = clean_text(body.get("title", ""), 160, "Lesson title")
    if len(title) < 3:
        raise ApiError(400, "Lesson title is too short.", "invalid_input")
    summary = clean_text(body.get("summary", ""), 500, "Summary")
    if len(summary) < 10:
        raise ApiError(400, "Add a one-sentence summary.", "invalid_input")
    try:
        minutes = int(body.get("minutes", 10))
    except (TypeError, ValueError):
        raise ApiError(400, "Minutes must be a number.", "invalid_input")
    if minutes < 1 or minutes > 180:
        raise ApiError(400, "Minutes must be between 1 and 180.", "invalid_input")

    raw = body.get("body") or {}
    if not isinstance(raw, dict):
        raise ApiError(400, "Lesson body must be an object.", "invalid_input")
    explanation = _text_list(raw.get("explanation", []), "Explanation", 20, 2000)
    if not explanation:
        raise ApiError(400, "Add at least one explanation paragraph.", "invalid_input")
    example = raw.get("example") or {}
    if not isinstance(example, dict):
        raise ApiError(400, "Example must be an object.", "invalid_input")
    example = {
        "title": clean_text(example.get("title", ""), 160, "Example title"),
        "text": clean_text(example.get("text", ""), 2000, "Example text"),
    }
    exercise = raw.get("exercise") or {}
    if not isinstance(exercise, dict):
        raise ApiError(400, "Exercise must be an object.", "invalid_input")
    exercise = {
        "prompt": clean_text(exercise.get("prompt", ""), 400, "Exercise prompt"),
        "steps": _text_list(exercise.get("steps", []), "Exercise steps", 20, 400),
    }
    if not exercise["prompt"]:
        raise ApiError(400, "Add the exercise prompt.", "invalid_input")
    return {
        "title": title,
        "minutes": minutes,
        "summary": summary,
        "body": {
            "explanation": explanation,
            "example": example,
            "do": _text_list(raw.get("do", []), "What to do", 20, 400),
            "dont": _text_list(raw.get("dont", []), "What not to do", 20, 400),
            "why": clean_text(raw.get("why", ""), 800, "Why it matters"),
            "mistakes": _text_list(raw.get("mistakes", []), "Common mistakes", 20, 400),
            "exercise": exercise,
        },
    }


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
