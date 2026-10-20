"""Business Check-Up: profile, diagnostic questions and submission."""

import json
from datetime import timedelta

import content
from .. import content_repo
from ..clock import iso, utcnow
from ..content_service import mcq_rows
from ..errors import ApiError, clean_text
from ..scoring import build_progress, diagnostic_summary, score_answers


def _priority_payload(conn, component_id, score):
    module_row = conn.execute(
        "SELECT id FROM modules WHERE component = ? AND status = 'published'", (component_id,)
    ).fetchone()
    module_id = module_row["id"] if module_row else None
    lessons = []
    if module_id:
        module = content_repo.get_module(conn, module_id)
        lessons = [lesson["title"] for lesson in (module["lessons"][:2] if module else [])]
    return {
        "component": component_id,
        "name": content.COMPONENT_BY_ID[component_id]["name"],
        "score": score,
        "recommendation": content.DIAGNOSTIC_RECOMMENDATIONS[component_id],
        "available": module_id is not None,
        "module_id": module_id,
        "lessons": lessons,
    }


def handle(h, conn, method, path, user):
    if path == "/api/profile" and method == "PUT":
        body = h.read_json()
        fields = {}
        limits = {"business_name": 100, "sector": 60, "stage": 40, "team_size": 20,
                  "revenue_band": 40, "years": 20, "main_challenge": 600}
        for key, limit in limits.items():
            val = clean_text(body.get(key, ""), limit, key.replace("_", " ").title())
            if not val:
                raise ApiError(400, "Please complete all profile fields.", "invalid_input")
            fields[key] = val
        conn.execute(
            "INSERT INTO profiles (user_id, business_name, sector, stage, team_size, revenue_band, years, main_challenge, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET"
            " business_name=excluded.business_name, sector=excluded.sector, stage=excluded.stage,"
            " team_size=excluded.team_size, revenue_band=excluded.revenue_band, years=excluded.years,"
            " main_challenge=excluded.main_challenge, updated_at=excluded.updated_at",
            (user["id"], fields["business_name"], fields["sector"], fields["stage"], fields["team_size"],
             fields["revenue_band"], fields["years"], fields["main_challenge"], iso()),
        )
        conn.commit()
        h.send_json({"ok": True, "progress": build_progress(conn, user)})
        return True

    if path == "/api/checkup" and method == "GET":
        rows = mcq_rows(conn, "diagnostic")
        questions = [{
            "id": r["id"], "component": r["component"], "topic": r["topic"], "prompt": r["prompt"],
            "options": json.loads(r["options"]),
        } for r in rows]
        profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],)).fetchone()
        history_rows = conn.execute(
            "SELECT overall, component_scores, created_at FROM diagnostic_results"
            " WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (user["id"],),
        ).fetchall()
        history = [{
            "overall": r["overall"],
            "components": json.loads(r["component_scores"]),
            "created_at": r["created_at"],
        } for r in history_rows]
        h.send_json({
            "questions": questions,
            "profile": dict(profile) if profile else None,
            "result": diagnostic_summary(conn, user["id"]),
            "history": history,
        })
        return True

    if path == "/api/checkup/submit" and method == "POST":
        body = h.read_json()
        answers = body.get("answers")
        if not isinstance(answers, dict):
            raise ApiError(400, "Answers must be an object.", "invalid_input")
        rows = mcq_rows(conn, "diagnostic")
        if not rows:
            raise ApiError(400, "No diagnostic questions are available.", "no_questions")
        score, detail, correct, total = score_answers(rows, answers)
        per = {}
        counts = {}
        for d in detail:
            comp = next(r["component"] for r in rows if r["id"] == d["id"])
            counts.setdefault(comp, [0, 0])
            counts[comp][1] += 1
            if d["is_correct"]:
                counts[comp][0] += 1
        for comp, (c, t) in counts.items():
            per[comp] = round(c / t * 100) if t else 0
        previous_row = conn.execute(
            "SELECT overall, component_scores, created_at FROM diagnostic_results"
            " WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        previous = None
        if previous_row:
            previous = {
                "overall": previous_row["overall"],
                "components": json.loads(previous_row["component_scores"]),
                "created_at": previous_row["created_at"],
            }
        conn.execute(
            "INSERT INTO diagnostic_results (user_id, answers, component_scores, overall, created_at) VALUES (?,?,?,?,?)",
            (user["id"], json.dumps(answers), json.dumps(per), score, iso()),
        )
        # Seed a starting action plan from the three weakest areas, once.
        if not conn.execute("SELECT id FROM plan_items WHERE user_id = ?", (user["id"],)).fetchone():
            weakest = sorted(per.items(), key=lambda kv: kv[1])[:3]
            for comp_id, comp_score in weakest:
                comp = content.COMPONENT_BY_ID[comp_id]
                conn.execute(
                    "INSERT INTO plan_items (user_id, title, detail, due, done, created_at) VALUES (?,?,?,?,?,?)",
                    (user["id"],
                     f"Improve {comp['name'].lower()}",
                     content.DIAGNOSTIC_RECOMMENDATIONS[comp_id],
                     (utcnow() + timedelta(days=14)).date().isoformat(), 0, iso()),
                )
        conn.commit()
        result = diagnostic_summary(conn, user["id"])
        priorities = sorted(per.items(), key=lambda kv: kv[1])[:3]
        strengths = sorted(per.items(), key=lambda kv: kv[1], reverse=True)[:2]
        change = None
        if previous:
            change = {
                "overall": score - previous["overall"],
                "components": {
                    comp: per.get(comp, 0) - previous["components"].get(comp, 0)
                    for comp in per
                },
            }
        h.send_json({
            "result": result,
            "score": score,
            "correct": correct,
            "total": total,
            "priorities": [_priority_payload(conn, c, s) for c, s in priorities],
            "strengths": [{"component": c, "name": content.COMPONENT_BY_ID[c]["name"], "score": s} for c, s in strengths],
            "previous": previous,
            "change": change,
            "progress": build_progress(conn, user),
        })
        return True

    return False
