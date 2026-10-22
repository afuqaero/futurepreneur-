"""Runtime configuration. Every path can be overridden with an env var so the
test suite can run against a throwaway data directory."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

DATA_DIR = Path(os.environ.get("BIZREADY_DATA_DIR") or (ROOT / "data"))
DB_PATH = Path(os.environ.get("BIZREADY_DB_PATH") or (DATA_DIR / "bizready.db"))
CONFIG_PATH = Path(os.environ.get("BIZREADY_CONFIG") or (ROOT / "config.json"))
BACKUP_DIR = DATA_DIR / "backups"
CSRF_SECRET_PATH = DATA_DIR / "csrf.key"
CSRF_SECRET = os.environ.get("BIZREADY_CSRF_SECRET", "").strip()

# Drop-in template files: replace built-ins or add new learner downloads.
TEMPLATES_DIR = Path(os.environ.get("BIZREADY_TEMPLATES_DIR") or (ROOT / "content" / "templates"))

HOST = os.environ.get("BIZREADY_HOST", "127.0.0.1")
PORT = int(os.environ.get("BIZREADY_PORT", "8000"))
QUIET = os.environ.get("BIZREADY_QUIET") == "1"

SESSION_DAYS = 7
MAX_BODY = 1_000_000

# Session cookie gets the Secure flag when served over HTTPS (reverse proxy).
SECURE_COOKIES = os.environ.get("BIZREADY_SECURE_COOKIES") == "1"
TRUST_PROXY = os.environ.get("BIZREADY_TRUST_PROXY") == "1"

LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 15 * 60

# Coach request window and conversation limits.
COACH_RATE_LIMIT = int(os.environ.get("BIZREADY_COACH_RATE_LIMIT", "20"))
COACH_RATE_WINDOW = int(os.environ.get("BIZREADY_COACH_RATE_WINDOW", "600"))

# JSON module seeding can be disabled for deterministic tests.
SEED_MODULES = os.environ.get("BIZREADY_SEED_MODULES", "1") == "1"

DEFAULT_SETTINGS = {
    "quiz_pass": "80",
    "scenario_pass": "70",
    "rubric_min": "3.0",
    "rubric_floor": "2",
    "platform_name": "futurePreneur",
}
