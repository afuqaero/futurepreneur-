"""Assessments: quizzes, scenarios, practical submission and templates."""

import json

from .. import content_repo
from ..clock import iso
from ..content_service import mcq_rows
from ..errors import ApiError, clean_text
from ..models import settings_public
from ..scoring import build_progress, is_pass, pass_mark, practical_latest, score_answers


def _published_module(conn):
    module = content_repo.get_module(conn, content_repo.DEFAULT_MODULE_ID, published_only=True)
    if not module:
        raise ApiError(404, "Module not available.", "not_found")
    return module


def handle(h, conn, method, path, user):
    if path.startswith("/api/assessment/") and path.endswith("/questions") and method == "GET":
        kind = path[len("/api/assessment/"):-len("/questions")].strip("/")
        if kind not in ("quiz", "scenario"):
            raise ApiError(404, "Assessment not found.", "not_found")
        module = _published_module(conn)
        rows = mcq_rows(conn, kind, module["id"])
        s = settings_public(conn)
        history = [dict(r) for r in conn.execute(
            "SELECT score, passed, created_at FROM attempts WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT 10",
            (user["id"], kind)).fetchall()]
        for item in history:
            item["passed"] = bool(item["passed"])
        h.send_json({
            "kind": kind,
            "questions": [{"id": r["id"], "component": r["component"], "topic": r["topic"],
                           "prompt": r["prompt"], "options": json.loads(r["options"])} for r in rows],
            "pass_mark": pass_mark(kind, s),
            "history": history,
        })
        return True

    if path.startswith("/api/assessment/") and path.endswith("/submit") and method == "POST":
        kind = path[len("/api/assessment/"):-len("/submit")].strip("/")
        if kind not in ("quiz", "scenario"):
            raise ApiError(404, "Assessment not found.", "not_found")
        body = h.read_json()
        answers = body.get("answers")
        if not isinstance(answers, dict):
            raise ApiError(400, "Answers must be an object.", "invalid_input")
        module = _published_module(conn)
        rows = mcq_rows(conn, kind, module["id"])
        if not rows:
            raise ApiError(400, "No questions are available.", "no_questions")
        score, detail, correct, total = score_answers(rows, answers)
        s = settings_public(conn)
        mark = pass_mark(kind, s)
        passed = is_pass(score, mark)
        conn.execute(
            "INSERT INTO attempts (user_id, kind, component, score, passed, detail, created_at) VALUES (?,?,?,?,?,?,?)",
            (user["id"], kind, module["component"], score, 1 if passed else 0,
             json.dumps({"detail": detail, "correct": correct, "total": total}), iso()),
        )
        conn.commit()
        wrong = [{"id": d["id"], "prompt": d["prompt"], "topic": d["topic"], "explanation": d["explanation"]}
                 for d in detail if not d["is_correct"]]
        h.send_json({
            "kind": kind, "score": score, "correct": correct, "total": total,
            "passed": passed, "pass_mark": mark, "detail": detail, "wrong": wrong,
            "progress": build_progress(conn, user),
        })
        return True

    if path == "/api/practical" and method == "GET":
        module = _published_module(conn)
        h.send_json({
            "practical": module["practical"],
            "submission": practical_latest(conn, user["id"]),
            "standards": settings_public(conn),
        })
        return True

    if path == "/api/practical/submit" and method == "POST":
        module = _published_module(conn)
        body = h.read_json()
        responses = body.get("responses")
        if not isinstance(responses, dict):
            raise ApiError(400, "Responses must be an object.", "invalid_input")
        cleaned = {}
        for prompt in (module["practical"].get("prompts") or []):
            val = clean_text(responses.get(prompt["id"], ""), 4000, prompt["label"])
            if len(val) < 30:
                raise ApiError(400, "Please give a fuller answer for every question (at least 30 characters).", "invalid_input")
            cleaned[prompt["id"]] = val
        conn.execute(
            "INSERT INTO practical_submissions (user_id, responses, status, created_at) VALUES (?,?,?,?)",
            (user["id"], json.dumps(cleaned), "pending", iso()),
        )
        conn.commit()
        h.send_json({
            "ok": True,
            "submission": practical_latest(conn, user["id"]),
            "message": "Submitted. A reviewer will score it against the rubric; your module is not marked passed until that review is complete.",
        }, 201)
        return True

    if path.startswith("/api/templates/") and method == "GET":
        slug = path[len("/api/templates/"):].strip("/")
        template = content_repo.get_template(conn, slug)
        if not template:
            raise ApiError(404, "Template not found.", "not_found")
        module = content_repo.get_module(conn, template["module_id"], published_only=True)
        if not module:
            raise ApiError(404, "Template not found.", "not_found")
        data = template["body"].encode("utf-8")
        h.send_bytes(
            data, "text/plain; charset=utf-8",
            extra={"Content-Disposition": f'attachment; filename="{template["filename"]}"', "Cache-Control": "no-store"},
        )
        return True

    return False
