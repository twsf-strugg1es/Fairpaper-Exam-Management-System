# 2. Technical Requirements Document (TRD): Fairpaper

Purpose: make technical choices explicit so the build does not rely on guesses.
Status: living document · Last updated 2026-10-12 · Describes the system **as built**; *(planned)* items are scheduled in the [Implementation Plan](06-IMPLEMENTATION-PLAN.md).

## Platforms

- **Web only, desktop first**: version one is a desktop web app (1024 px and wider). Narrower, only the public landing page, login and signup work; other routes show a "use a computer" screen.
- Supported: the last 2 versions of Chrome, Edge, Firefox and Safari on Windows, macOS and Linux; old low-spec PCs are a first-class target. The landing page also supports mobile Safari and Android Chrome.
- Clipboard clearing uses the async Clipboard API (`navigator.clipboard.writeText`), which needs a focused page; it's best effort, and paste blocking doesn't depend on it.
- *(planned)* An installable PWA. There are no native apps.

## Frontend and hosting

| Item | Choice |
|---|---|
| Framework | React 19, React Router 7, Create React App (`react-scripts` 5) |
| Styling | Tailwind CSS 3 with CSS-variable theme tokens; light and dark themes |
| HTTP | axios instance in `src/api.js` (adds the `Authorization` and `X-Organization-Id` headers) |
| Icons / fonts | `react-icons/lu` (Lucide); self-hosted `@fontsource` IBM Plex Sans/Mono and Hind Siliguri |
| State | React Context (`AuthContext`, `ThemeContext`) plus local component state; no global store |
| Build output | Static files (`npm run build`), served by nginx or a CDN *(planned)* |
| Config | `REACT_APP_API_URL` at build time (default `http://localhost:8000`); the web image's `API_ORIGIN` (defaults to it) goes into the CSP |

## Backend and database

| Item | Choice |
|---|---|
| API | FastAPI (Python 3.10+; the code uses `X \| None` syntax), uvicorn, Pydantic v2; OpenAPI at `/docs` |
| ORM | SQLAlchemy (synchronous sessions), `psycopg[binary]` |
| Database | PostgreSQL 12+; UUID primary keys; JSON columns for options, answers and event details |
| Migrations | Alembic, `backend/migrations/versions/000N_*.py`; the app never calls `create_all` |
| File storage | Today: image answers inline in the database as `data:` URLs. *(planned)* S3-compatible object storage (Cloudflare R2 / AWS S3 / MinIO) with signed URLs |
| Background jobs | None today. *(planned)* A small scheduler/worker for notifications and closing abandoned attempts |
| Region | One region at launch (Singapore or Mumbai: low latency to South Asia, acceptable globally). *(planned)* An EU region for customers that require EU data residency, as a separate deployment per region rather than one global database |

### Internationalization (global readiness)

| Concern | Requirement |
|---|---|
| UI text | **Done (1.8):** every visible string goes through `t('English text')` / `tn(count, one, other)` from `src/i18n/` (`useI18n()`). English text is the key, so a missing translation falls back to English. Translations live in the catalogs in `src/i18n/index.js` (Bengali is task 4.13). `npm run i18n:extract` lists every string in `src/i18n/strings.json` for translators; CI fails if it's out of date. `?lang=en-XA` renders a pseudo-language to find strings that skipped `t()` |
| API messages | Error `detail` and `message` strings stay English and are translated on the client: `errorMessage()` passes them through `t()`, and the extractor collects them from `backend/app`. Messages with variable parts (f-strings) are not translatable yet; give them a fixed sentence when they matter |
| Dates, numbers, currency | Formatted with `Intl` APIs and the user's locale; stored as UTC timestamps / integer minor units + ISO 4217 currency code |
| Settings | **Done (1.9):** organization `default_language`, `timezone` (IANA), `currency`, `country`; user `language`. `/me` memberships carry the organization's `timezone` and `default_language`. The frontend calls `setTimeZone()` (in `App.js`) so every formatter in `src/utils.js` uses the organization's timezone; `formatExamTime()` adds a short zone label when the organization's offset differs from the viewer's, and the exam form reads and writes `datetime-local` values in that zone (`toZonedInput` / `fromZonedInput`). Language order: `?lang=` > account > organization > browser; a hidden test language (`en-XA`, `en-XB`) stays until it's changed |
| Scripts | Font stack covers Latin and Bengali today; add Noto fallbacks for other scripts. Layout works right-to-left (**done, 1.10**): logical Tailwind utilities only, `<html dir>` set from the language catalog (`dir` field in `src/i18n/index.js`), test with `?lang=en-XB` |
| Phone numbers | Stored in E.164 format; validated per country |
| Local exam conventions | Negative marking, merit lists, grading scales are per-exam/per-organization settings, never global defaults |

