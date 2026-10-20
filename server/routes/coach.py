"""AI coach endpoint."""

from ..ai import coach_endpoint
from ..errors import ApiError


def handle(h, conn, method, path, user):
    if path == "/api/coach" and method == "POST":
        body = h.read_json()
        mode = body.get("mode", "teach")
        messages = body.get("messages") or []
        if not isinstance(messages, list):
            raise ApiError(400, "Messages must be a list.", "invalid_input")
        h.send_json(coach_endpoint(messages, mode))
        return True
    return False
