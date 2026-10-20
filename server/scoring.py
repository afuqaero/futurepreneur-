"""Server-authoritative scoring, pass rules and the progress model.

Nothing here trusts the client: answers are scored against active questions in
the database, and module/mastery state is derived from stored attempts.
"""

import json

import content
from . import content_repo
from .ai import ai_status
from .models import public_user, settings_public


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_answers(questions, answers):
    detail = []
    correct = 0
    for q in questions:
        raw = answers.get(str(q["id"]), answers.get(q["id"]))
        try:
            chosen = int(raw)
        except (TypeError, ValueError):
            chosen = None
        ok = chosen == q["correct"]
        if ok:
            correct += 1
        detail.append({
            "id": q["id"],
            "prompt": q["prompt"],
            "options": json.loads(q["options"]),
            "chosen": chosen,
            "correct": q["correct"],
            "is_correct": ok,
            "explanation": q["explanation"],
            "topic": q["topic"],
        })
    total = len(questions)
    score = round(correct / total * 100) if total else 0
    return score, detail, correct, total


def pass_mark(kind, settings):
    return settings["quiz_pass"] if kind == "quiz" else settings["scenario_pass"]


def is_pass(score, mark):
    return score >= mark


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------


def diagnostic_summary(conn, user_id):
    row = conn.execute(
        "SELECT * FROM diagnostic_results WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    if not row:
        return None
    return {
        "overall": row["overall"],
        "components": json.loads(row["component_scores"]),
        "created_at": row["created_at"],
    }


def practical_latest(conn, user_id):
    row = conn.execute(
        "SELECT * FROM practical_submissions WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "responses": json.loads(row["responses"]),
        "status": row["status"],
        "rubric": json.loads(row["rubric"]) if row["rubric"] else None,
        "average": row["average"],
        "passed": bool(row["passed"]),
        "reviewer_note": row["reviewer_note"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
    }


def best_attempt(conn, user_id, kind):
    rows = conn.execute(
        "SELECT * FROM attempts WHERE user_id = ? AND kind = ? ORDER BY score DESC, id DESC", (user_id, kind)
    ).fetchall()
    if not rows:
        return None
    best = rows[0]
    return {
        "score": best["score"],
        "passed": bool(best["passed"]),
        "attempts": len(rows),
        "last_at": rows[0]["created_at"],
    }


def module_state(conn, user_id, module_id=content_repo.DEFAULT_MODULE_ID):
    s = settings_public(conn)
    module = content_repo.get_module(conn, module_id)
    lessons = module["lessons"] if module else []
    done_rows = conn.execute(
        "SELECT lesson_id FROM lesson_progress WHERE user_id = ?", (user_id,)
    ).fetchall()
    done = {r["lesson_id"] for r in done_rows}
    lessons_done = len([l for l in lessons if l["id"] in done])
    quiz = best_attempt(conn, user_id, "quiz")
    scenario = best_attempt(conn, user_id, "scenario")
    practical = practical_latest(conn, user_id)

    quiz_passed = bool(quiz and quiz["passed"])
    scenario_passed = bool(scenario and scenario["passed"])
    practical_passed = bool(practical and practical["passed"])
    module_passed = quiz_passed and scenario_passed and practical_passed

    total = len(lessons)
    percent = (
        (lessons_done / total) * 20 if total else 0
    ) + (30 if quiz_passed else 0) + (25 if scenario_passed else 0) + (25 if practical_passed else 0)
    return {
        "id": module_id,
        "title": module["title"] if module else "",
        "component": module["component"] if module else "",
        "status": module["status"] if module else "missing",
        "lessons_done": lessons_done,
        "lessons_total": total,
        "quiz": quiz,
        "scenario": scenario,
        "practical": practical,
        "quiz_passed": quiz_passed,
        "scenario_passed": scenario_passed,
        "practical_passed": practical_passed,
        "passed": module_passed,
        "percent": round(percent),
        "standards": {"quiz_pass": s["quiz_pass"], "scenario_pass": s["scenario_pass"], "rubric_min": s["rubric_min"]},
    }


def mastery_level(score):
    if score is None:
        return "Not assessed"
    if score >= 85:
        return "Optimising"
    if score >= 70:
        return "Structured"
    if score >= 50:
        return "Developing"
    return "Beginner"


def build_progress(conn, user):
    uid = user["id"]
    diag = diagnostic_summary(conn, uid)
    profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (uid,)).fetchone()
    mod = module_state(conn, uid)
    plan_rows = conn.execute("SELECT * FROM plan_items WHERE user_id = ? ORDER BY done, id", (uid,)).fetchall()
    plan = [dict(r) for r in plan_rows]
    plan_done = len([p for p in plan if p["done"]])
    plan_fraction = (plan_done / len(plan)) if plan else 0

    overall = 0
    if profile:
        overall += 10
    if diag:
        overall += 20
    overall += (mod["lessons_done"] / mod["lessons_total"] * 15) if mod["lessons_total"] else 0
    if mod["quiz_passed"]:
        overall += 20
    if mod["scenario_passed"]:
        overall += 15
    if mod["practical_passed"]:
        overall += 15
    overall += plan_fraction * 5
    overall = round(overall)

    if mod["passed"]:
        practical_avg = (mod["practical"] or {}).get("average") or 0
        quiz_score = (mod["quiz"] or {}).get("score") or 0
        level = "Optimising" if (quiz_score >= 90 and practical_avg >= 3.5 and plan_done >= 2) else "Structured"
        basis = "Verified module results"
    elif mod["quiz_passed"] or mod["scenario_passed"] or (mod["practical"] and mod["practical"]["status"] == "reviewed"):
        level = "Developing"
        basis = "Partial assessment results"
    elif diag:
        level = "Beginner"
        basis = "Diagnostic only — no module assessment passed yet"
    else:
        level = "Not assessed"
        basis = "No verified assessment yet"

    components = []
    for comp in content_repo.components_public(conn):
        score = (diag or {}).get("components", {}).get(comp["id"])
        status = "not-started"
        source = None
        level_c = "Not assessed"
        if comp["id"] == mod["component"] and mod["passed"]:
            status = "passed"
            level_c = "Optimising" if level == "Optimising" else "Structured"
            source = "Module verified"
        elif comp["id"] == mod["component"] and (mod["quiz_passed"] or mod["scenario_passed"]):
            status = "in-progress"
            level_c = "Developing"
            source = "Partial module results"
        elif score is not None:
            status = "diagnostic"
            source = "Diagnostic only — module not assessed"
        components.append({
            "id": comp["id"], "name": comp["name"], "short": comp["short"],
            "available": comp["available"], "score": score, "status": status,
            "mastery": level_c, "source": source,
        })

    attempts = [
        dict(r) for r in conn.execute(
            "SELECT kind, component, score, passed, created_at FROM attempts WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (uid,),
        ).fetchall()
    ]
    for a in attempts:
        a["passed"] = bool(a["passed"])

    next_steps = []
    if not profile:
        next_steps.append({"title": "Create your business profile", "detail": "Five questions so the platform can tailor your results.", "route": "checkup"})
    if not diag:
        next_steps.append({"title": "Take the 24-question Business Check-Up", "detail": "Identify strengths and weaknesses across all eight areas.", "route": "checkup"})
    if mod["lessons_done"] < mod["lessons_total"]:
        nxt = mod["lessons_done"] + 1
        next_steps.append({"title": f"Continue lesson {nxt} of {mod['lessons_total']}", "detail": "About 10 minutes, with a practical exercise.", "route": "module"})
    if not mod["quiz_passed"]:
        next_steps.append({"title": "Pass the knowledge quiz", "detail": f"Score {mod['standards']['quiz_pass']}% or higher. Retries are unlimited.", "route": "test"})
    if not mod["scenario_passed"]:
        next_steps.append({"title": "Try the scenario test", "detail": f"Five real-world decisions; pass mark {mod['standards']['scenario_pass']}%.", "route": "test"})
    if not mod["practical"]:
        next_steps.append({"title": "Submit the practical assignment", "detail": "Apply the module to your own business.", "route": "test"})
    elif mod["practical"]["status"] == "pending":
        next_steps.append({"title": "Practical assignment awaiting review", "detail": "A reviewer will score it against the rubric.", "route": "test"})
    elif mod["practical"]["status"] == "reviewed" and not mod["practical"]["passed"]:
        next_steps.append({"title": "Revise the practical assignment", "detail": "Read the reviewer note and resubmit.", "route": "test"})
    if mod["passed"] and len(next_steps) == 0:
        next_steps.append({"title": "Turn results into action", "detail": "Pick one item in your action plan and finish it this week.", "route": "progress"})

    return {
        "user": public_user(user),
        "profile": dict(profile) if profile else None,
        "diagnostic": diag,
        "module": mod,
        "overall_percent": overall,
        "mastery": {"level": level, "basis": basis},
        "components": components,
        "attempts": attempts,
        "plan": plan,
        "plan_done": plan_done,
        "next_steps": next_steps,
        "settings": settings_public(conn),
        "ai": ai_status(),
    }
