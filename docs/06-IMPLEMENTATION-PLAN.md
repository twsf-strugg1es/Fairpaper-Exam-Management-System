# 6. Implementation Plan: Fairpaper

Purpose: give the AI agent an ordered build sequence with checkpoints.
Status: living document · Last updated 2026-10-12 · Tick tasks (`[x]`) when merged.

The product already exists (see "Completed"). Milestones 1–6 take it to a **paid pilot**. Milestones 7–8 come after the pilot.

## How to work through this plan

- Do tasks **in order inside a milestone**, unless the Dependency column allows otherwise. Each task = one PR.
- **Owner/agent:** `agent` = any coding agent; `owner` = the product owner must decide or provide something (accounts, keys, choices).
- **Every task's definition of done also includes:** backend tests pass (`python -m pytest tests/ -q`); for new endpoints, a cross-organization access test; a migration if the schema changed; `npm run build` has zero warnings; the affected docs (02 TRD, 03 App Flow, 05 Schema) are updated.
- **Before moving to the next milestone:** run the app, walk the journeys in [03-APP-FLOW.md](03-APP-FLOW.md) affected by the milestone, verify the related acceptance criteria in [01-PRD.md](01-PRD.md), and record any unresolved issue at the bottom of this file under "Open issues".

## Completed

- [x] Phase 1: security holes fixed (answer keys hidden, ownership checks, Alembic baseline)
- [x] Phase 2: multi-organization restructure (organizations, memberships, roles, groups, join codes)
- [x] Phase 3: exam integrity step 1 (shuffle, fullscreen, violations, auto-submit, integrity report, one attempt per exam) + UI redesign

---

## Milestone 1: Project setup

| ✓ | ID | Task | Owner | Inputs | Output | Definition of done | Depends on |
|---|---|---|---|---|---|---|---|
| [x] | 1.1 | Rename the product to **Fairpaper** in the UI | agent (+ owner approves the mark) | 04 UI/UX Brief "Assets" | `Logo` in `ui.js`, `AuthLayout` text, `public/index.html` title, `manifest.json`, favicons | No "PorikkhaKori" string left in `frontend/` (`grep -ri porikkha`); the new mark is used in light and dark | — |
| [x] | 1.2 | `.env.example` for backend and frontend | agent | 02 TRD env tables | `backend/.env.example`, `frontend/.env.example` | A fresh clone runs by copying the examples | — |
| [x] | 1.3 | Docker setup | agent | — | `backend/Dockerfile` (+ entrypoint running migrations, non-root, healthcheck), `frontend/Dockerfile` (nginx, SPA fallback, security headers), `docker-compose.yml` (db, api, web), `.gitattributes` (LF everywhere) | CI (task 1.5) builds both images and the compose stack passes `/health`. Local `docker compose up` is optional: the owner's PC runs natively (8 GB RAM). MinIO is added with object storage in 3.5 | 1.2 |
| [x] | 1.4 | `/health` endpoint; remove the "Hello" root | agent | — | `GET /health` checks the DB connection | Returns 200 / 503; test added | — |
| [x] | 1.5 | CI (GitHub Actions) | agent | — | `.github/workflows/ci.yml`: backend tests on SQLite; on PostgreSQL: `alembic upgrade head` on an empty DB, `alembic check` (models match migrations), downgrade + re-upgrade, full test suite; frontend test + build with `CI=true`; Semgrep (blocking); Docker images built and the compose stack health-checked | Every push and PR to `main` runs all jobs; a failing job blocks merging (owner enables branch protection on `main`) | 1.3 |
| [x] | 1.6 | Structured logging; remove the debug prints in `start_exam` | agent | — | JSON logs with request ID, user ID, organization ID | No `print(` in `backend/app` | — |
| [x] | 1.7 | Fix the README (structure, links to the six docs) | agent | — | README | Matches the repo tree | — |
| [x] | 1.11 | Apply design direction A ("Exam paper") to the app | agent | `design/v0/Fairpaper v0.html`, 04 Brief | Tokens (paper, ink, marker green, red pen), 2–6 px radii, no shadows/blur/pulse; `bubble`, `status-dot`, `tag`, `kbd`, `sheet` classes; app shell rail; auth sheet; exams register; exam page (lettered answer bubbles, bubble question map, slim timer bar, keyboard 1–9 / ← → / F); rules screen; student dashboard | Every screen renders in the new style in light and dark at 1280 × 800; tests and build pass | 1.1 |
| [x] | 1.8 | i18n framework (global readiness) | agent | 02 TRD "Internationalization", 04 Brief "Internationalization rules" | `src/i18n/` (no library: English text is the key, `t()` / `tn()` with `Intl.PluralRules`, `<html lang dir>` synced); every screen's strings wrapped; `errorMessage()` translates server messages; date/number formatters use the chosen language; pseudo-language `?lang=en-XA`; `npm run i18n:extract` writes `src/i18n/strings.json` (515 strings incl. 38 server messages) and CI fails if it's stale | Pseudo-language screenshots of every App Flow screen show no plain English except data and the brand; app looks identical in English | 1.1 |
| [x] | 1.9 | Organization and user locale settings | agent | 05 Schema | Migration `0006_locale_settings`: `country`, `default_language` (default `en`), `timezone` (IANA, default `UTC`), `currency` on organizations; `language` on users. `PATCH /org` changes any of them; org signup starts in the browser's timezone. Organization → Settings has a "Region and language" card; Account has a Language field. Every date shows in the organization's timezone; exam windows add a label (e.g. `GMT+6`) when it differs from the viewer's, and the exam form is entered in it | Exam windows show in the organization's timezone with a label when it differs from the viewer's; tests (`test_locale.py`, `utils.test.js`) | 1.8 |
| [x] | 1.10 | RTL-safe layout | agent | 04 Brief | Every physical utility swapped for its logical one (`ms`/`me`, `ps`/`pe`, `start`/`end`, `text-start`/`text-end`, `border-s`/`border-e`, `rounded-s`/`rounded-e`); `<html dir>` comes from the language catalog; switch knob, select caret and back/forward arrows mirror; exam ←/→ follow the reading direction; test pseudo-language `?lang=en-XB` renders right to left | With `dir="rtl"` forced (`en-XB`), J1–J6 layouts aren't broken (screenshots in the checkpoint report) | 1.8 |

