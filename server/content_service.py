"""Content reads: the module, its overrides, and active question rows."""

from copy import deepcopy

import content


def get_module_content(conn):
    module = deepcopy(content.MODULE)
    overrides = {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM content_overrides").fetchall()
    }
    for lesson in module["lessons"]:
        for field in ("title", "summary", "explanation"):
            key = f"lesson:{lesson['id']}:{field}"
            if key in overrides:
                lesson[field] = overrides[key].split("\n\n") if field == "explanation" else overrides[key]
    if "module:tagline" in overrides:
        module["tagline"] = overrides["module:tagline"]
    if "module:intro" in overrides:
        module["intro"] = overrides["module:intro"].split("\n\n")
    return module


def mcq_rows(conn, kind):
    return conn.execute(
        "SELECT * FROM questions WHERE kind = ? AND active = 1 ORDER BY position, id", (kind,)
    ).fetchall()