Backend environment (`backend/.env`):

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql://user:pass@host:5432/db` |
| `SECRET_KEY` | yes | JWT signing key; the app refuses to start without it |
| `CORS_ORIGINS` | no | Comma-separated allowed frontend origins (default: localhost:3000, localhost:5173) |
| `LOG_LEVEL` | no | `DEBUG` / `INFO` (default) / `WARNING` / `ERROR`. Logs are JSON lines on stdout |
| `BACKGROUND_JOBS` | no | `on` (default) / `off`. Runs the abandoned-attempt finalizer inside the API; turn off when cron runs `python -m app.jobs finalize-attempts` instead |
| `RATE_LIMITS` | no | `on` (default) / `off`. Off only for load tests |
| `APP_URL` | prod: yes | The frontend's public URL, used in emailed links (default `http://localhost:3000`) |
| `EMAIL_BACKEND` | prod: yes | `console` (default: writes `.eml` files to `EMAIL_OUTBOX_DIR`, sends nothing), `smtp`, `memory` (tests) |
| `EMAIL_FROM` | with smtp | Sender, e.g. `Fairpaper <no-reply@fairpaper.app>` (owner decision) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | with smtp | Any provider's SMTP relay. Port 587 uses STARTTLS, 465 uses TLS |

## Authentication and roles

- **Sign-in:** email + password via `POST /token` (OAuth2 password form; the `username` field holds the email).
- **Tokens:** JWT HS256, 60-minute expiry, `sub` = user ID (tokens with an email subject are still accepted for one release). The frontend refreshes before expiry with `POST /token/refresh`, so a long exam never logs anyone out. Tokens are stored in `localStorage`.
- **Passwords:** `pbkdf2_sha256` (passlib). Older bcrypt hashes still verify.
- **Roles are per organization** (`Membership.role`): `owner` > `admin` > `examiner` > `candidate`.
  - Staff = owner, admin, examiner: questions, exams, grading, results.
  - Managers = owner, admin: members, groups, join codes, organization settings.
  - Only owners can grant, change or remove the owner role; an organization always keeps at least one owner.