## Milestone 2: Data and auth

| ✓ | ID | Task | Owner | Inputs | Output | Definition of done | Depends on |
|---|---|---|---|---|---|---|---|
| [x] | 2.1 | Missing indexes + unique `answers(attempt_id, question_id)` | agent | 05 Schema "Indexes" | Migration `0007_indexes_unique_answers` (deduplicates answers first, keeping the evaluated one) | Upgrade works on a copy of real data; save-answer still upserts | 1.5 |
| [x] | 2.2 | Server-side exam validation | agent | 05 Schema "Data validation" | `ExamCreate` validators | start < end, duration ≥ 1, ≥ 1 question → 422; tests | — |
| [x] | 2.3 | Email sending abstraction | agent; **owner** picks the provider | provider SMTP credentials | `app/notify.py` (`send_email`): `console` (`.eml` files, dev), `memory` (tests), `smtp` (any provider). Owner still picks the provider and sender address (Open issues) | Tests use the memory backend; provider set by env var | — |
| [x] | 2.4 | Password reset | agent | 2.3 | `password_reset_tokens` table (hashed, 30 min, single use); 2 endpoints; `/forgot-password`, `/reset-password/:token` pages | PRD **AC14** passes; tests for reuse, expiry, unknown email | 2.3 |
| [x] | 2.5 | Email verification (soft) | agent | 2.3 | `users.email_verified_at`; verify link; banner until verified | Unverified users can still take exams (pilot) | 2.3 |
| [x] | 2.6 | Rate limiting on `/token`, signup, reset | agent | — | `app/rate_limit.py` (own limiter, see TRD decision): sign-in per IP + failures per account, signup and org signup per IP, join codes per user. Reset gets its limit with 2.4 | Exceeding the limit → 429 with `Retry-After`; `test_rate_limit.py` | — |
| [x] | 2.7 | Archive instead of destroy | agent | 05 Schema "Retention" | `questions.archived_at`, `exams.archived_at`; delete = archive once used | Deleting a used question never removes answers; past results still render; tests | 2.1 |
| [x] | 2.8 | JWT subject = user ID (accept old email tokens for one release) | agent | — | `security.py`, `routers/auth.py`; `test_jwt_subject.py` | Changing an email doesn't log the user out; test | — |

