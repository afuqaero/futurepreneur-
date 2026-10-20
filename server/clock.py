"""One clock for the whole app so timestamps are consistent."""

from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or utcnow()).isoformat(timespec="seconds").replace("+00:00", "Z")
