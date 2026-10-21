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


def practical_latest(conn, user_id, module_id=content_repo.DEFAULT_MODULE_ID):
    row = conn.execute(
        "SELECT * FROM practical_submissions WHERE user_id = ? AND module_id = ? ORDER BY id DESC LIMIT 1",
        (user_id, module_id),
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


def best_attempt(conn, user_id, kind, module_id=content_repo.DEFAULT_MODULE_ID):
    rows = conn.execute(
        "SELECT * FROM attempts WHERE user_id = ? AND kind = ? AND module_id = ?"
        " ORDER BY score DESC, id DESC",
        (user_id, kind, module_id),
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
    quiz = best_attempt(conn, user_id, "quiz", module_id)
    scenario = best_attempt(conn, user_id, "scenario", module_id)
    practical = practical_latest(conn, user_id, module_id)

    quiz_passed = bool(quiz and quiz["passed"])
    scenario_passed = bool(scenario and scenario["passed"])
    practical_passed = bool(practical and practical["passed"])
    module_passed = quiz_passed and scenario_passed and practical_passed

    total = len(lessons)
    percent = (
        (lessons_done / total) * 20 if total else 0
    ) + (30 if quiz_passed else 0) + (25 if scenario_passed else 0) + (25 if practical_passed else 0)
    if module_passed:
        percent = 100
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


def _focus_module(modules):
    if not modules:
        return None
    started = [m for m in modules if m["lessons_done"] or m["quiz"] or m["scenario"] or m["practical"]]
    incomplete = [m for m in modules if not m["passed"]]
    if incomplete:
        for module in incomplete:
            if module in started:
                return module
        return incomplete[0]
    return modules[0]


def build_progress(conn, user):
    uid = user["id"]
    diag = diagnostic_summary(conn, uid)
    profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (uid,)).fetchone()
    modules = [
        module_state(conn, uid, row["id"])
        for row in content_repo.list_modules(conn, published_only=True)
    ]
    default_module = next((m for m in modules if m["id"] == content_repo.DEFAULT_MODULE_ID), modules[0] if modules else None)
    focus = _focus_module(modules)
    passed_modules = [m for m in modules if m["passed"]]
    modules_passed = len(passed_modules)
    modules_total = len(modules)

    plan_rows = conn.execute("SELECT * FROM plan_items WHERE user_id = ? ORDER BY done, id", (uid,)).fetchall()
    plan = [dict(r) for r in plan_rows]
    plan_done = len([p for p in plan if p["done"]])

    overall = round(sum(m["percent"] for m in modules) / modules_total) if modules_total else 0

    any_assessment = any(m["quiz"] or m["scenario"] or m["practical"] for m in modules)
    if passed_modules:
        quiz_scores = [m["quiz"]["score"] for m in passed_modules if m["quiz"]]
        practical_avgs = [m["practical"]["average"] for m in passed_modules if m["practical"] and m["practical"]["average"] is not None]
        avg_quiz = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0
        avg_practical = sum(practical_avgs) / len(practical_avgs) if practical_avgs else 0
        if avg_quiz >= 90 and avg_practical >= 3.5 and plan_done >= 1:
            level = "Optimising"
            basis = f"{modules_passed} of {modules_total} modules verified · quiz {round(avg_quiz)}% · practical {avg_practical:.2f}/4"
        else:
            level = "Structured"
            basis = f"{modules_passed} of {modules_total} modules fully verified"
    elif any_assessment:
        level = "Developing"
        basis = "Assessment attempts recorded — complete all three criteria to pass a module"
    elif diag:
        level = "Beginner"
        basis = "Diagnostic only — no module assessment passed yet"
    else:
        level = "Not assessed"
        basis = "No verified assessment yet"

    by_component = {m["component"]: m for m in modules}
    components = []
    for comp in content_repo.components_public(conn):
        score = (diag or {}).get("components", {}).get(comp["id"])
        module = by_component.get(comp["id"])
        status = "not-started"
        source = None
        level_c = "Not assessed"
        if module and module["passed"]:
            status = "passed"
            quiz_score = (module["quiz"] or {}).get("score") or 0
            practical_avg = (module["practical"] or {}).get("average") or 0
            level_c = "Optimising" if quiz_score >= 90 and practical_avg >= 3.5 else "Structured"
            source = "Module verified"
        elif module and (module["quiz_passed"] or module["scenario_passed"] or module["practical"]):
            status = "in-progress"
            level_c = "Developing"
            source = "Partial module results"
        elif score is not None:
            status = "diagnostic"
            source = "Diagnostic only — module not assessed"
        components.append({
            "id": comp["id"], "name": comp["name"], "short": comp["short"],
            "available": comp["available"], "module_id": comp["module_id"],
            "score": score, "status": status, "mastery": level_c, "source": source,
        })

    attempts = [
        dict(r) for r in conn.execute(
            "SELECT a.kind, a.module_id, a.component, a.score, a.passed, a.created_at, m.title AS module_title"
            " FROM attempts a LEFT JOIN modules m ON m.id = a.module_id"
            " WHERE a.user_id = ? ORDER BY a.id DESC LIMIT 40",
            (uid,),
        ).fetchall()
    ]
    for item in attempts:
        item["passed"] = bool(item["passed"])

    trend = [
        {
            "kind": a["kind"], "score": a["score"], "passed": a["passed"],
            "module_title": a.get("module_title") or a.get("component"),
            "created_at": a["created_at"],
        }
        for a in reversed(attempts[:12])
    ]

    next_steps = []
    if not profile:
        next_steps.append({"title": "Create your business profile", "detail": "A few questions so the check-up and coaching fit your business.", "route": "checkup"})
    if not diag:
        next_steps.append({"title": "Take the 24-question Business Check-Up", "detail": "Identify strengths and weaknesses across all eight areas.", "route": "checkup"})
    if focus:
        if focus["passed"]:
            next_steps.append({"title": "Turn your results into action", "detail": "Pick one item in your improvement plan and finish it this week.", "route": "progress"})
        elif focus["lessons_done"] < focus["lessons_total"]:
            nxt = focus["lessons_done"] + 1
            next_steps.append({
                "title": f"Continue {focus['title']}: lesson {nxt} of {focus['lessons_total']}",
                "detail": "About 10 minutes, with a practical exercise you can apply this week.",
                "route": f"learn/{focus['id']}",
            })
        elif not focus["quiz_passed"]:
            next_steps.append({
                "title": f"Pass the {focus['title']} knowledge quiz",
                "detail": f"Score {focus['standards']['quiz_pass']}% or higher. Retries are unlimited.",
                "route": f"test/{focus['id']}/quiz",
            })
        elif not focus["scenario_passed"]:
            next_steps.append({
                "title": f"Try the {focus['title']} scenario test",
                "detail": f"Real decisions with a {focus['standards']['scenario_pass']}% pass mark.",
                "route": f"test/{focus['id']}/scenario",
            })
        elif not focus["practical"]:
            next_steps.append({
                "title": f"Submit the {focus['title']} practical",
                "detail": "Apply the module to your own business and send it for review.",
                "route": f"test/{focus['id']}/practical",
            })
        elif focus["practical"]["status"] == "pending":
            next_steps.append({
                "title": f"{focus['title']} practical is awaiting review",
                "detail": "A reviewer will score it against the rubric before the module can pass.",
                "route": f"test/{focus['id']}/practical",
            })
        elif focus["practical"]["status"] == "reviewed" and not focus["practical"]["passed"]:
            next_steps.append({
                "title": f"Revise the {focus['title']} practical",
                "detail": "Read the reviewer note and resubmit with the gaps fixed.",
                "route": f"test/{focus['id']}/practical",
            })

    return {
        "user": public_user(user),
        "profile": dict(profile) if profile else None,
        "diagnostic": diag,
        "modules": modules,
        "modules_passed": modules_passed,
        "modules_total": modules_total,
        "focus_module": focus,
        "module": default_module,
        "overall_percent": overall,
        "mastery": {"level": level, "basis": basis},
        "components": components,
        "attempts": attempts,
        "trend": trend,
        "plan": plan,
        "plan_done": plan_done,
        "next_steps": next_steps,
        "settings": settings_public(conn),
        "ai": ai_status(conn),
    }