## Milestone 3: Core journey (pilot-ready exam operations)

| ✓ | ID | Task | Owner | Inputs | Output | Definition of done | Depends on |
|---|---|---|---|---|---|---|---|
| [x] | 3.1 | Finalize abandoned attempts | agent | 02 TRD debt #2 | `app/jobs.py`: an asyncio loop in the API (every 60 s, no new dependency) plus a cron entry point; scores attempts past their deadline + grace as `time_up`, ending at the deadline; scoring is claimed atomically so it happens once | An attempt with no submit is finalized within 2 minutes of its deadline; test with a mocked clock | 1.3 |
| [x] | 3.2 | Single-question create/edit | agent | 03 App Flow (question editor) | `POST/PUT /admin/questions`; editor page with type-specific fields | All 4 types can be created and edited; a used question → editing creates a new version or is blocked (decide and document) | 2.7 |
| [x] | 3.3 | Edit exam before it opens | agent | — | `PUT /admin/exams/{id}`; `/admin-exams/:id/edit` | Allowed while Draft/Scheduled and no attempts exist; otherwise 409 with a reason | 2.2 |
| [x] | 3.4 | Free tags | agent | 02 TRD debt #3 | Remove the hardcoded list in the import; tag autocomplete | Imported tags are kept as written (lower-cased) | — |
| [ ] | 3.5 | Object storage for image answers | agent; **owner** creates the bucket | S3/R2 credentials | `app/storage.py`; upload endpoint with server-side type/size checks; signed URLs; migration moving existing `data:` URLs | No `data:` URLs left in `answers`; graders still see images | 1.3 |
| [x] | 3.6 | Bulk candidate import | agent | 2.3 | Upload CSV/XLSX → preview → confirm → report; invite email with set-password link | PRD **AC15** passes | 2.3, 2.4 |
| [x] | 3.7 | Add staff by invite (no account yet) | agent | 2.3 | Invite email → set password → membership | An examiner can be invited by email | 3.6 |
| [x] | 3.8 | Offline-tolerant answer saving | agent | — | IndexedDB queue, retry with backoff, saved/saving/offline indicator; the server ignores stale writes via `client_seq` | Disconnecting the network for 60 s mid-exam loses nothing; manual test + unit test of the queue | 2.1 |
| [ ] | 3.9 | Notifications (email; SMS when the gateway is ready) | agent; **owner** picks the SMS gateways | 2.3, gateway keys | Exam published (target groups), 1 h reminder, results published; per-organization switches; sent in the recipient's language; SMS routed by phone country (BD gateway for +880, global provider otherwise) | Events send once (idempotent); tests with the console backend | 2.3, 3.1 |
| [x] | 3.11 | Clipboard protection during exams | agent | PRD F25, AC21 | `useExamIntegrity`: clear the clipboard on Start exam and on every return to the exam; block paste via keys (Ctrl/Cmd+V, Shift+Insert), context menu, `drop` and middle-click (`auxclick`); flag each attempt as `copy_paste` | **AC21** passes in Chrome, Edge and Firefox; a failed clipboard clear never breaks the exam | — |
| [x] | 3.11b | Blur on leaving, click to return; no question text selection (owner request, 2026-10-31) | agent | PRD F7, F25, AC29, AC30 | `useExamIntegrity`: `blocked` stays on after focus returns until `returnToExam()` (a click anywhere or the button), which also empties the clipboard and re-enters fullscreen; `selectstart` and Ctrl/Cmd+A blocked outside answer boxes. `ExamPage`: the exam blurs (static `blur-md`, `inert`) behind the card, and placeholder bars replace the question text while hidden | **AC29**, **AC30** pass in the browser; hook tests | 3.11 |
| [x] | 3.15 | Edge-case states on every screen (owner request, 2026-10-31) | agent | 04 Brief "Interaction states", 03 "Empty and blocked states" | `ui.js`: skeleton `PageLoader` variants with a slow-connection note, `ErrorState`, `NoResults`, `UploadProgress`, `EmailSuggestion`, `DraftNotice`; `Toaster.js`, `OfflineBanner.js`, `NoAccess.js`, `hooks/useDraft.js`; `utils`: `errorKind`, `suggestCorrection`, `suggestEmail`; 401 interceptor + `logout(reason)` + return path; applied to every list and detail page, the exam page, the exam and question forms, imports and photo answers | Each state forced in the browser (slow, unreachable, 500, offline, wrong role, expired session, misspelled search, email typo, field errors, draft restore, publish toast); `states.test.js` | — |
| [ ] | 3.12 | Public landing page | agent; **owner** approves the copy | PRD F26, 04 Brief (landing exception) | `/` for signed-out visitors: hero, how it works, integrity features, who it's for, pricing placeholder, sign-up calls to action; responsive to 360 px; restrained scroll effects | Lighthouse 90+ on mobile and desktop; reduced motion fully static; no layout shift | 1.1 |
| [x] | 3.13 | Launch waitlist | agent; **owner** picks the sender address | PRD F27, AC22–AC23; 05 Schema `waitlist_signups` | `POST /waitlist` (public; rate-limited; same response whether new or existing; honeypot field against bots); `/waitlist` page in direction A; `manage_waitlist.py export` (CSV) and `send-launch` (uses `notify.py`, sets `notified_at`, includes unsubscribe link); `GET /waitlist/unsubscribe/{token}` | **AC22**, **AC23** pass; cross-check that no email is ever returned by the API | 2.3, 2.6 |
| [ ] | 3.14 | Product video slot on the landing page | agent; **owner** provides the YouTube link | PRD F28, AC24 | `PromoVideo` component: 16:9 frame; no link → "Video coming soon" placeholder; link set → `youtube-nocookie.com` thumbnail facade, iframe loaded on click; link read from `REACT_APP_PROMO_VIDEO_URL` | **AC24** passes; no third-party request until the visitor presses play | 3.12 |
| [x] | 3.10 | "Get started" checklist for new organizations | agent | 03 App Flow first use | Checklist on the empty Exams page | Disappears when all 4 steps are done | 3.6 |

