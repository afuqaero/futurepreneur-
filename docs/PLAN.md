# futurePreneur — Build Plan (v1)

**Status:** Phases 1–7 complete (21 October 2026). Phase 7 shipped the verified progress report, trends and one-page print plan.
**Deployment:** Vercel production `https://futurepreneur-pink.vercel.app`, serverless Python API + Neon Postgres, region `iad1`.
**Date:** 19 October 2026
**Purpose:** Turn the existing working prototype into the complete futurePreneur platform described in the brief — 8 components, verified assessments, real progress tracking, admin-managed content, and a coach that never pretends.

---

## 0. Executive summary

A working prototype already exists at `C:\Users\user\bizready` and is running on `http://localhost:8000`. It already implements the full journey with **one** component built (Business Strategy & Model). The remaining work is not "build a website from zero" — it is:

1. **Harden the foundation** (structure, security, automated tests, content moved into the database).
2. **Complete all 8 components** to the same standard as the strategy module.
3. **Finish the admin area** so content, questions and passing rules are editable without code.
4. **Prove correctness** — server-side scoring, boundary tests, verified-only mastery levels, labelled demo mode.

**Recommendation: extend the existing app rather than rebuild it.** The prototype already does the hard, easy-to-get-wrong parts correctly (server-side scoring, PBKDF2 passwords, session cookies, rubric review, AI key kept server-side, honest demo mode). A rewrite in a new stack would burn the ~30% that works and delay the real bottleneck, which is **content volume and content quality**.

If you want a different stack, say so now — that decision changes Phase 1 completely.

---

## 1. Audit of what already exists

**Location:** `C:\Users\user\bizready`
**Stack:** Python 3.14 standard library (`ThreadingHTTPServer`) + SQLite + vanilla JS SPA (hash router) + hand-written CSS. No build step, no npm dependencies, runs with `python server.py`.
**Size:** ~4,900 lines (`server.py` 1,557 / `content.py` 736 / `app.js` 1,901 / `styles.css` 695).

