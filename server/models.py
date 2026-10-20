"""Small read models shared across routes."""


def get_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def _as_int(value, default):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def settings_public(conn):
    s = get_settings(conn)
    return {
        "quiz_pass": _as_int(s.get("quiz_pass"), 80),
        "scenario_pass": _as_int(s.get("scenario_pass"), 70),
        "rubric_min": _as_float(s.get("rubric_min"), 3.0),
        "rubric_floor": _as_int(s.get("rubric_floor"), 2),
        "platform_name": s.get("platform_name", "futurePreneur"),
    }


def public_user(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"],
    }