## Milestone 4: Secondary features (competitive set for coaching centers)

| ✓ | ID | Task | Owner | Inputs | Output | Definition of done | Depends on |
|---|---|---|---|---|---|---|---|
| [ ] | 4.1 | Negative marking | agent | PRD AC16 | `exams.negative_mark` (float, default 0); grading; shown on the rules screen and results | **AC16** passes; negative totals follow the owner's decision (allow, or floor at 0) | — |
| [x] | 4.2 | Per-exam marks | agent | — | `exam_questions.marks` (nullable override) | Totals use the override; test | — |
| [x] | 4.3 | Result publishing control | agent | — | `exams.results_release` = `on_close` / `manual`; Publish results button | Candidates see nothing until released; test | — |
| [x] | 4.4 | Merit list / rank | agent | PRD AC17 | Ranked tab on Exam results; optional candidate-visible rank | **AC17** passes | 4.3 |
| [x] | 4.5 | Export XLSX + PDF result cards | agent | — | `GET /admin/exams/{id}/export.xlsx` (Results, Marks by question, Questions, Exam; `app/results_export.py`); `GET /admin/exams/{id}/result-cards` + `/admin-exams/:examId/cards` print view (one A4 card per page, the browser saves the PDF); **Export to Excel**, **Result cards** and per-row **Card** on Exam results | Opens in Excel with Bengali names intact (`test_results_export.py`); a name starting with `=` stays text; 4 cards print as 4 PDF pages | 4.4 |
| [x] | 4.6 | Random question pools | agent | PRD AC18 | Migration `0016_pool_rules`: `exam_pool_rules`, `attempt_questions` (paper drawn once at start, marks frozen); `crud.attempt_questions` used by every attempt-scoped read; rule editor with live match counts on the exam form; 422 on save / 409 on publish when the bank can't fill a rule; export labels drawn slots | **AC18** passes (`test_pool_rules.py`: same 5 after reload, resume, restart and bank changes); grading uses the stored questions; 260 tests green on SQLite and PostgreSQL; `alembic check` clean | 3.4 |
| [x] | 4.7 | Question types: true/false, fill-in-the-blank, numeric (tolerance), matching, ordering | agent | — | `app/question_types.py` (check a key, grade, what candidates see) used by the editor, one Excel reader for import and preview (all rows checked first), grading and candidate payloads; results send `is_correct` once answers are revealed; `AnswerKeyEditor` (a card per type, **Insert a blank**), exam renderers (blanks inside the sentence, number read-back, matching dropdowns, ordering arrows), `AnswerKey` in the bank, `questionTypes.js` for display; template with a row per type | Each type auto-grades (`test_question_types.py`: typed numbers and words, keys, grading, shuffled order never the key, template imports as it is, a bad row imports nothing); `questionTypes.test.js` (client number reading matches the server, keys survive editor round trips); walked in the app: write, sit and score 10/10, right-to-left | 3.2 |
| [ ] | 4.8 | KaTeX math + images in questions | agent | 3.5 | Rendering in the editor, exam and results | `$...$` renders; images load via signed URLs | 3.2, 3.5 |
| [x] | 4.9 | Grade by question + partial marks | agent | — | `/admin-exams/:examId/grade/:questionId` (`GradeByQuestionPage`): every submitted answer to one question, marks control (`GradeControl`: 0 / half / full in one click, any mark to two decimals, Enter saves and moves on, comment), hide names, only-ungraded filter, progress per question; the per-student page uses the same control; `GET /admin/exams/{id}/grading[/{question_id}]`; `crud.grade_answer` behind every grading route (0–worth on that paper, submitted only, written/image only); migration `0017_unique_evaluation` (one grade per answer); blank answers 0 without grading; students see "2 of 4 marks" | All answers to a question graded on one page by keyboard (walked in the app); `test_partial_marks.py` (range, submitted only, auto-graded refused, two graders leave one grade, blank is 0, other organizations 404); `GradeControl.test.js`; 0017 keeps the newest of two grades on PostgreSQL | — |
| [x] | 4.10 | Sections with their own time limits | agent | — | Migration `0018_exam_sections`: `exam_sections`, `section_id` on `exam_questions` / `exam_pool_rules` / `attempt_questions`, `attempt_sections`; `crud.section_timeline` (open one at a time, close at the deadline, next opens then), `finish_section`, section checks in `save_answer`; session sends only the open section's questions; `POST /student/attempts/{id}/sections/{section_id}/finish`; exam form **Sections** card (titles, minutes, instructions, order, where new picks go, a section per question and rule); exam page: section heading and instructions, map grouped by section, section countdown, **Finish section** with confirm, automatic move on time-out with a notice; rules screen lists the sections | A section locks when its time ends (`test_sections.py`: only the open section is sent, early and late answers refused, finish twice skips nothing, the clock runs while away, the last section's time-out submits); walked in the app with a 1-minute section | 4.6 |
| [x] | 4.11b | Per-question time limits | agent | PRD F29, AC25–AC28; 05 Schema (`timing_mode`, `exam_questions.time_limit_seconds`, `attempt_question_timings`) | Migration `0019_per_question_timing`: `exams.timing_mode`, `questions.default_time_limit_seconds`, `exam_questions.time_limit_seconds` and `position`, `attempt_question_timings`; `crud.question_timeline` on the engine shared with timed sections (`_open_in_turn`), `next_question`, `closed_for_good` (Next locks at once, 5 s grace only on time-out); session sends only the open question with `progress`; `POST /student/attempts/{id}/questions/{question_id}/next`; exam form **Timing** + seconds per question + **Apply** to all; editor **Seconds**; Excel `time_limit_seconds`; exam page: question countdown, **Next question** (asks first when unanswered), locked step map, moves on by itself, rules line | AC25–AC28 pass (`test_per_question.py`: one question sent, early and locked answers refused, the clock runs on through a reload, the exam deadline caps a question, no-limit waits, the last time-out submits, timing checks, defaults in editor and import); walked in the app with a 10-second question | 3.1, 3.3 |
| [x] | 4.11 | Accommodations: extra time per candidate, extend a live attempt | agent | — | Migration `0020_extra_time`: `exam_attempts.extra_minutes`, `exam_extra_time`; deadline = usual deadline + extra (past the window's close if need be); `crud.set_extra_time`; `GET/PUT /admin/exams/{id}/extra-time[/{student_id}]`, `GET /student/attempts/{id}/clock`; Exam results: **Add time** per attempt and an **Extra time** card; exam page asks the server before submitting at zero and every minute, with a notice; rules screen shows the extra minutes | Deadline respects the extension (`test_extra_time.py`: set before start, added while writing (saves accepted, the job waits), past the window, can't cut a live exam short, not after submitting, organization and role checks); walked in the app: a 1-minute exam extended by 10 kept running | 3.1 |
| [ ] | 4.12 | Analytics: per-topic breakdown, item analysis | agent | — | Report tab | Difficulty index and discrimination shown per question | 4.4 |
| [ ] | 4.13 | Bengali translation | agent; **owner** reviews the translations | 1.8 | `src/locales/bn.json`, language switch | Every screen in the App Flow inventory is translated | 1.8 |

