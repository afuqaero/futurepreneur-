"""AI coach endpoint: persisted conversations, learner context and a request window."""

import re

from .. import coach_store, config
from ..ai import coach_endpoint
from ..errors import ApiError, clean_text
from ..scoring import build_progress


def _learner_context(conn, user):
    """Small, factual context so live coaching is not generic — and never invents results."""
    profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],)).fetchone()
    progress = build_progress(conn, user)
    bits = []
    if profile:
        bits.append(
            f"Business: {profile['business_name']} · {profile['sector']} · {profile['stage']} · "
            f"{profile['team_size']} people · {profile['years']} · {profile['revenue_band']} monthly revenue."
        )
        bits.append(f"Owner's stated main challenge: {profile['main_challenge']}")
    else:
        bits.append("Business profile: not completed yet.")

    weak = sorted(
        [c for c in progress["components"] if c["score"] is not None],
        key=lambda c: c["score"],
    )[:3]
    if weak:
        bits.append("Weakest check-up areas (self-assessed): " + ", ".join(
            f"{c['name']} {c['score']}%" for c in weak
        ) + ".")
    verified = [m["title"] for m in progress["modules"] if m["passed"]]
    if verified:
        bits.append("Verified modules: " + ", ".join(verified) + ".")
    else:
        bits.append("Verified modules: none yet.")
    bits.append(
        "Use this context only to make examples relevant. Never treat the check-up as a verified score, "
        "and never claim a module is passed unless it is listed as verified."
    )
    return "Learner context (private, do not quote back verbatim):\n" + "\n".join(bits)


def _clean_messages(raw):
    if not isinstance(raw, list):
        raise ApiError(400, "Messages must be a list.", "invalid_input")
    cleaned = []
    for item in raw[-12:]:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            continue
        text = item.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        cleaned.append({"role": item["role"], "content": text.strip()[:4000]})
    if not cleaned or cleaned[-1]["role"] != "user":
        raise ApiError(400, "Send a message to the coach.", "invalid_input")
    return cleaned


def _session_or_404(conn, user, session_id):
    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        raise ApiError(404, "Conversation not found.", "not_found")
    session = coach_store.get_session(conn, user["id"], session_id)
    if not session:
        raise ApiError(404, "Conversation not found.", "not_found")
    return session


def _session_payload(session):
    return {
        "id": session["id"], "mode": session["mode"], "title": session["title"],
        "created_at": session["created_at"], "updated_at": session["updated_at"],
    }


def handle(h, conn, method, path, user):
    if path == "/api/coach" and method == "POST":
        body = h.read_json()
        mode = body.get("mode", "teach")
        if mode not in coach_store.MODES:
            raise ApiError(400, "Unknown coach mode.", "invalid_input")

        session = None
        if body.get("session_id") not in (None, ""):
            session = _session_or_404(conn, user, body.get("session_id"))

        if body.get("message") is not None:
            user_text = clean_text(body.get("message"), 4000, "Message")
            if not user_text:
                raise ApiError(400, "Send a message to the coach.", "invalid_input")
            history = coach_store.messages(conn, session["id"]) if session else []
        else:
            cleaned = _clean_messages(body.get("messages"))
            user_text = cleaned[-1]["content"]
            history = cleaned[:-1]

        retry = coach_store.record_request(
            conn, user["id"], config.COACH_RATE_LIMIT, config.COACH_RATE_WINDOW
        )
        if retry:
            raise ApiError(
                429,
                f"Coach limit reached ({config.COACH_RATE_LIMIT} messages per "
                f"{config.COACH_RATE_WINDOW // 60} minutes). Try again in about {retry} seconds.",
                "rate_limited",
                {"Retry-After": str(retry)},
            )

        if session is None:
            session = coach_store.create_session(conn, user["id"], mode, user_text)
        elif session["mode"] != mode:
            coach_store.set_mode(conn, session["id"], mode)
            session["mode"] = mode

        context = history[-10:] + [{"role": "user", "content": user_text}]
        result = coach_endpoint(context, mode, _learner_context(conn, user), conn)

        coach_store.append(conn, session["id"], "user", user_text)
        coach_store.append(conn, session["id"], "assistant", result["reply"])
        coach_store.set_title(conn, session["id"], user_text)
        conn.commit()

        session = coach_store.get_session(conn, user["id"], session["id"])
        h.send_json({
            **result,
            "session": _session_payload(session),
            "session_id": session["id"],
        })
        return True

    if path == "/api/coach/sessions" and method == "GET":
        h.send_json({"sessions": coach_store.list_sessions(conn, user["id"])})
        return True

    match = re.fullmatch(r"/api/coach/sessions/(\d+)", path)
    if match:
        session = _session_or_404(conn, user, match.group(1))
        if method == "GET":
            h.send_json({
                "session": _session_payload(session),
                "messages": coach_store.messages(conn, session["id"]),
            })
            return True
        if method == "DELETE":
            coach_store.delete_session(conn, user["id"], session["id"])
            h.send_json({"ok": True})
            return True

    if path == "/api/coach/sessions" and method == "DELETE":
        coach_store.delete_all(conn, user["id"])
        h.send_json({"ok": True})
        return True

    return False