- **Organization context:** every organization-scoped request sends `X-Organization-Id`. `permissions.get_current_membership` resolves it to the caller's membership or returns 403. Route guards: `require_staff`, `require_manager`, `require_candidate`.
- **Rate limits (2.6):** `app/rate_limit.py`, in-process counters (one API instance; several instances need Redis or Postgres). `POST /token`: 100/min per IP, and 10 failed sign-ins per account per 15 min (counted for unknown emails too; a success clears it). `/signup`: 60 per 10 min per IP; `/signup/organization`: 10/hour per IP; `/organizations/join`: 20 per 10 min per user; `/waitlist` and `/waitlist/unsubscribe`: 20 per 10 min per IP; staff invite resends: 3 per person per hour. Over the limit → 429 with `Retry-After`. Per-IP limits are generous because a class signs in together from one school network. The client IP is `request.client.host`; uvicorn `--proxy-headers` trusts `X-Forwarded-For` only from `FORWARDED_ALLOW_IPS` (default 127.0.0.1), so set that to the load balancer's address in production.
- **Password reset (2.4):** `routers/password_reset.py`. Tokens are 32 random bytes (URL-safe), stored only as SHA-256, valid 30 minutes, single use; a new request or a successful reset invalidates every open link. Known gap: tokens already issued (60 min JWTs) stay valid after a reset until they expire.
- **Email verification (2.5, soft):** `routers/email_verification.py`. Both signups email a link; the token is a signed JWT with `purpose: verify-email` and the email, so changing the address kills old links and nothing is stored. `security.get_current_user` refuses any token with a `purpose`, so an emailed link can never act as a session. Signed-in pages show `VerifyEmailBanner` (dismissible per visit) until confirmed.
- **Invites (3.6, 3.7):** `app/invites.py`. Adding someone without an account (bulk student import, or Organization → Staff) creates the account with an unusable random password and a 7-day single-use `invite` token in `password_reset_tokens`; the link `/invite/<token>` is confirmed by `POST /password-reset/confirm`. People who already have an account are added and emailed. An invite counts as pending while its token is unused; **Resend invite** replaces every open link (3 per person per hour).
- *(planned)* Google sign-in.

## External services and APIs

| Service | Purpose | Status | Limits / notes | Credentials owner |
|---|---|---|---|---|
| Email (SMTP, or Resend/SES) | Reset, verification, invites, notifications | planned | Provider free tiers ≈ 3k/month | Product owner |
| SMS: BD gateway (SSL Wireless / BulkSMSBD / Alpha SMS) for Bangladesh; Twilio (or similar) elsewhere | Exam reminders, results | planned | Per-SMS cost; sender ID rules differ by country; route by the phone number's country | Product owner |
| Object storage (R2/S3) | Image answers, webcam snapshots, ID photos | planned | Signed URLs, private bucket | Product owner |
| Sentry | Error tracking (API + web) | planned | Free tier | Product owner |
| Payments: SSLCommerz / bKash (Bangladesh); Stripe or Paddle (global; Paddle also handles sales tax/VAT as merchant of record) | Subscriptions | planned (P3) | Merchant accounts required; payment provider chosen per organization's country | Business owner |

No external service is called today. All credentials will come from environment variables and are never committed.

## Architecture

```
Browser (React SPA)
  │  HTTPS JSON · Authorization: Bearer <jwt> · X-Organization-Id: <uuid>
  ▼
FastAPI app (backend/app)
  main.py ── routers/ (auth, organizations, admin, student, profile)
                │  depend on permissions.py (membership + role) and security.py (JWT user)
                ▼
             crud.py (business logic: grading, shuffling, deadlines, integrity)
             results_export.py (Excel workbook and result-card data, task 4.5)
                ▼
             models.py (SQLAlchemy) ──► PostgreSQL (schema via Alembic)
```