## Milestone 5: Quality

| ✓ | ID | Task | Owner | Inputs | Output | Definition of done | Depends on |
|---|---|---|---|---|---|---|---|
| [ ] | 5.1 | Security review | agent | 02 TRD "Security" | Fixes + a report in the PR | Tenant-isolation test for every endpoint; no answer keys in candidate payloads; dependency audit clean | M3 |
| [ ] | 5.2 | Load test | agent | TRD performance targets | k6/Locust script in `loadtest/` | 500 candidates start + save meets the p95 targets on staging-sized infrastructure, or the gaps are fixed | 6.1 |
| [ ] | 5.3 | Accessibility pass | agent | 04 Brief "Accessibility" | Fixes | Keyboard-only walk of J1–J6; axe shows no serious issues; reduced-motion respected | — |
| [ ] | 5.4 | Low-end PC + performance pass | agent | 04 Brief "Performance budget", "Motion", "Current code vs. this brief" | Remove `backdrop-blur` and pulse animations; route-level code splitting; font subsetting | Every budget in the brief met on the target PC profile (Lighthouse desktop with CPU throttling) | 3.8 |
| [x] | 5.4b | `DesktopOnly` gate below 1024 px | agent | 03 App Flow "Desktop only" | Component wrapping every route except landing, login and signup; resize-aware; never interrupts a running exam | PRD **AC19** and **AC20** pass | — |
| [ ] | 5.5 | Error tracking | agent; **owner** creates the Sentry project | DSN | Sentry in the API + web | A test error appears in Sentry with user/organization context | 1.6 |
| [ ] | 5.6 | Remove legacy grading endpoints | agent | 02 TRD debt #6 | Smaller `admin.py` | The frontend doesn't call them; tests updated | — |
| [ ] | 5.7 | Frontend tests for the exam page | agent | — | Jest tests: rules → answer → submit; blocked overlay | Run in CI | 1.5 |

