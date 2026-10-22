"""API router. Order matters: public auth routes, then authenticated routes."""

from .. import security
from ..errors import ApiError
from . import admin, assess, auth, checkup, coach, learn, progress


def route(h, conn, method, path, query):
    if auth.handle(h, conn, method, path, query):
        return
    user = security.require_user(conn, h)
    for module in (checkup, learn, assess, progress, coach):
        if module.handle(h, conn, method, path, user):
            return
    if admin.handle(h, conn, method, path, user):
        return
    raise ApiError(404, "Not found.", "not_found")
