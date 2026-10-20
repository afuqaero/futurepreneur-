"""Error types and input cleaning shared by every route."""


class ApiError(Exception):
    def __init__(self, status, message, code=None, headers=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.headers = headers or {}


def clean_text(value, max_len=5000, field="value"):
    if not isinstance(value, str):
        raise ApiError(400, f"{field} must be text.", "invalid_input")
    value = value.strip()
    if len(value) > max_len:
        raise ApiError(400, f"{field} is too long.", "invalid_input")
    return value
