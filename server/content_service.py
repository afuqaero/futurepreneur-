"""Content reads shared by learner endpoints."""

from . import content_repo


def get_module_content(conn, module_id=content_repo.DEFAULT_MODULE_ID, published_only=True):
    return content_repo.get_module(conn, module_id, published_only=published_only)


def mcq_rows(conn, kind, module_id=None):
    if module_id:
        return conn.execute(
            "SELECT * FROM questions WHERE kind = ? AND active = 1 AND (module_id = ? OR module_id IS NULL)"
            " ORDER BY position, id",
            (kind, module_id),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM questions WHERE kind = ? AND active = 1 ORDER BY position, id", (kind,)
    ).fetchall()
