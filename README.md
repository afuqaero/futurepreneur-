# futurePreneur

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
| Learner | `aina@futurepreneur.app` | `Demo1234!` |
| Admin | `admin@futurepreneur.app` | `Admin1234!` |

The database lives at `data/bizready.db`. A timestamped backup is written to `data/backups/` on every start (last 5 kept).

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

66 tests: scoring boundaries (79/80/81, 69/70), pass rules, mastery levels, auth, CSRF, login throttling, role checks, full module journey, module-scoped question isolation, per-module remediation, module-aware rubric review, rubric floor, settings changes, headers, static traversal, draft/publish gates, admin content authoring, revisions, audit, check-up history and deltas, coach persistence/privacy/rate limiting, live-provider context injection, key masking, chronological progress trends, and drop-in template file overrides.

## Design system

Deep blue `#0F2A66`, yellow `#FFC93C`, ink `#0A1733` on cloud `#F6F7FB`. Display type is Bricolage Grotesque, body is DM Sans. The Gen-Z layer lives in `static/theme.css` (loaded after `styles.css`) with illustrations in `static/img/`. Lessons use story cards: illustrated “why it matters”, a big-idea card, case file, colour-coded do/don’t, folded mistakes and a mission, instead of a wall of text.

## Your own template files

You do not need to edit code to replace a template. Drop a file into `content/templates/` and it is served immediately.

```
content/templates/
  finance-13-week-cashflow.xlsx     # replaces the built-in template with that slug
  finance/Stock-count.csv           # adds an extra download to the Finance module
  operations/Opening-checklist.pdf  # adds an extra download to Operations
```

- **Replace:** the filename must match the template slug shown in Admin → Content → Templates. Supported: `pdf, docx, xlsx, pptx, csv, md, txt, zip, png, jpg`.
- **Add:** any supported file inside `content/templates/<module-id>/` appears as an extra learner download, titled from the filename.
- Only published modules serve files; max 10 MB per file; one file per slug for replacements.
- The learner row shows “Your file” so you can tell a real file from a built-in one.

See `content/templates/README.md` for the full rules.

## Configuration

Environment variables (server-side only; nothing is exposed to the browser):

| Variable | Purpose |
|---|---|
| `BIZREADY_AI_KEY` | Enables live AI coaching via an OpenAI-compatible API (overrides the admin-saved key) |
| `BIZREADY_AI_BASE_URL` | Default `https://api.openai.com/v1` |
| `BIZREADY_AI_MODEL` | Default `gpt-4o-mini` |
| `BIZREADY_COACH_RATE_LIMIT` | Coach requests per learner per window (default 20) |
| `BIZREADY_COACH_RATE_WINDOW` | Window in seconds (default 600) |
| `BIZREADY_DATA_DIR` | Override the data directory |
| `BIZREADY_SECURE_COOKIES=1` | Add `Secure` to cookies and HSTS (use behind HTTPS) |
| `BIZREADY_TRUST_PROXY=1` | Trust `X-Forwarded-For` for client IP (only behind a proxy) |
| `BIZREADY_HOST` / `BIZREADY_PORT` | Bind defaults |

Without a key the coach runs in **demo mode**, labelled on every reply. It never pretends to be live AI.

## Vercel + Supabase deployment

The repository now includes the JavaScript/Vercel migration foundation in `api/`, `supabase/schema.sql`,
`vercel.json`, and `package.json`. The migration is intentionally additive while the remaining API routes are
ported; the original Python server remains available for local development during the transition.

1. Create a Supabase project and run `supabase/schema.sql` in the SQL Editor.
2. In Vercel, import this GitHub repository and set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and
   `SUPABASE_SERVICE_ROLE_KEY` under Project Settings → Environment Variables.
3. Add `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`, and
   `DEEPSEEK_MODEL=deepseek-chat` for the live coach. Without the key, the coach stays in labelled demo mode.
4. Deploy. The serverless health check is available at `/api/health`.

Never expose `SUPABASE_SERVICE_ROLE_KEY` to browser code. It is used only by the Vercel function.

Admins can set the provider in **Admin → Standards → AI coach provider**. The key is stored in the server-side SQLite settings table, never returned by any endpoint, and never written to the page. `BIZREADY_AI_KEY` still overrides a saved key. Conversations and their messages are stored in SQLite; learners can reopen or clear them. The coach is limited to 20 messages per 10 minutes per learner by default.

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
  remediation.py           missed-question → lesson mapping
  coach_store.py           conversations, messages, rate window
  ai.py                    coach proxy + labelled demo fallback
  http.py                  Handler, static files, dispatch
  routes/                  auth, checkup, learn, assess, progress, coach, admin
  migrations/001_init.sql
static/                    index.html, app.js, styles.css
tests/                     unittest suite + live-server harness
content.py                 legacy seed for the Strategy module
content/seed/*.json        authoring seed for all eight modules
content/templates/         drop-in files: replace a template or add a download
data/                      SQLite database + backups (gitignored)
docs/PLAN.md               phase plan and current status
```

## Security baseline (Phase 1)

- PBKDF2-SHA256 passwords (200k iterations), server-side sessions in SQLite, HttpOnly + SameSite=Lax cookies.
- CSRF: signed double-submit cookie (`br_csrf` + `X-CSRF-Token`) required on every POST/PUT/PATCH/DELETE.
- Login throttling: 5 failures per 15 minutes per IP+email, `429` with `Retry-After`.
- CSP (no inline scripts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, Permissions-Policy.
- Server-side scoring only; clients never see the answer key before submitting.
- AI provider keys live in the server-side SQLite settings table or environment, are never returned by an endpoint, and are never written to the page. Coach conversations are per-user and capped per request window.
- Static path traversal blocked; request bodies capped at 1 MB.
- Admin routes re-check role on every request.

**Known limits:** the server binds to `127.0.0.1` by default and uses HTTP. Do not expose it to the internet without a TLS reverse proxy, `BIZREADY_SECURE_COOKIES=1`, and `BIZREADY_TRUST_PROXY=1`. Login throttling is per-process (fine for one server, resets on restart). SQLite is single-writer; suitable for tens of concurrent learners, not hundreds.

## Status

- **Phase 1 — complete:** modular server, migrations, backups, CSRF, throttling, security headers, 39-test suite, behaviour parity with the prototype.
- **Phase 2 — complete:** modules, lessons, templates and practicals live in SQLite, with admin authoring, draft/publish, preview, revisions and an audit trail (47 tests total).
- **Phase 3 — complete:** Check-Up v2 — customer type, clearer results, gap threshold, retake history and deltas (51 tests total).
- **Phase 4 — content complete:** all 8 modules live (4 lessons + 2 templates + 10 quiz + 5 scenario questions each).
- **Phase 5 — complete:** all 8 modules are assessable. Question banks are module-scoped and server-scored, every result includes per-question feedback plus the exact lessons to revisit, practical submissions go to a module-aware admin review queue, and progress/mastery aggregate across the full module set.
- **Phase 6 — complete:** persisted coach conversations with reopen/clear, per-user rate limiting with `Retry-After`, admin-managed OpenAI-compatible provider settings, key masking, learner context injection and a prompt-injection guard.
- **Phase 7 — complete:** module-by-module results with honest statuses, a 12-attempt score trend with quiz/scenario reference lines, and a one-page print/PDF business improvement plan (66 tests total).
- Phases 8–10: see `docs/PLAN.md`.
