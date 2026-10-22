from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1] / "static"
TYPES = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json; charset=utf-8"}

def handler(request):
    raw = request.args.get("path", "") if hasattr(request, "args") else ""
    rel = Path(unquote(raw)).as_posix().lstrip("/")
    target = (ROOT / rel).resolve()
    if ROOT not in target.parents or not target.is_file():
        return {"statusCode": 404, "body": "Not found"}
    return {"statusCode": 200, "headers": {"Content-Type": TYPES.get(target.suffix.lower(), "application/octet-stream"), "Cache-Control": "public, max-age=300"}, "body": target.read_text(encoding="utf-8")}
