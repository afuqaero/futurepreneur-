"""Persistence for coach conversations and the per-user request window."""

from datetime import timedelta

from .clock import iso, utcnow

MODES = ("teach", "solve", "test")


def create_session(conn, user_id, mode, title=""):
    now = iso()
    cur = conn.execute(
        "INSERT INTO coach_sessions (user_id, mode, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (user_id, mode, title[:90], now, now),
    )
    conn.commit()
    return get_session(conn, user_id, cur.lastrowid)


def get_session(conn, user_id, session_id):
    row = conn.execute(
        "SELECT * FROM coach_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def list_sessions(conn, user_id, limit=8):
    rows = conn.execute(
        "SELECT s.*,"
        " (SELECT content FROM coach_messages m WHERE m.session_id = s.id ORDER BY m.id DESC LIMIT 1) AS preview,"
        " (SELECT COUNT(*) FROM coach_messages m WHERE m.session_id = s.id) AS message_count"
        " FROM coach_sessions s WHERE s.user_id = ? ORDER BY s.updated_at DESC, s.id DESC LIMIT ?",
        (user_id, max(1, min(limit, 30))),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        preview = item.get("preview") or ""
        item["preview"] = preview[:140]
        out.append(item)
    return out


def messages(conn, session_id, limit=40):
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM coach_messages WHERE session_id = ?"
        " ORDER BY id ASC LIMIT ?",
        (session_id, max(1, min(limit, 100))),
    ).fetchall()
    return [dict(r) for r in rows]


def append(conn, session_id, role, content):
    conn.execute(
        "INSERT INTO coach_messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
        (session_id, role, content, iso()),
    )
    conn.execute("UPDATE coach_sessions SET updated_at = ? WHERE id = ?", (iso(), session_id))


def set_title(conn, session_id, title):
    conn.execute("UPDATE coach_sessions SET title = ? WHERE id = ? AND title = ''", (title[:90], session_id))


def set_mode(conn, session_id, mode):
    conn.execute("UPDATE coach_sessions SET mode = ?, updated_at = ? WHERE id = ?", (mode, iso(), session_id))


def delete_session(conn, user_id, session_id):
    conn.execute("DELETE FROM coach_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
    conn.commit()


def delete_all(conn, user_id):
    conn.execute("DELETE FROM coach_sessions WHERE user_id = ?", (user_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Rate window
# ---------------------------------------------------------------------------


def record_request(conn, user_id, limit, window_seconds):
    """Return retry-after seconds when over the limit, otherwise record and return 0."""
    now = utcnow()
    cutoff = iso(now - timedelta(seconds=window_seconds))
    rows = conn.execute(
        "SELECT created_at FROM coach_rate_events WHERE user_id = ? AND created_at >= ?"
        " ORDER BY id ASC",
        (user_id, cutoff),
    ).fetchall()
    if len(rows) >= limit:
        oldest = rows[0]["created_at"]
        try:
            from datetime import datetime

            oldest_dt = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
            retry = int((oldest_dt + timedelta(seconds=window_seconds) - now).total_seconds()) + 1
        except Exception:
            retry = window_seconds
        return max(1, retry)

    conn.execute(
        "INSERT INTO coach_rate_events (user_id, created_at) VALUES (?,?)", (user_id, iso(now))
    )
    # Keep the table small; nothing older than a day is needed for a 10-minute window.
    conn.execute(
        "DELETE FROM coach_rate_events WHERE user_id = ? AND created_at < ?",
        (user_id, iso(now - timedelta(days=1))),
    )
    conn.commit()
    return 0