## Milestone 6: Release (pilot)

| ✓ | ID | Task | Owner | Inputs | Output | Definition of done | Depends on |
|---|---|---|---|---|---|---|---|
| [ ] | 6.1 | Staging + production environments | agent; **owner** provides the cloud account + domain | Domain, hosting choice | Managed Postgres, API container, static web on a CDN, HTTPS | Staging deploys automatically on main; production on tag | 1.3, 1.5 |
| [ ] | 6.2 | Backups and restore drill | agent | — | Daily backups, 7+ days | A restore into staging was done once and documented | 6.1 |
| [ ] | 6.3 | Deploy and rollback runbook | agent | — | `docs/DEPLOY.md` | Covers migrate → deploy → verify `/health` → rollback (previous image; migrations expand-then-contract) | 6.1 |
| [ ] | 6.4 | Uptime monitoring + alerts during exam windows | agent | — | Uptime check on `/health`, alert to the owner | Alert received in a test | 6.1 |
| [ ] | 6.5 | Terms of Service + Privacy Policy pages | **owner** writes/approves the text; agent adds the pages | Legal text | `/terms`, `/privacy`, linked from signup | Linked and reachable signed out | — |
| [ ] | 6.6 | Pilot test plan | agent + owner | PRD acceptance criteria | A checklist run on production with a dummy organization: AC1–AC17 | All pass; issues logged | M3–M5 |
| [ ] | 6.7 | Pilot launch | owner | — | One institution onboarded | PRD success measures tracked weekly | 6.6 |