**Main data flows**
1. **Login:** `/token` → JWT → `/me` returns the user and their memberships → the frontend stores the selected `organizationId` → every later call carries both headers.
2. **Exam start:** `POST /student/exams/{id}/start` checks visibility (organization + group), publish state, window, and that the exam isn't already submitted, then creates or reuses the attempt and returns the questions (shuffled per attempt, with no answer keys), saved answers and the deadline.
2b. **Marks per exam (4.2):** `exam_questions.marks` overrides a question's `max_score` for one exam; `crud.exam_marks(exam)` is the only place that resolves it, and `POST /admin/exams/` now returns the same payload as `GET /admin/exams/{id}` (with `total_marks` and each question's `bank_max_score`).
3. **Answering:** `POST /attempts/{id}/save-answer` upserts one answer. It is rejected after `deadline + 30 s` (`ANSWER_GRACE_SECONDS`), and, with timed sections or per-question timing, for a question whose section or question hasn't opened or has closed (a student who moved on can't change it; an answer sent as the time ran out has 5 s, `TIMEOUT_GRACE_SECONDS`). **Offline-tolerant (3.8):** the exam page queues every answer in IndexedDB (`frontend/src/answerQueue.js`; memory if IndexedDB is blocked), newest value per question, and sends them one at a time with backoff (1 s → 30 s), immediately on the browser's `online` event, and on reopening the exam (answers still waiting are shown and sent). Each save carries `client_seq` (strictly increasing, `max(last + 1, Date.now())`, so it also increases across reloads); the server applies it with one conditional UPDATE and answers `stale` when it already holds a newer one, so a delayed retry can't overwrite a newer answer. Submit first drains the queue and refuses, with a message, while answers are still waiting. Limits: answers still waiting when the deadline + grace passes are rejected by the server (the attempt is finalized with what it has), and the local copy lives in that browser only.
4. **Integrity:** the exam page's `useExamIntegrity` hook sends events to `POST /attempts/{id}/events` (`fetch` with `keepalive`). The server counts violations and submits automatically at `max_violations`. When the page loses focus the hook sets `blocked`: the exam page blurs and renders placeholder bars instead of the question (an AI sidebar or extension can read a page's text even when it's blurred), and `blocked` stays on after focus returns until the candidate clicks (`returnToExam`), which is also when the clipboard is emptied again and fullscreen re-entered. With copy/paste protection on, `selectstart` and Ctrl/Cmd+A are blocked outside answer boxes and the page is `user-select: none`.
5. **Submit:** `POST /attempts/{id}/submit` auto-grades choice questions and records the submit reason (`student`, or `time_up` if within 5 s of the deadline). Written and image answers wait for manual grading through `/admin/evaluations/...`.

**Deadline rule:** `deadline = min(attempt.start_time + duration, exam.end_time)`. The server decides; the client timer only displays it.

## Security and privacy