| Area | State | Evidence |
|---|---|---|
| Auth (register/login/logout, hashed passwords, server sessions) | Working | PBKDF2-SHA256, 200k iterations, HttpOnly cookie, expiry check |
| Business profile | Working | `profiles` table + `PUT /api/profile` |
| Diagnostic check-up (8 components, 24 questions) | Working | 3 questions per component, scored server-side |
| Learning module UI (lessons, do/don't, why, mistakes, exercises) | Working for 1 of 8 | Strategy module: 4 lessons |
| Downloadable templates | Working | 4 templates (canvas, break-even sheet, planner, checklist) |
| Knowledge quiz (80% pass) | Working for 1 component | 10 questions |
| Scenario test (70% pass) | Working for 1 component | 5 questions |
| Practical assignment + rubric (≥3/4 avg, floor 2) | Working, admin-reviewed | `practical_submissions` + review endpoint |
| Progress dashboard + mastery levels | Working | `build_progress()`, `mastery_level()` |
| Action plan | Working | `plan_items` table, add/toggle |
| AI coach, 3 modes | Working, **demo mode** (no key) | Server-side proxy, config in `data/config.json` or env |
| Admin: learners, submissions review, questions, settings, content overrides | Partial | `/api/admin/*` |
| Automated tests | **None** | — |
| Deployment / backups | **None** | — |
| Modules 2–8 content | **Missing** | `available: false` on 7 components |

Current data: 3 users, 2 profiles, 2 diagnostic results, 4 attempts, 5 lesson completions, 8 plan items, 39 questions. This is test data, not a clean demo set.

**Honest gaps:**
- 7 of 8 modules are empty placeholders; their quizzes/scenarios/practicals do not exist.
- Content lives in `content.py`; the admin can only override snippets, not author a module.
- `server.py` is a single 1,557-line file — every new endpoint makes it worse.
- No CSRF protection, no login rate limiting, no audit log.
- No tests, so "pass/fail logic is correct" is currently an assertion, not a proven fact.
- No migration path from the current schema, no backup routine.

---

## 2. Target architecture

```
bizready/
  run.py                      # entry point: python run.py [--port 8000]
  server/
    config.py  clock.py  errors.py
    db.py                     # connection, migrations, backups, seeds
    security.py               # passwords, sessions, CSRF, throttling, headers
    models.py                 # settings + public user
    content_service.py        # module reads and overrides
    scoring.py                # scoring, pass rules, progress, mastery
    ai.py                     # coach proxy + labelled demo fallback
    http.py                   # handler, static files, dispatch
    routes/                   # auth, checkup, learn, assess, progress, coach, admin
    migrations/001_init.sql
  content/                    # seed JSON (Phase 2); content.py today
  static/                     # SPA: index.html, app.js, styles.css
  tests/                      # unittest suite + live-server harness
  data/bizready.db            # gitignored
  docs/PLAN.md  README.md
```

**Why Python + SQLite stays:** zero install friction on this machine, transactional integrity for scoring, and single-writer SQLite is fine for a training platform with tens of learners. If concurrent users exceed ~50, move to Postgres — the schema and service layer are written to allow it.

**What changes conceptually:** content moves out of Python and into the database, seeded from JSON. That is what makes the admin area real instead of decorative.

---

## 3. Data model (target)

Existing tables kept and extended. New tables marked **+**.

```
users(id, email, name, password_hash, role, created_at, last_login_at)
sessions(token, user_id, created_at, expires_at, ip, user_agent)
profiles(user_id PK, business_name, business_type, stage, employees,
         customers, monthly_revenue_band, main_challenge, updated_at)
components(id, name, short, description, topics_json, position, enabled)   +
modules(id, component_id, title, tagline, level, minutes, outcome,
        intro_json, status[draft|published], version, updated_at)          +
lessons(id, module_id, position, title, minutes, summary, body_json, version) +
templates(id, module_id, slug, filename, mime, body, version)              +
questions(id, module_id, kind[diagnostic|quiz|scenario], topic, difficulty,
          prompt, options_json, correct_index, explanation, lesson_ref,
          active, version)                                                 +
diagnostic_results(id, user_id, answers_json, component_scores_json,
                   overall, version, created_at)
attempts(id, user_id, kind, module_id, answers_json, score, passed,
         detail_json, duration_s, created_at)
practical_submissions(id, user_id, module_id, responses_json, status,
                      rubric_json, average, passed, reviewer_id,
                      reviewer_note, created_at, reviewed_at)
lesson_progress(user_id, module_id, lesson_id, completed_at)
plan_items(id, user_id, title, detail, due_date, done, source, created_at)
settings(key, value, updated_at)
content_revisions(id, entity, entity_id, snapshot_json, editor_id, created_at) +
audit_log(id, actor_id, action, entity, entity_id, detail_json, created_at)    +
```

**Rules**
- Every module's questions carry `lesson_ref`, so a failed topic can point at the exact lesson to revisit.
- `attempts.detail_json` stores per-question results at submit time; re-scoring reads the stored `correct_index` version, so editing a question later cannot silently rewrite history.
- Deleting content is a status change (`active=0` / `status=archived`), never a hard delete.
- All content edits write a row to `content_revisions`.

---

## 4. Scoring, pass rules and mastery (exact)

**Knowledge quiz:** `score = round(correct / total × 100)`. Pass ≥ 80 (configurable in admin).
**Scenario test:** same formula. Pass ≥ 70.
**Practical assignment:** reviewer scores 4 criteria 1–4. Pass requires **average ≥ 3.0 AND no criterion < 2**.
**Module pass:** all three criteria met. Partial completion is shown as partial, never as passed.
**Diagnostic:** self-reported, unscored against a pass mark. It produces priority ranking only.

**Mastery levels (per component) — verified evidence only**

| Level | Rule |
|---|---|
| Not assessed | No diagnostic and no attempts |
| Beginner | Diagnostic complete, no passed quiz |
| Developing | Quiz attempt exists but not passed, or quiz passed without scenario/practical |
| Structured | Module fully passed (quiz + scenario + practical) |
| Optimising | Module fully passed **and** a later quiz retake ≥ 90 **and** ≥ 1 action-plan item completed |

**Overall level** = level of the lowest *passed* module count, never an average that hides a gap. Diagnostic self-report can never lift a learner above Beginner on its own.
**Test proof:** unit tests at 49/50/69/70/79/80/89/90 and rubric boundaries (2.75/3.0/3.25), plus a test that editing a question after an attempt does not change that attempt's stored result.

---

## 5. Design system — biru, putih, kuning (Gen Z-leaning)

**Direction:** a bright, confident study-app feel — white cards, deep blue action, yellow highlighter and sticker accents, chunky outlines, big friendly type. Still calm enough for a 45-year-old warung owner on a mid-range Android phone. Teal is **removed** from the brief's palette; yellow takes over completion and highlight duty.

### 5.1 Tokens

| Token | Value | Use |
|---|---|---|
| Ink | `#0A1733` | All body text, headings, 2px outlines |
| Blue 600 | `#1B4DFF` | Primary buttons, active nav, progress fill, pass state |
| Blue 700 | `#0D33C4` | Pressed / hover on blue |
| Blue tint | `#EAF0FF` | Section washes, next-step cards, selected rows |
| Yellow 400 | `#FFD23F` | Highlighter marks, badges, stickers, milestones |
| Yellow 600 | `#F0B400` | Yellow text/border on tinted backgrounds only |
| White | `#FFFFFF` | Cards, sheets, sidebar |
| Cloud | `#F6F7FB` | App background |
| Line | `#E3E7F2` | Hairline borders, tracks |
| Muted | `#5B6480` | Secondary text, meta |
| Error | `#C6293A` | Errors and failed attempts **only**, always with an icon (5.6:1 on white) |

**Contrast rules:** `#1B4DFF` on white is 5.9:1 (safe even at 14px bold and 16px regular). Yellow is **never** text on white or a thin border for meaning — it appears as a background block, highlighter stroke, sticker or badge, always paired with ink text (ink on yellow = 12.3:1). Body copy is always Ink on White/Cloud (17.8:1 / 16.5:1). Muted is 5.5:1 on Cloud and never used for critical status.

### 5.2 Type

- **Display: Bricolage Grotesque 700/800**, tight tracking (−0.03em), sentence case, max 3 lines. Used for page titles, module titles, score numbers, empty-state headlines.
- **Body: DM Sans 400/500/700**, 16px / 1.6, max ~68 characters per line. All lesson content, forms, buttons.
- Numbers use `font-variant-numeric: tabular-nums` so scores don't jump.
- Fallback stack: `system-ui, -apple-system, Segoe UI, sans-serif` — no layout shift if Google Fonts fails.

### 5.3 The "Gen Z" layer (bounded)

- **Sticker language:** rotated 2–3° pill labels ("no jargon", "6 minutes", "module passed"), 1.5px ink border, 2px offset shadow. Max two per screen, never on top of text.
- **Offset shadows**, not blur: `3px 3px 0 #0A1733` on primary CTAs and key cards; hover lifts to `5px 5px 0`.
- **Highlighter:** yellow marker behind one key phrase in a headline (gradient underline), never whole paragraphs.
- **Shapes:** 22–26px card radius, 999px pills, 2px ink borders on hero/CTA cards, 1.5px soft borders elsewhere.
- **Numbered chips** for steps and priorities; dashed dividers between meta rows.
- **Microcopy voice:** direct, warm, lightly cheeky in empty states — *"No check-up yet. 6 minutes, no judgement."* — but plain language everywhere content teaches. No slang that dates, no emoji as status.
- **Motion:** 150–200ms ease-out, `translate(-1px,-1px)` lift, progress bars animate once on load. Confetti fires **only** on a server-confirmed module pass (a real event, never on page load).
- **Guardrails:** one loud element per screen; no gradient soup; no neon-on-neon; no custom cursor; no icon-only status; no yellow text; display type never used below 18px.

### 5.4 Layout

Light app shell: white sidebar with a 2px ink right edge on desktop, active item as a blue pill with white text and a small yellow dot; mobile keeps a white bottom tab bar (5 sections) with blue active icon + label, admin tucked into the avatar menu. Content max-width 1180px, 24px gutters (16px mobile). Hero band on Dashboard and Check-Up results uses white card + ink border + yellow circle motif.

### 5.5 Accessibility targets

Every control keyboard reachable; 3px blue focus ring with 2px white offset; label on every input (no placeholder-as-label); contrast ≥ 4.5:1 for body, ≥ 3:1 for large text and UI edges; status always icon + text + colour; tap targets ≥ 44px; `prefers-reduced-motion` kills lift/confetti; lesson content readable at 200% zoom.

### 5.6 Visual reference

`docs/style-preview.html` is the approved-direction mock: palette chips, type specimen, mastery pills, progress card, hero. It is a **style frame**, not the application — Phase 1 ports these tokens into `styles.css`, it does not copy the file.

**No decorative features.** Every visible control does something or is clearly marked "coming in a later phase" and disabled.

---

## 6. Content plan — 8 modules

Each module: 5–6 lessons × (explanation, real example, What to Do, What Not to Do, Why It Matters, Common Mistakes, exercise), 2 templates, 10-question quiz, 5 scenario questions, 1 practical assignment with a 4-criterion rubric. Written at roughly a 9th-grade reading level, second person, RM and Malaysian micro-business context.

| # | Component | Anchor examples (food / online / service) |
|---|---|---|
| 1 | Business Strategy & Model | Aina's Kitchen (food), Norli's skincare shop (online), Raj's aircon servicing (service) — **already written** |
| 2 | Marketing & Sales | Warung lunch set vs delivery apps; TikTok seller with no repeat buyers; plumber with WhatsApp leads |
| 3 | Operations & Quality | Café prep-line bottleneck; laundry turnaround; cleaning crew checklist |
| 4 | Financial Management | Daily cash reconciliation; pricing for profit; separating personal and business money |
| 5 | People & Leadership | Part-timer rostering; first hire; training a cook to standard |
| 6 | Systems & SOP | Writing a 1-page SOP; handover; checklist that staff actually use |
| 7 | Legal & Risk | SSM registration, halal/health permits, basic contracts, insurance — with a clear "not legal advice" disclaimer and local-verification note |
| 8 | Digitalisation & Growth | WhatsApp catalogue, Google Business Profile, simple POS, when *not* to buy software |

**Content standard (goes in `docs/CONTENT_STANDARD.md`):** one idea per lesson, every claim illustrated by a number or a named business, no filler, no jargon without a plain-language gloss, each exercise finishes in under 20 minutes.

**Content is the long pole.** Writing 7 modules to the standard of module 1 is ~60% of total build effort. It will be done module by module, each one reviewed before moving on.

---

## 7. Phases

Each phase ends with a **checkpoint**: I show evidence (test output, screenshots, a seeded demo walkthrough) and stop for your go-ahead. No phase starts early.

### Phase 0 — Decision gate (now)
Deliverable: this plan. You choose stack path, AI provider, deployment target.
**Exit:** written approval.

### Phase 1 — Foundation hardening ✅ (20 Oct 2026)
Split `server.py` into modules without changing behaviour; add `run.py`; add migration runner; SQLite WAL + foreign keys + backup-on-start; CSRF token on all state-changing routes; login rate limiting (5 attempts / 15 min / IP+email); security headers (CSP, X-Content-Type-Options, Referrer-Policy, frame-ancestors); structured error responses; stdlib `unittest` harness with a live-server fixture (pytest is not installed on this machine).
**Acceptance:** every existing flow still works; suite green; login/register/lesson/quiz/practical/progress smoke test passes; no endpoint lost.

**Delivered:** `server/` package (14 modules), `run.py`, `001_init.sql`, backups (5 kept), signed double-submit CSRF, throttling, CSP/security headers, typed error codes, 39 tests, `README.md`.
**Evidence:** 39/39 tests pass (14.5 s); parity check against the old server — 10 of 12 endpoints byte-identical, the 2 differences were learner counts from extra test users only; existing `data/bizready.db` migrated in place with a backup written first; browser smoke test logged in through the form and persisted an action-plan update (97% → 98%) with no JS errors.
**Bug found and fixed while testing:** the old admin settings endpoint wrote `rubric_floor` as `"2.0"`, which crashed `int()` on every later settings read (500). Now stored as an integer and parsed defensively.

### Phase 2 — Content engine + real admin authoring ✅ (20 Oct 2026)
Move modules, lessons, templates and questions into the DB, seeded from `content/*.json`; admin CRUD with validation, draft/publish, revision history, preview; passing thresholds editable with audit trail.
**Acceptance:** create a question in admin → it appears in the learner quiz; edit lesson text → learner sees it; invalid question rejected with a clear message; change quiz pass mark to 75 → a 74 fails and a 75 passes on new attempts; revisions listed.

**Delivered:** `modules`, `lessons`, `templates`, `content_revisions` and `audit_log` tables (migration `002_content.sql`); seeding from the prototype; DB-backed module reads with published-only enforcement; admin module CRUD, publish gate (≥1 lesson, 5 quiz, 3 scenario, practical), lesson editor, template editor, practical editor, preview pane, revision history, audit rows for settings and reviews.
**Evidence:** 47/47 tests pass, including draft-hidden-until-published, publish gate, lesson edit reaching the learner, revision snapshot, template download/delete, settings audit, and module-slug/lesson validation. Live server verified: module list, module save (v2), revision list, short-title rejection. UI verified in headless Chrome over CDP: 5 admin tabs, module list, lesson switching, preview pane, save toast, zero JS errors; 390px layout switches to one column with no horizontal scroll.

### Phase 3 — Business Check-Up v2 ✅ (20 Oct 2026)
Expanded profile (type, stage, staff, customers, revenue band, main challenge); diagnostic intro with honest framing ("this is a self-assessment, not a test"); results page: per-component bars, top 3 strengths, top 3 gaps, priority order, recommended module + lesson links; retake with history comparison.
**Acceptance:** complete → results render correct strengths/gaps on seeded data; retake stores a second result; old result remains in history; recommendations link to the right module.

**Delivered:** `customer_type` profile field (`003_checkup.sql`); GET `/api/checkup` now returns priorities, strengths, previous, change and history on reload; strengths capped at 3 and never overlap gaps; gaps are areas below 85% (max 3), so a 100% area can no longer appear as a "priority"; history table with per-retake deltas; explicit "self-assessment, not a test" callout.
**Evidence:** 51/51 tests pass, including customer-type round-trip, history ordering (83/67/50), +16 delta, old results retained, and priorities ordered weakest-first. Headless Chrome: 2 real gaps (0%, 67%), two history rows, +16 chip, customer type shown and editable, zero JS errors, 390px with no horizontal scroll.
**Bug found and fixed:** the first cut listed the three lowest scores even when many were 100%, producing a "priority" card at 100% while also calling it a strength. Gap ranking now uses a threshold and excludes overlaps.

### Phase 4 — Learn & Improve, modules 2–8 ✅ (content complete, 7 of 7)
Same structure as strategy for all 8. Per module: 4 lessons, 2 templates, mini quiz, lesson completion, progress within module, "next lesson" flow; lessons render as story cards with illustration, case file, do/don't and a mission.
**Delivered:** Marketing & Sales, Operations & Quality, Financial Management, People & Leadership, Systems & SOP, Legal & Risk, Digitalisation & Growth — 4 lessons and 2 templates each, plus 10 quiz + 5 scenario questions and a practical rubric per module; JSON seeding pipeline; per-module assessment scoping.
**Next:** Phase 5 completed the assessment screens for modules 2–8; those “Arrives in Phase 5” labels are gone.
**Acceptance:** all 8 open and render; lesson completion persists across logout; templates download with correct filename/type; no placeholder lorem anywhere.

### Phase 5 — Assessment centre ✅ (21 October 2026)
Question banks (8 × 10 quiz, 8 × 5 scenario), 8 practical assignments with 4-criterion rubrics, server-side scoring, immediate per-question feedback with explanations, pass/retry, attempt history, remediation list mapping missed topics → lessons, submission → admin review queue.
**Delivered:** module-scoped routes (`/api/module/<id>/assessment/<kind>/...`, `/api/module/<id>/practical`), strict isolation from Strategy's legacy endpoints, per-module attempt history, per-submission criteria in the admin queue, and cross-module progress aggregation. Every wrong answer carries a lesson link from the explicit 120-question map (`server/remediation.py`, keyword fallback for admin-authored questions). Module pass stays assessment-only; lessons remain optional learning.
**Evidence:** 59/59 tests pass, including module isolation, hidden inactive questions, wrong-rubric rejection, exact remediation lessons, unreviewed practical staying unpassed and marketing passing without passing Strategy. Headless Chrome: 8 test cards, module-scoped runner, 0% result listing 4 lessons, no horizontal scroll at 390px, zero JS exceptions.
**Acceptance:** boundary tests pass; a failed attempt lists the exact lessons to revisit; retake does not overwrite history; practical cannot pass without reviewer scoring; unpublished questions never appear.

### Phase 6 — AI Business Coach ✅ (21 October 2026)
Three modes with distinct system prompts; provider config in admin (OpenAI-compatible base URL + model + key), key stored server-side and never returned by any endpoint; per-user rate limit; conversation persistence and clear-history; learner context injected (business type, weakest components); explicit demo mode when no key — labelled on every message, deterministic, sourced from the module content; timeout/error states; prompt-injection guard.
**Delivered:** migration `007_coach.sql` adds `coach_sessions`, `coach_messages` and `coach_rate_events`. `GET/POST /api/coach`, `GET /api/coach/sessions`, `GET/DELETE /api/coach/sessions/<id>` and `DELETE /api/coach/sessions` persist and clear conversations. Admin `GET/PUT /api/admin/ai` configures base URL/model/key; only `key_set` and `key_source` are returned. 20 messages per 10 minutes per learner (configurable), with `Retry-After`. Live prompts carry the safety guard plus a factual learner context block (business, sector, weakest check-up areas, verified modules). UI auto-reopens the latest conversation, lists recent chats, starts a new chat without deleting history, and offers Clear all.
**Evidence:** 65/65 tests pass, including persistence, cross-user 404, 429 + `Retry-After`, masked key in bootstrap/admin responses, a mock OpenAI-compatible provider receiving `Bearer <key>` and the learner context, and a learner blocked from admin AI settings. Headless Chrome: chat survives reload, new chat preserves history, reopen restores messages, clear-all empties it, no key in the DOM, 390px no horizontal scroll, zero JS exceptions.
**Acceptance:** no key → banner “Demo mode — not a live AI” and no fabricated personalisation; with key → live replies; no key in client files, logs or API responses; rate limit returns 429 with a clear message.

### Phase 7 — My Business Progress ✅ (21 October 2026)
Verified-only mastery, per-component score cards, modules passed / needs improvement, assessment timeline, score trends, recommended next steps engine, editable action plan with due dates and completion, print/PDF export of the plan.
**Shipped early (on request):** five owner-facing aspect cards — Marketing, Finance, Operations, Management (Strategy + Systems), People & Growth (People + Digitalisation) — each showing a labelled self-assessed baseline and a verified badge only where a module is fully passed. The full eight-component table stays underneath, including Legal & Risk.
**Delivered:** a `Module results` table for all eight modules (lessons, quiz, scenario, practical, completion, and an honest status: Passed / Awaiting review / Needs improvement / In progress / Not started); `trend` in `/api/progress` holds the last 12 quiz/scenario attempts chronologically; an SVG score chart with separate quiz-80 and scenario-70 reference lines and green/red pass dots; best/latest attempt stats; a `Print / save PDF` button that prints a dedicated one-page plan with business profile, mastery, 1/8 module table, next steps and the action plan.
**Evidence:** `66/66` tests pass, including chronological trend order, attempt scores and pass flags. Headless Chrome: 8 module rows, 2 trend points for the demo learner, print CSS shows only the plan, `Page.printToPDF` produces **1 page** at A4, mobile 390px has no horizontal scroll, and zero JS exceptions.
**Acceptance:** mastery cannot rise without a verified pass (tested); a learner with only a diagnostic shows Beginner; progress percentages match attempt records; export produces a readable one-page plan.

### Phase 8 — Admin area (≈ 3 h)
Learner list + detail (progress, attempts, submissions), rubric review queue with notes, content health (modules missing questions, unpublished items), pass-rate summary, settings with confirmation + audit, content revision browser, CSV export.
**Acceptance:** admin can review a submission end-to-end; role checks block learners on every admin route (tested); settings change is audited; CSV exports match DB counts.

### Phase 9 — QA, accessibility, responsive (≈ 3–4 h)
Playwright (or scripted browser) smoke: register → checkup → module → quiz → scenario → practical → progress → admin edit. Mobile at 360×640, tablet 768, desktop 1280/1440. Keyboard-only pass. Empty/loading/error states. Contrast audit. Performance budget (< 200 KB JS, no layout shift on load). Clean seeded demo reset.
**Acceptance:** smoke test green from a fresh DB; no horizontal scroll at 360px; zero unlabelled inputs; yellow-on-white contrast audit passes (yellow never load-bearing text); no leftover teal/green from the old palette; screenshots of all 5 sections desktop + mobile.

### Phase 10 — Packaging & handoff (≈ 2 h)
`README.md`, `docs/RUN.md` (start, reset, backup, configure AI), `.env.example`, seed/reset commands, demo accounts, screenshot set, deployment notes (Docker optional; SQLite volume warning), known-limitations list.
**Acceptance:** a fresh clone runs with two commands; demo data loads; limitations documented honestly.

**Total: ≈ 40–50 h of build, with content authoring dominating.** Checkpoints after every phase; Phases 4 and 5 have per-module checkpoints.

---

## 8. Risks and how the plan handles them

| Risk | Handling |
|---|---|
| Content quality collapses into generic filler | Fixed content standard, one module reviewed before the next, real numbers and named businesses required |
| Scoring/pass logic silently wrong | Pure functions + boundary tests in Phase 1/5, server-authoritative scoring, stored per-attempt detail |
| Admin area becomes decorative | Phase 2 makes content DB-backed first, so admin edits are the real source of truth |
| AI coach fabricates confidence | Demo mode labelled on every message; no fake personalisation; live mode only when a key exists |
| Legal module gives unsafe advice | "General education, not legal advice" disclaimer; Malaysian-specific items flagged for local verification; no definitive compliance claims |
| SQLite corruption / data loss | WAL, foreign keys, backup-on-start, documented restore, CSV export |
| Self-hosted server exposed to internet | Bind localhost by default; deploy notes require HTTPS reverse proxy, secure cookies, rate limits |
| Scope creep (certificates, payments, multi-tenant) | Explicitly out of scope in v1 (below) |

---

## 9. Explicitly out of scope for v1

- Certificates of completion (the brief forbids fabricated certificates; a real one needs identity + verified completion + issuance records — a later, separate feature).
- Payments, subscriptions, multi-organisation accounts.
- Email verification, password reset by email, SSO (needs an email provider).
- Native mobile apps.
- Video content.
- AI-generated assessment grading (practical work is human-reviewed).
- Bahasa Melayu interface (v1 is English with Malaysian context; copy can be localised later).

---

## 10. Demo data to ship

- `aina@futurepreneur.app / Demo1234!` — food business, diagnostic done, strategy module passed, plan in progress.
- `raj@futurepreneur.app / Demo1234!` — service business, diagnostic done, mid-module, one failed quiz.
- `admin@futurepreneur.app / Admin1234!` — admin with a pending practical submission to review.
- Question banks for all 8 components, 4 templates per completed module, one unpublished draft module to demonstrate the draft state.

---

## 11. Decisions I need before Phase 1

1. **Stack path** — (A) extend this Python/SQLite app *[recommended]*, (B) rebuild on Next.js + Postgres, (C) extend now, migrate later.
2. **AI coach** — do you have an OpenAI-compatible API key/provider to configure, or should v1 ship demo-mode-first and stay clearly labelled until a key is added?
3. **Deployment** — local demo only for now, or does it need to be reachable by real learners (which adds HTTPS, hosting, backups and a security pass)?
4. **Language** — English-only v1, or English + Bahasa Melayu from the start? (Affects every content phase, so it must be decided before Phase 4.)