---

## Milestone 7 (after pilot): Proctoring step 2

| ✓ | ID | Task | Depends on |
|---|---|---|---|
| [ ] | 7.1 | Consent screen + per-exam proctoring settings + retention (90 days) | 3.5 |
| [ ] | 7.2 | Webcam snapshots at random intervals (30–90 s) → object storage | 7.1 |
| [ ] | 7.3 | In-browser face checks (MediaPipe): `no_face`, `multiple_faces` as **flags** | 7.2 |
| [ ] | 7.4 | ID photo before start; shown in the integrity report | 7.2 |
| [ ] | 7.5 | Safe Exam Browser support (Config Key / Browser Exam Key header check) | — |
| [ ] | 7.6 | Live proctor dashboard (online, violations; pause/extend/end) | 4.11 |
| [ ] | 7.7 | Similarity check for written answers within an exam | — |

## Milestone 8 (after pilot): Business

| ✓ | ID | Task | Depends on |
|---|---|---|---|
| [ ] | 8.1 | Plans and limits enforced on the server | — |
| [ ] | 8.2 | Billing: SSLCommerz / bKash (Bangladesh) + Stripe or Paddle (global), regional prices, invoices, trial | 8.1 |
| [ ] | 8.3 | Organization branding (logo, color, subdomain) | 3.5 |
| [ ] | 8.4 | Audit log of staff actions | — |
| [ ] | 8.5 | Google sign-in | — |
| [ ] | 8.6 | Organization export (ZIP) + account deletion with anonymization | 2.7 |
| [ ] | 8.7 | Paid public mock tests | 8.2 |
| [ ] | 8.8 | PWA (installable, offline shell) | 3.8 |
| [ ] | 8.9 | GDPR toolkit: data processing agreement, subprocessor list, cookie consent, data export/deletion requests, breach process (**owner** + legal review) | 8.6 |
| [ ] | 8.10 | EU region deployment (separate stack, organizations pinned by `data_region`) | 6.1, 1.9 |
| [ ] | 8.11 | More translations based on the first global market (e.g. Hindi, Arabic with RTL, Spanish) | 1.10, 4.13 |
| [ ] | 8.12 | Global marketing site + English-first onboarding | 1.8 |

## Open issues

Record anything unresolved at a milestone checkpoint here: date, issue, decision needed, owner.