| Concern | Control |
|---|---|
| Tenant isolation | Every tenant query filters by `membership.organization_id`; cross-organization access tests in `tests/test_organizations.py`. **Every new endpoint needs one.** |
| Answer-key leakage | Candidate payloads are built by `crud.questions_for_attempt` and never include `correct_answers`. Results include correct answers only after the exam window closes. |
| Integrity data | Server-side counting. The client clock (`occurred_at`) is informational only; ordering uses the server's `recorded_at`. Event payloads are validated (known types only, ≤ 50 per request, details ≤ 1000 chars). |
| Passwords | Hashed (pbkdf2_sha256); change-password requires the old password. |
| Transport | HTTPS in production *(planned, at deploy)*; CORS restricted by `CORS_ORIGINS`. |
| Sensitive data held | Name, email, optional date of birth and gender, answers, integrity events, uploaded images. *(planned)* webcam/ID images need explicit consent, a retention limit (e.g. 90 days after the exam closes) and deletion by the organization. |
| Privacy law (global) | Before selling outside Bangladesh: GDPR (EU/UK) — lawful basis, data processing agreement for organizations, data export and deletion, subprocessor list, cookie consent, breach process; FERPA/COPPA considerations for US schools and under-13 users; Bangladesh's data protection rules for local customers. Webcam/biometric data (P2) is special-category data under GDPR: explicit consent, minimal retention, EU hosting option |
| Browser headers | Set by `frontend/nginx.conf` on every response: a Content-Security-Policy (scripts only from the site, `connect-src` = `API_ORIGIN`, YouTube only for the promo video, `frame-ancestors 'none'`), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` (camera, microphone, location, payment off; revisit for webcam proctoring in Milestone 7). The build sets `INLINE_RUNTIME_CHUNK=false` so no inline script is needed. `API_ORIGIN` defaults to the build's `REACT_APP_API_URL`; CI checks the headers. HSTS belongs on the TLS proxy in front |
| Known gaps | Rate limits are per process (fine for one instance); JWT in `localStorage` (exposed to XSS; the CSP limits the damage); no audit log. See Key decisions and the Implementation Plan. |

## Performance and reliability targets

| Target | Value | Status |
|---|---|---|
| Exam-start burst | 500 candidates start within 60 s; p95 start < 1.5 s | not yet load-tested |
| Save-answer latency | p95 < 500 ms at 500 concurrent candidates | not yet load-tested |
| Answer durability | 0 accepted answers lost | design goal; offline queue planned |
| Uptime during scheduled exams | 99.9% | planned (monitoring) |
| Backups | Daily automatic backups, ≥ 7-day retention, restore tested once per quarter | planned |
| Frontend | First load < 3 s on 3G for the exam page; JS bundle kept lean | to be measured |

## Environments and delivery

| Environment | Today | Planned |
|---|---|---|
| Development | **Native** (default; fits an 8 GB PC): local PostgreSQL service + `uvicorn --reload` in `backend/.venv` + `npm start`. Optional: `docker compose up --build` (db, api, web) on PCs with RAM to spare | MinIO added to compose with object storage (3.5) |
| Test | `pytest` on in-memory SQLite; Jest smoke tests | CI (1.5) also runs pytest against Postgres, `alembic upgrade head` on an empty database, and builds + health-checks the Docker images |
| Staging | none | Same images as production, seeded demo organization |
| Production | none | Managed Postgres; API container; static web on a CDN; Sentry; uptime check on `/health` |

Delivery rules: migrations run before the new API version starts; frontend `npm run build` must have zero warnings (CRA treats warnings as errors when `CI=true`); every PR runs both test suites. Rollback = redeploy the previous image. Migrations must be backward compatible for one release (expand, then contract).

Commands:
```bash
cd backend && alembic upgrade head && python -m uvicorn app.main:app --reload --port 8000
cd backend && python -m pytest tests/ -q
cd frontend && npm start | npm test -- --watchAll=false | npm run build
```

## Key technical decisions and tradeoffs

| Decision | Reason | Alternative considered |
|---|---|---|
| Roles live on memberships; the JWT carries only the user | One person can be a candidate at one organization and an examiner at another | Role claims in the JWT: needs a token per organization and goes stale when roles change |
| Organization chosen via the `X-Organization-Id` header | Simple; works with one token for all organizations | Subdomain per organization: better branding, more DNS/CORS work (maybe later) |
| Groups decide exam visibility; no groups = everyone | Matches "batches"; zero configuration for small organizations | Explicit per-candidate assignment: too much admin work |
| One attempt per (exam, candidate), enforced by a unique constraint | Stops duplicate attempts from double clicks or parallel requests | App-level check only: racy. Retakes would need an `attempt_number` column |
| Shuffle seeded by attempt ID, not stored | Stable order on reload with no extra table | Storing the order: needed later for random *pools*, because a pool can change |
| Pool draws are stored per attempt (`attempt_questions`, 4.6) | A seeded draw alone would change when the bank changes (a question archived, one added); AC18 wants the same paper after a reload and after bank changes. Marks are frozen with it | Re-deriving the draw from the seed: no table, but breaks as soon as the bank changes |
| A pool rule gives every drawn question the same marks (4.6) | Every student's total is identical, so ranks and percentages compare fairly | Each drawn question keeps its own bank marks: totals would differ per student |
| Grading compares option values, not positions | Shuffling can never affect scores | Index-based answers: breaks with shuffling |
| Violations vs flags | Only leaving the exam can end an attempt; copy/paste/right-click are only recorded. Wrongly auto-submitting an honest candidate costs more than missing a flag | Every event counts: too many false positives |
| Server clock is authoritative | Candidates can change their device clock | Trusting `occurred_at`: easy to fake |
| Fullscreen skipped where unsupported (iOS) | Blocking iPhone users entirely is worse | Requiring a desktop: loses mobile-first users |
| Alembic owns the schema | Safe upgrades of existing institutions' data | `create_all` at startup: can't alter existing tables |
| Image answers inline as `data:` URLs | Fastest to ship for v0 | Object storage: **required before webcam snapshots**, scheduled in the plan |
| Tests on SQLite | Fast, no setup | Postgres in CI: planned, since JSON/constraint behavior differs |
| Global product, Bangladesh launch | One codebase; local conventions are settings. Gets a paying pilot fast without hardcoding one country | Separate BD and global products: double the maintenance |
| Region per deployment (not one global database) | Simple data-residency story for EU customers | Multi-region single database: complex, unnecessary at this scale |
| Translations without a library (`src/i18n/`, ~100 lines on `Intl`) | `react-i18next` and `i18next` declare a TypeScript 5 peer that conflicts with CRA's TypeScript 4.9 (needs `--legacy-peer-deps` everywhere), and they add bundle weight the performance budget doesn't allow | `react-i18next` with forced peer resolution: hides real conflicts in every install |
| Email through SMTP (`app/notify.py`), not a provider SDK | Every candidate provider (SES, Brevo, Mailgun, Postmark, Google Workspace) offers SMTP, so the owner's provider choice is configuration, not code; no SDK dependency | Provider HTTP API: slightly better error detail, but ties the code to one vendor before the owner has chosen |
| Results release has a third mode, `immediate`, as the default (4.3) | The plan named `on_close` and `manual`, but every existing exam shows the score right after submitting; making that a mode keeps them unchanged and lets coaching centers keep instant feedback | Defaulting new exams to `on_close`: changes what students already expect, with no owner decision behind it |
| Own rate limiter (`app/rate_limit.py`, ~100 lines) | Needs per-account failure counting and a class-sized per-IP allowance, which are easier to express directly; no new dependency | `slowapi`: decorators need `request` in every signature and still need custom logic for per-account failures |
| CRA kept for now | Works; migrating isn't urgent | Vite: faster builds; a reasonable later task |
| CSS-variable tokens + a small component set (`ui.js`) | One consistent look in light and dark; replaced several competing style systems | Component library (MUI/shadcn): heavier, generic look |
| Result cards are a print view saved as PDF by the browser (4.5) | The browser shapes every script correctly (Bengali conjuncts, Arabic, Devanagari) with the fonts it already has, prints one card per A4 page, and the server needs no PDF library, HarfBuzz or bundled fonts | Server-side PDFs (fpdf2 + uharfbuzz + Noto fonts): a real download link, but a font per script and a shaping engine on the server; worth it only if cards must be emailed in bulk |
| An ended session is told apart from signing out (3.15) | Any 401 on a signed-in request (`api.js` interceptor, not the sign-in call itself) and the idle timeout call `logout('expired' | 'idle')`, which notes the reason, the page and the email in `sessionStorage`; `/login` reassures, keeps the email and returns there. Only same-app paths are followed (`/…`, never `//…`), so the return can't be used as an open redirect | A plain redirect to `/login`: people lose their place and think their work is gone |
| Form drafts in localStorage (3.15) | The exam and question forms are long; keeping unsaved changes on the device (keyed by user and organization, written only after a real change) survives sign-outs, closed tabs and crashes with no server work | Server-side drafts: work across devices, but a table and an API for something that's rarely needed |
| Extra time is one number per student per exam (4.11) | An accommodation set before the exam and "ten more minutes" during it are the same thing to a student, so staff set a total (`exam_extra_time`, copied onto the attempt as `extra_minutes` when it starts or at once while it runs). The deadline is the usual one (own duration, capped by the window) plus that total, so it may run past the window's close, which is the point. A live exam can't be cut short by it (409 when the new deadline is under a minute away), and a submitted one can't change. Extra time stretches the exam's own clock only: timed sections and per-question limits keep their times. The exam page asks the server for the time left before submitting at zero, and every minute, so an extension never arrives too late; offline, it submits as before | A pause/resume button: harder to make fair and to audit; per-section or per-question extra time: rarely needed, and it can come later |
| Per-question timing runs on the same engine as timed sections (4.11b) | A per-question exam is a row of one-question blocks, so `crud._open_in_turn` serves both: one open at a time, a block whose time ran out closes at its deadline and the next opens then, a reload keeps the countdown (PRD AC26–AC28). A question's limit is the exam's for it, else the question's own default (`questions.default_time_limit_seconds`; drawn questions have only that), else none: it waits for Next. **Next** locks the question at once; only an answer in flight as its time runs out gets 5 s (`TIMEOUT_GRACE_SECONDS`). The open question alone is sent, never the ones after it, and the exam's duration still ends everything. Per-question timing can't be combined with timed sections (422): two clocks per question would contradict each other; untimed sections still work as headings. Questions keep the teacher's order (`exam_questions.position`), because a forward-only exam depends on it | A separate engine per mode: two copies of the same deadline logic to keep in step |
| Timed sections run one at a time, on the server's clock (4.10) | A section with its own time only means something if the student can't spend it elsewhere: once any section of an exam has a time limit, the sections are taken in order, the server sends only the open section's questions (upcoming ones can't be read early), refuses answers to upcoming sections and to closed ones (a 5 s grace only for answers in flight when its time runs out; finishing early locks it at once), and a closed section never reopens. `crud.section_timeline` opens the first section when the attempt starts; a section whose time has run out closes at its deadline and the next opens at that moment, so the clock keeps running while the student is away (the same rule as the exam timer). The overall duration still applies, whichever ends first; when the last section's time runs out the exam is submitted. Sections without any time are only headings, with free navigation. Finishing is per section ID, so a double click can't skip a section | Every section timed and forward-only, always: rules out sections that are just headings. Free navigation with per-section timers: a timer that doesn't stop anything |
| Staff grade one question across every paper, with partial marks (4.9) | Marking question by question is how examiners work through a pile of scripts: the same model answer in mind, fairer and faster than paper by paper. Every grading route goes through `crud.grade_answer`: written and image questions only, once the student has submitted, from 0 to what the question is worth on that paper, kept to two decimals. Blank answers earn 0 without grading. Hiding names while grading is a switch on the page | Correct/incorrect only (what the per-paper page did): no credit for a half-right explanation |
| One grade per answer, enforced by the database (4.9) | Several staff can now grade the same exam at once; a grade used to be created after checking none existed, so two graders could store two grades and the final score would add both. `0017_unique_evaluation` removes duplicates (keeping the newest) and adds `uq_evaluation_answer`; `grade_answer` catches the race and overwrites instead | A lock per answer: more moving parts for the same result |
| Every question type's rules live in one module, `app/question_types.py` (4.7) | The editor (`schemas.QuestionEdit`), the Excel import and its preview (one reader, `_read_question_sheet`), grading (`crud.question_points`) and what candidates are sent (`crud.questions_for_attempt`, the results page) call the same functions, so a type can't behave differently in one place. Before this the importer had its own checks and accepted questions the editor refused | Per-type checks in each caller: they had already drifted apart |
| Typed answers are compared kindly (4.7) | Fill-in answers match after Unicode NFC, case-folding, single spaces and stripping punctuation around them, against a list of accepted answers per blank. Numbers read Bengali, Arabic-Indic, Persian and Devanagari digits, a minus sign, a decimal comma ("9,81", "1.000,5") and digit grouping ("1,000", lakh "1,00,000"); a comma before exactly three digits groups, unless the number starts with 0 ("0,500" is 0.5). A ± margin set by the teacher, plus 1e-9 so 0.1 + 0.2 counts as 0.3. The exam page shows how a number was read ("Read as 9.81") | Exact string match: marks students wrong for "dhaka" or "9,8"; fuzzy or AI matching: unpredictable, and hard to explain to a student who lost a mark |
| Ordering and matching hide their key in the order (4.7) | An ordering question stores its items in the correct order and a matching question stores its pairs side by side, so candidates always get them shuffled (seeded by attempt and question, like options), an ordering question is never shown in the correct order, and the results page sends the stored order only once the answers are revealed. Up/down arrows instead of drag and drop: work with a keyboard and a screen reader, and on touch | Drag and drop: familiar, but needs a library, and fails keyboard and screen-reader users |
| Question text sets its own direction (4.7) | The question is the teacher's writing, so the exam page gives it `dir="auto"`: an English sentence with blanks reads in order in a right-to-left interface, and an Arabic one in a left-to-right interface | The interface direction: puts the blanks of a sentence in the wrong reading order when the two differ |
| Spreadsheet cells from user input are always text (4.5) | openpyxl stores a string starting with `=` as a formula; a student named `=HYPERLINK(...)` could otherwise plant a link in the examiner's file | Prefixing an apostrophe: changes what the examiner sees |

