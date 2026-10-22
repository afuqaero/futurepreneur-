"""Drop-in template files.

Two ways to use your own files, no code changes required:

1. ``content/templates/<slug>.<ext>`` replaces the generated download for an
   existing template (same slug as shown in the admin template editor).
2. ``content/templates/<module-id>/<any-name>.<ext>`` adds an extra download
   to that module, titled from the filename.

Files are scanned per request, so dropping a file in takes effect immediately.
Only whitelisted document extensions are served.
"""

import hashlib
import re
from pathlib import Path
from urllib.parse import quote

from . import config

# extension -> (short label, content type)
FORMATS = {
    ".pdf": ("PDF", "application/pdf"),
    ".docx": ("DOC", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("XLS", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".pptx": ("PPT", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".csv": ("CSV", "text/csv; charset=utf-8"),
    ".md": ("MD", "text/markdown; charset=utf-8"),
    ".txt": ("TXT", "text/plain; charset=utf-8"),
    ".zip": ("ZIP", "application/zip"),
    ".png": ("PNG", "image/png"),
    ".jpg": ("JPG", "image/jpeg"),
    ".jpeg": ("JPG", "image/jpeg"),
}

SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_BYTES = 10 * 1024 * 1024


def base_dir():
    return Path(config.TEMPLATES_DIR)


def _meta(path):
    return FORMATS[path.suffix.lower()]


def override_for(slug):
    """A file named exactly <slug>.<ext> replaces the built-in template."""
    if not SAFE_ID.fullmatch(slug or ""):
        return None
    for ext in FORMATS:
        candidate = base_dir() / f"{slug}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _module_dir(module_id):
    if not SAFE_ID.fullmatch(module_id or ""):
        return None
    return base_dir() / module_id


def custom_files(module_id):
    folder = _module_dir(module_id)
    if not folder or not folder.is_dir():
        return []
    files = [
        p for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in FORMATS and not p.name.startswith(".")
    ]
    return files


def custom_slug(module_id, path):
    digest = hashlib.sha1(f"{module_id}/{path.name}".encode("utf-8")).hexdigest()[:12]
    return f"local-{digest}"


def find_custom(slug):
    """Return (path, module_id) for a generated local slug, or None."""
    if not slug.startswith("local-"):
        return None
    root = base_dir()
    if not root.is_dir():
        return None
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not SAFE_ID.fullmatch(folder.name):
            continue
        for path in custom_files(folder.name):
            if custom_slug(folder.name, path) == slug:
                return path, folder.name
    return None


def _title_from(stem):
    text = re.sub(r"[-_]+", " ", stem).strip()
    return text[:1].upper() + text[1:] if text else "Template"


def decorate(module):
    """Add file overrides and folder-added files to a module payload."""
    templates = []
    for item in module.get("templates", []):
        row = dict(item)
        path = override_for(row["slug"])
        if path:
            label, _ = _meta(path)
            row.update({"format": label, "filename": path.name, "source": "file"})
        else:
            row["source"] = "builtin"
            suffix = Path(row.get("filename", "")).suffix.lower()
            if suffix in FORMATS:
                row["format"] = FORMATS[suffix][0]
        templates.append(row)

    seen = {t["slug"] for t in templates}
    for path in custom_files(module.get("id", "")):
        slug = custom_slug(module["id"], path)
        if slug in seen:
            continue
        label, _ = _meta(path)
        templates.append({
            "slug": slug,
            "title": _title_from(path.stem),
            "description": "File supplied by your team.",
            "format": label,
            "filename": path.name,
            "source": "file",
        })
        seen.add(slug)

    return {**module, "templates": templates}


def content_disposition(filename):
    fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "template"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


def send(h, path):
    size = path.stat().st_size
    if size > MAX_BYTES:
        return False
    _, ctype = _meta(path)
    h.send_bytes(
        path.read_bytes(), ctype,
        extra={"Content-Disposition": content_disposition(path.name), "Cache-Control": "no-store"},
    )
    return True