- 2026-10-12: Owner decisions pending: email provider (2.3), SMS gateway (3.9), hosting region (6.1), Fairpaper logo mark (1.1), negative-total policy (4.1), retakes (PRD open question 7), first global market and global pricing (PRD open questions 8–9), waitlist sender address (3.13), YouTube link for the product video (3.14).
- 2026-10-26: Security scan at the end of Milestone 2: Semgrep 0, Nuclei 0, ZAP on the API 0. ZAP on the frontend dev server flagged missing headers (dev server only) and a missing Content-Security-Policy, which was real. Fixed 2026-10-27: CSP + Permissions-Policy in `frontend/nginx.conf`, checked by CI and by walking the production build in a browser with zero violations.
- 2026-10-27: 3.2 decision (agent, documented in the TRD): questions students have met are locked rather than versioned in place; staff duplicate them to make a new version. Tell us if you'd rather have automatic versions.
- 2026-10-26: 2.3 built provider-neutral (SMTP). Owner still decides: which email provider, and the sender address/domain (needs SPF/DKIM on the domain). Until then the API writes emails to a local outbox.
- 2026-10-26: Remove the email-subject fallback for old tokens in `security.get_current_user` in the release after 2.8 ships (agent; no owner decision).
- 2026-10-28: 3.13 waitlist built. Still needed before `manage_waitlist.py send-launch` can run: the sender address (`EMAIL_FROM`, with SPF/DKIM) and the owner's approval of the launch email wording (placeholder in `backend/manage_waitlist.py`). Collecting signups needs neither.
- 2026-10-28: Landing prototype v2 after owner feedback: one simple page (hero with the waitlist form inline, three points, video slot, closing waitlist band); the proctoring demo and timer are out, v1 kept as `index-v1.html`. Owner still approves the copy (3.12).
- 2026-10-28: The landing prototype (`scrollcraft/builds/fairpaper-landing/`) now saves signups through `POST /waitlist`. When it's hosted, set `<meta name="fairpaper-api">` in `index.html` and `waitlist.html` to the API's public address and add the landing page's origin to the API's `CORS_ORIGINS`. Porting it into the app at `/` is task 3.12 (needs the owner's copy approval).
- 2026-10-28: Landing SEO/AEO: a 7-question FAQ (with FAQPage structured data), Organization (Kori) and WebSite data, canonical and social-card tags, `og-image.png`, `robots.txt` (allows ChatGPT's OAI-SearchBot), `sitemap.xml` and `llms.txt`; draft pages are `noindex`. Every absolute URL uses **https://fairpaper.app** as a placeholder: change it in `index.html`, `privacy.html`, `terms.html`, `robots.txt`, `sitemap.xml` and `llms.txt` if the domain differs. After hosting: verify in Google Search Console and Bing Webmaster Tools and submit the sitemap.
- 2026-10-28: Terms of Use for the landing page (`terms.html`), adapted from General Legal's CC0 template: Bangladesh law and Dhaka courts, consumers keep their own country's mandatory protections; the template's US arbitration clauses and US state notices were left out. Same rule as the Privacy Policy: fill the highlighted placeholders (domain, company name, address, contact and security emails, liability cap, court city) and get a lawyer's review before publishing.
- 2026-10-29: **4.1 Negative marking deferred by the owner** ("dont add the negative marking feature now"). Skip it until the owner brings it back; it still needs the negative-total policy.
- 2026-10-29: Owner asked to unlink the Privacy Policy and Terms of Use until launch. `privacy.html` and `terms.html` stay in the landing folder (now `noindex`, out of `sitemap.xml` and `llms.txt`); nothing links to them. Re-link them from the footer and the waitlist form when the text is final. Note: collecting waitlist emails publicly without a reachable privacy notice can breach GDPR and Bangladesh's PDPA, so re-link before the page is promoted to people outside a private preview.
- 2026-10-28: Privacy Policy for the landing page and waitlist (`scrollcraft/builds/fairpaper-landing/privacy.html`), adapted from General Legal's CC0 GDPR template and written to match what the site actually collects. **Before the landing page goes public** the owner must fill the highlighted placeholders (registered company name, address, privacy email, hosting and email providers, storage region, retention periods) and have a lawyer review it, especially against Bangladesh's Personal Data Protection Act 2026. Fonts are now self-hosted (`fonts/`, SIL OFL), so the landing page makes no third-party requests. The exam platform itself needs its own policy (and terms, and a data processing agreement for organizations) before launch.
- 2026-10-28: Renamed TestKori → Fairpaper (owner decision; a name that works internationally). Changed everywhere in code, emails, docs and the landing page (now `scrollcraft/builds/fairpaper-landing/`). Not changed: the GitHub repository name, the `milestone-1` branch, and existing local Docker volumes (the compose database user is now `fairpaper`, so run `docker compose down -v` once). The owner still needs to register the domain (fairpaper.app suggested) and check the trademark.
- 2026-10-28: The owner switched the logo to the answer-sheet row (four bubbles, the third filled), applied to `LogoMark`, the favicons, `logo192/512.png` and the landing pages. The landing page uses Geist; the app still uses IBM Plex Sans.