## Known technical debt

1. Image answers stored in the database (move to object storage).
2. ~~Abandoned attempts are never finalized~~ Fixed in 3.1: `app/jobs.py` runs every 60 s inside the API (`main.lifespan`; `BACKGROUND_JOBS=off` disables it) and scores attempts whose deadline + 30 s grace has passed, as `time_up`, ending at the deadline. Cron can run the same job: `python -m app.jobs finalize-attempts`. `crud.finish_attempt` claims an attempt atomically (`UPDATE … WHERE end_time IS NULL`), so a submit, a second tab and the job can't score it twice.
3. ~~The Excel import changes unknown tags into `"others"`~~ Fixed in 3.4: `crud.normalize_tags` keeps tags as written (lower-cased, trimmed, no leading `#`, ≤ 20 tags of ≤ 40 chars), in any script; the tag filter matches the JSON-escaped text so Bengali tags work.
4. ~~No single-question create/edit endpoint or UI~~ Fixed in 3.2: `POST /admin/questions/`, `PUT /admin/questions/{id}`, `POST /admin/questions/{id}/duplicate` with `schemas.QuestionEdit` validation (choice types: 2–10 distinct options, the correct answer(s) among them, exactly one for single choice). **Decision:** a question locks once any student has started an exam containing it (or answered it): editing would change what they saw or how they're graded. The API returns 409 and the editor offers "Duplicate and edit the copy"; exams keep the original. ~~Exams can't be edited after creation~~ Fixed in 3.3: `PUT /admin/exams/{id}` while the exam is a draft, or published but not yet open, and nobody has started it; otherwise 409 with the reason (`crud.exam_edit_blocker`). Every exam payload carries `edit_blocked` (null while editable).
5. ~~Debug prints and no structured logging~~ Done: JSON logs to stdout via `app/logging_config.py` (one `app.request` line per request with `request_id`, `method`, `path`, `status`, `duration_ms`, `user_id`, `organization_id`, `role`); every response has an `X-Request-ID` header; unexpected 500s return a generic message with that reference instead of exception text. Health check: `GET /health` (200, or 503 when the database is unreachable).
6. Unused legacy grading endpoints in `admin.py`: `/exams/attempts/{id}`, `/exams/attempts/{id}/evaluate`, `/answers/{id}/evaluate`, `/answers/{id}/evaluation`, `/attempts/{id}/results`. The frontend doesn't call them; remove them after confirming. Since 4.9 the two that grade check every mark through `crud.grade_answer`, like the pages do.
7. Naive `datetime.utcnow` defaults in several models; prefer timezone-aware values.
8. JWT in `localStorage`. ~~JWT subject is the email~~ Fixed in 2.8: the subject is the user ID; tokens with an email subject are still accepted until the next release (remove the fallback in `security.get_current_user`).
9. ~~README project structure stale~~ Fixed in 1.7.
