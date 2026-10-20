# BizReady

A practical business-readiness platform for micro and small business owners: diagnostic check-up, eight learning modules, a coach, verified assessments, and an honest progress record.

Website (responsive web app), Python standard library + SQLite + vanilla JS. No npm install, no build step.

## Run

```bash
python run.py                 # http://localhost:8000
python run.py --port 8080     # different port
python run.py --host 0.0.0.0  # expose on the LAN (read the security note first)
python run.py --reset         # back up and rebuild the demo database
```

Demo accounts:

| Role | Email | Password |
|---|---|---|
| Learner | `aina@demo.bizready.app` | `Demo1234!` |
| Admin | `admin@bizready.app` | `Admin1234!` |

The database lives at `data/bizready.db`. A timestamped backup is written to `data/backups/` on every start (last 5 kept).

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

51 tests: scoring boundaries (79/80/81, 69/70), pass rules, mastery levels, auth, CSRF, login throttling, role checks, full module journey, rubric floor, settings changes, headers, static traversal, draft/publish gates, admin content authoring, revisions, audit, check-up history and deltas.

## Configuration

Environment variables (server-side only; nothing is exposed to the browser):

| Variable | Purpose |
|---|---|
| `BIZREADY_AI_KEY` | Enables live AI coaching via an OpenAI-compatible API |
| `BIZREADY_AI_BASE_URL` | Default `https://api.openai.com/v1` |
| `BIZREADY_AI_MODEL` | Default `gpt-4o-mini` |
| `BIZREADY_DATA_DIR` | Override the data directory |
| `BIZREADY_SECURE_COOKIES=1` | Add `Secure` to cookies and HSTS (use behind HTTPS) |
| `BIZREADY_TRUST_PROXY=1` | Trust `X-Forwarded-For` for client IP (only behind a proxy) |
| `BIZREADY_HOST` / `BIZREADY_PORT` | Bind defaults |

Without a key the coach runs in **demo mode**, labelled on every reply. It never pretends to be live AI.

Optional `config.json` at the project root:

```json
{ "ai": { "api_key": "...", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini" } }
```

Keep `config.json` out of version control (already in `.gitignore`).

## Structure

```
run.py                     entry point
server/
  config.py  clock.py  errors.py
  db.py                    connection, migrations, backups, seeds
  security.py              passwords, sessions, CSRF, throttling, headers
  models.py                settings, public user
  content_service.py       module reads + overrides
  scoring.py               scoring, pass rules, progress, mastery
  ai.py                    coach proxy + labelled demo fallback
  http.py                  Handler, static files, dispatch
  routes/                  auth, checkup, learn, assess, progress, coach, admin
  migrations/001_init.sql
static/                    index.html, app.js, styles.css
tests/                     unittest suite + live-server harness
content.py                 legacy seed for the Strategy module
content/seed/*.json        authoring seed for new modules (Marketing live)
data/                      SQLite database + backups (gitignored)
docs/PLAN.md               phase plan and current status
```

## Security baseline (Phase 1)

- PBKDF2-SHA256 passwords (200k iterations), server-side sessions in SQLite, HttpOnly + SameSite=Lax cookies.
- CSRF: signed double-submit cookie (`br_csrf` + `X-CSRF-Token`) required on every POST/PUT/PATCH/DELETE.
- Login throttling: 5 failures per 15 minutes per IP+email, `429` with `Retry-After`.
- CSP (no inline scripts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, Permissions-Policy.
- Server-side scoring only; clients never see the answer key before submitting.
- Static path traversal blocked; request bodies capped at 1 MB.
- Admin routes re-check role on every request.

**Known limits:** the server binds to `127.0.0.1` by default and uses HTTP. Do not expose it to the internet without a TLS reverse proxy, `BIZREADY_SECURE_COOKIES=1`, and `BIZREADY_TRUST_PROXY=1`. Login throttling is per-process (fine for one server, resets on restart). SQLite is single-writer; suitable for tens of concurrent learners, not hundreds.

## Status

- **Phase 1 — complete:** modular server, migrations, backups, CSRF, throttling, security headers, 39-test suite, behaviour parity with the prototype.
- **Phase 2 — complete:** modules, lessons, templates and practicals live in SQLite, with admin authoring, draft/publish, preview, revisions and an audit trail (47 tests total).
- **Phase 3 — complete:** Check-Up v2 — customer type, clearer results, gap threshold, retake history and deltas (51 tests total).
- **Phase 4 — in progress:** Marketing & Sales module live (4 lessons, 2 templates, 10 quiz + 5 scenario questions, practical). Six modules remain: Operations, Finance, People, Systems, Legal, Digitalisation.
- Phases 5–10: see `docs/PLAN.md`.
