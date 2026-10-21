"""Assessments: quizzes, scenarios, practical submission and templates.

All assessment routes are module-scoped: a quiz answer can only ever be scored
against questions that belong to the module being attempted. The legacy
`/api/assessment/...` and `/api/practical` paths stay as aliases for the
default Strategy module so older clients and tests keep working.
"""

import json
import re

from .. import content_repo, remediation, template_files
from ..clock import iso
from ..content_service import mcq_rows
from ..errors import ApiError, clean_text
from ..models import settings_public
from ..scoring import build_progress, is_pass, pass_mark, practical_latest, score_answers

MODULE_ASSESSMENT_RE = re.compile(r"/api/module/([\w-]+)/assessment/(quiz|scenario)/(questions|submit)")
MODULE_PRACTICAL_RE = re.compile(r"/api/module/([\w-]+)/practical(?:/submit)?")
LEGACY_ASSESSMENT_RE = re.compile(r"/api/assessment/(quiz|scenario)/(questions|submit)")


def _published_module(conn, module_id):
    module = content_repo.get_module(conn, module_id, published_only=True)
    if not module:
        raise ApiError(404, "Module not available.", "not_found")
    return module


def _module_brief(module):
    return {"id": module["id"], "title": module["title"], "component": module["component"]}


def _questions_payload(conn, module, kind, user):
    rows = mcq_rows(conn, kind, module["id"])
    if not rows:
        raise ApiError(400, "No questions are available for this assessment.", "no_questions")
    s = settings_public(conn)
    history = [dict(r) for r in conn.execute(
        "SELECT score, passed, created_at FROM attempts"
        " WHERE user_id = ? AND kind = ? AND module_id = ? ORDER BY id DESC LIMIT 10",
        (user["id"], kind, module["id"])).fetchall()]
    for item in history:
        item["passed"] = bool(item["passed"])
    return {
        "kind": kind,
        "module": _module_brief(module),
        "questions": [
            {"id": r["id"], "component": r["component"], "topic": r["topic"],
             "prompt": r["prompt"], "options": json.loads(r["options"])}
            for r in rows
        ],
        "pass_mark": pass_mark(kind, s),
        "history": history,
    }


def _submit_answers(h, conn, module, kind, user):
    body = h.read_json()
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise ApiError(400, "Answers must be an object.", "invalid_input")
    rows = mcq_rows(conn, kind, module["id"])
    if not rows:
        raise ApiError(400, "No questions are available for this assessment.", "no_questions")
    score, detail, correct, total = score_answers(rows, answers)

    by_id = {r["id"]: r for r in rows}
    for item in detail:
        source = by_id.get(item["id"])
        item["lesson"] = remediation.lesson_for(
            module, item["id"],
            topic=source["topic"] if source else item.get("topic", ""),
            prompt=source["prompt"] if source else item.get("prompt", ""),
        )

    s = settings_public(conn)
    mark = pass_mark(kind, s)
    passed = is_pass(score, mark)
    conn.execute(
        "INSERT INTO attempts (user_id, module_id, kind, component, score, passed, detail, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (user["id"], module["id"], kind, module["component"], score, 1 if passed else 0,
         json.dumps({"detail": detail, "correct": correct, "total": total}), iso()),
    )
    conn.commit()

    wrong = [d for d in detail if not d["is_correct"]]
    remediation_lessons = []
    seen = set()
    for d in wrong:
        lesson = d.get("lesson")
        if lesson and lesson["id"] not in seen:
            seen.add(lesson["id"])
            remediation_lessons.append(lesson)
    h.send_json({
        "kind": kind,
        "module": _module_brief(module),
        "score": score,
        "correct": correct,
        "total": total,
        "passed": passed,
        "pass_mark": mark,
        "detail": detail,
        "wrong": [
            {"id": d["id"], "prompt": d["prompt"], "topic": d["topic"],
             "explanation": d["explanation"], "lesson": d.get("lesson")}
            for d in wrong
        ],
        "remediation": remediation_lessons,
        "progress": build_progress(conn, user),
    })
    return True


def _practical_payload(conn, module, user):
    return {
        "module": _module_brief(module),
        "practical": module["practical"],
        "submission": practical_latest(conn, user["id"], module["id"]),
        "standards": settings_public(conn),
    }


def _submit_practical(h, conn, module, user):
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
        "INSERT INTO practical_submissions (user_id, module_id, responses, status, created_at) VALUES (?,?,?,?,?)",
        (user["id"], module["id"], json.dumps(cleaned), "pending", iso()),
    )
    conn.commit()
    h.send_json({
        "ok": True,
        "module": _module_brief(module),
        "submission": practical_latest(conn, user["id"], module["id"]),
        "message": "Submitted. A reviewer will score it against the rubric; your module is not marked passed until that review is complete.",
    }, 201)
    return True


def handle(h, conn, method, path, user):
    match = MODULE_ASSESSMENT_RE.fullmatch(path)
    legacy = LEGACY_ASSESSMENT_RE.fullmatch(path)
    if match or legacy:
        module_id = match.group(1) if match else content_repo.DEFAULT_MODULE_ID
        kind = match.group(2) if match else legacy.group(1)
        action = match.group(3) if match else legacy.group(2)
        module = _published_module(conn, module_id)
        if action == "questions" and method == "GET":
            h.send_json(_questions_payload(conn, module, kind, user))
            return True
        if action == "submit" and method == "POST":
            return _submit_answers(h, conn, module, kind, user)

    match = MODULE_PRACTICAL_RE.fullmatch(path)
    if match:
        module_id = match.group(1)
        submit = path.endswith("/submit")
        module = _published_module(conn, module_id)
        if not submit and method == "GET":
            h.send_json(_practical_payload(conn, module, user))
            return True
        if submit and method == "POST":
            return _submit_practical(h, conn, module, user)

    if path == "/api/practical" and method == "GET":
        module = _published_module(conn, content_repo.DEFAULT_MODULE_ID)
        h.send_json(_practical_payload(conn, module, user))
        return True

    if path == "/api/practical/submit" and method == "POST":
        module = _published_module(conn, content_repo.DEFAULT_MODULE_ID)
        return _submit_practical(h, conn, module, user)

    if path.startswith("/api/templates/") and method == "GET":
        slug = path[len("/api/templates/"):].strip("/")
        template = content_repo.get_template(conn, slug)
        module_id = template["module_id"] if template else None
        local_path = None
        if template:
            local_path = template_files.override_for(slug)
        else:
            hit = template_files.find_custom(slug)
            if not hit:
                raise ApiError(404, "Template not found.", "not_found")
            local_path, module_id = hit
        module = content_repo.get_module(conn, module_id, published_only=True)
        if not module:
            raise ApiError(404, "Template not found.", "not_found")
        if local_path:
            if not template_files.send(h, local_path):
                raise ApiError(404, "Template file is too large to serve.", "not_found")
            return True
        if not template:
            raise ApiError(404, "Template not found.", "not_found")
        data = template["body"].encode("utf-8")
        h.send_bytes(
            data, "text/plain; charset=utf-8",
            extra={"Content-Disposition": f'attachment; filename="{template["filename"]}"', "Cache-Control": "no-store"},
        )
        return True

    return False
