"""Assessments: quizzes, scenarios, practical submission and templates."""

import json

import content
from ..clock import iso
from ..content_service import mcq_rows
from ..errors import ApiError, clean_text
from ..models import settings_public
from ..scoring import build_progress, is_pass, pass_mark, score_answers


def handle(h, conn, method, path, user):
    if path.startswith("/api/assessment/") and path.endswith("/questions") and method == "GET":
        kind = path[len("/api/assessment/"):-len("/questions")].strip("/")
        if kind not in ("quiz", "scenario"):
            raise ApiError(404, "Assessment not found.", "not_found")
        rows = mcq_rows(conn, kind)
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
        rows = mcq_rows(conn, kind)
        if not rows:
            raise ApiError(400, "No questions are available.", "no_questions")
        score, detail, correct, total = score_answers(rows, answers)
        s = settings_public(conn)
        mark = pass_mark(kind, s)
        passed = is_pass(score, mark)
        conn.execute(
            "INSERT INTO attempts (user_id, kind, component, score, passed, detail, created_at) VALUES (?,?,?,?,?,?,?)",
            (user["id"], kind, "strategy", score, 1 if passed else 0,
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
        from ..scoring import practical_latest

        h.send_json({
            "practical": content.MODULE["practical"],
            "submission": practical_latest(conn, user["id"]),
            "standards": settings_public(conn),
        })
        return True

    if path == "/api/practical/submit" and method == "POST":
        from ..scoring import practical_latest

        body = h.read_json()
        responses = body.get("responses")
        if not isinstance(responses, dict):
            raise ApiError(400, "Responses must be an object.", "invalid_input")
        cleaned = {}
        for prompt in content.MODULE["practical"]["prompts"]:
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
        if slug not in content.TEMPLATE_FILES:
            raise ApiError(404, "Template not found.", "not_found")
        meta = next((t for t in content.MODULE["templates"] if t["slug"] == slug), None)
        filename = meta["filename"] if meta else f"{slug}.txt"
        data = content.TEMPLATE_FILES[slug].encode("utf-8")
        h.send_bytes(
            data, "text/plain; charset=utf-8",
            extra={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
        )
        return True

    return False
