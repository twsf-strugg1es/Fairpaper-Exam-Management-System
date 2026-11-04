# Guide for coding agents

Read this first. The six project documents are in `docs/`. Read them in this order:
1. [01-PRD.md](01-PRD.md): what to build and the acceptance criteria
2. [02-TRD.md](02-TRD.md): stack, architecture, security, key decisions, known debt
3. [03-APP-FLOW.md](03-APP-FLOW.md): every screen, route and user path
4. [04-UI-UX-BRIEF.md](04-UI-UX-BRIEF.md): visual rules, tokens, components
5. [05-BACKEND-SCHEMA.md](05-BACKEND-SCHEMA.md): tables, relationships, who can do what
6. [06-IMPLEMENTATION-PLAN.md](06-IMPLEMENTATION-PLAN.md): **what to build next**, in order

Before implementing, flag any contradiction between these documents and the code, and ask the owner to resolve it.

## Workflow (follow every session)

1. **Sync first.** `git pull` (or clone) before anything else. Then read the six docs and the "Open issues" section of `06-IMPLEMENTATION-PLAN.md`, so you know where the last session stopped.
2. **One milestone per session.** Pick the first milestone with unticked tasks and do its tasks in order, one commit per task. Don't start the next milestone.
3. **Never guess an owner decision.** If a task's Owner column says **owner**, or it needs something only the owner has (logo, provider choice, API keys, legal text, pricing), skip it. Add it to "Open issues" and continue with tasks that don't depend on it.
4. **Keep the docs true.** After each task: tick it in the plan; update `02-TRD`, `03-APP-FLOW` and `05-BACKEND-SCHEMA` if you changed what they describe. Docs and code must never disagree. The docs are the only memory the next session has.
5. **Stop at the checkpoint.** When the milestone is done (or blocked), run both test suites and the build, walk the affected journeys in `03-APP-FLOW`, check the related PRD acceptance criteria, then **stop and report to the owner**:
   - what was done (tasks + commits)
   - what's left or blocked, and why
   - decisions needed from the owner
   - anything in the docs you think is wrong
   - **visuals** when the milestone changed anything the user can see: screenshots of the affected screens from the running app at 1280 × 800 (plus 390 px phone width for the landing page)

   Wait for the owner's reply before continuing.
6. **End of the plan: draft the next version, then wait.** When every task in Milestones 1–6 is ticked (or the owner asks), write drafts of the next version's six documents in `docs/next/` (same template and file names). Base them on the PRD's remaining planned features, the plan's Milestones 7–8, the open issues, and what you learned. Then **stop and ask the owner to review**. Don't implement anything from `docs/next/` until the owner approves it. On approval, move the current docs to `docs/archive/v<N>/` and `docs/next/` to `docs/`.
7. **Don't push or deploy** unless the owner asks. Commit locally on a branch named `milestone-<N>`.

## What this is
Fairpaper: a multi-tenant online exam platform for coaching centers, schools and hiring teams. Built for a global audience, launching in Bangladesh first. It has a FastAPI + PostgreSQL backend in `backend/` and a React (CRA + Tailwind) frontend in `frontend/`.

## Commands
```bash
# backend (needs backend/.env with DATABASE_URL and SECRET_KEY)
cd backend
pip install -r requirements.txt
alembic upgrade head
python create_admin.py                       # demo org + owner admin@example.com; prints a random password once
python -m uvicorn app.main:app --reload --port 8000
DATABASE_URL=sqlite:///:memory: SECRET_KEY=tests-only-key-never-use-it-anywhere-else python -m pytest tests/ -q   # must pass before every commit; tests use SQLite but app import needs both vars

# frontend
cd frontend
npm install
npm start                                    # http://localhost:3000
npm test -- --watchAll=false
npm run build                                # must finish with no warnings
```

## Rules that must not be broken
1. **Tenant isolation.** Every organization-scoped endpoint takes its membership from `permissions.require_staff` / `require_manager` / `require_candidate` and filters every query by `membership.organization_id`. Add the endpoint to `CASES` in `tests/test_tenant_isolation.py` (the test fails until you do); it proves another organization gets 403/404 and changes nothing.
2. **Never send `correct_answers` to candidates** before the exam has closed. Build candidate question payloads with `crud.questions_for_attempt`.
3. **Schema changes go through Alembic.** Add a new `backend/migrations/versions/000N_<name>.py` with `down_revision` set to the previous one. Never edit applied migrations. Use `server_default` for new non-null columns.
4. **The server is authoritative** for time, deadlines, violation counts and scores. The client only displays them.
5. **Shuffling is seeded by attempt ID** (stable on reload). Grading compares option values, never positions.
6. **Integrity features flag, they don't accuse.** Flag events never end an attempt. Only `VIOLATION_EVENTS` count toward `max_violations`.
7. Store and send times as UTC ISO strings with an offset. The frontend formats them with `src/utils.js`, in the organization's timezone (`setTimeZone()` in `App.js`); exam windows use `formatExamTime()`, which adds the zone when it isn't the viewer's.
8. **Global by default.** Never hardcode one country's language, currency, phone format, timezone or exam convention. Local behavior (negative marking, merit lists, bKash, Bengali) is a setting. Every user-facing string goes through `t()` / `tn()` from `src/i18n` (`const { t, tn } = useI18n()`), including `aria-label`, `placeholder` and `title`. English text is the key. Text kept in a table and translated where it's shown is wrapped in `msg('…')` so the extractor finds it. Run `npm run i18n:extract` after changing UI text and commit `src/i18n/strings.json` (CI checks it); it also prints what `src/i18n/bn.json` is missing, so add the Bengali too. Check new screens with `?lang=en-XA`. Layout uses logical utilities only (`ms-`, `ps-`, `start-`, `text-start`, `border-s`, `rounded-s`, never `ml-`/`pl-`/`left-`/`text-left`); check right-to-left with `?lang=en-XB`.

## Conventions
- **Logging:** never `print`. Use `logger = logging.getLogger(__name__)`; pass structured data as `extra={"fields": {...}}`. For unexpected errors: `logger.exception(...)` then `HTTPException(500, detail=internal_error_detail())`. Never put exception text or secrets in a response or a log message.
- **Backend:** routers stay thin; shared logic goes in `crud.py`; Pydantic schemas live in `schemas.py`; constants (roles, event types, submit reasons) live in `models.py`. Return clear `detail` messages; the frontend shows them via `errorMessage(err)`.
- **Frontend:** use the components in `src/components/ui.js` and the theme tokens (`bg-surface`, `text-muted`, `border-line`, `brand`, `danger`…). Don't add new colors or one-off CSS. Write Tailwind classes literally; never build them from template strings. Icons come from `react-icons/lu`. Put signed-in pages inside `AppShell`.
- **Copy and tone:** plain, specific, sentence case. Don't promise that cheating is impossible.
- **Comments:** only when the *why* isn't obvious.
- **Commits:** small and focused. The message explains why. Run both test suites first.

## Gotchas
- CI (`.github/workflows/ci.yml`) is the gate: SQLite + PostgreSQL tests, migrations (`alembic check` fails if models and migrations differ), frontend build, Semgrep with `--error`, Docker stack health. Run `TEST_DATABASE_URL=postgresql+psycopg://... pytest` to reproduce the Postgres job locally.
- Backend tests use in-memory SQLite, not Postgres. Test anything Postgres-specific (JSON queries, constraints, migrations) against a real database too.
- SQLite gives a column declared `UUID` numeric affinity, so an id whose hex reads as a number (`1234…e5678`) would be stored as a float and fail on read, about once in a million ids. `tests/conftest.py` makes SQLite create UUID columns as `CHAR(32)`. Don't remove it.
- `frontend/package.json` `jest.moduleNameMapper` and the `TextEncoder` polyfill in `setupTests.js` are required for React Router 7 under CRA's Jest. Don't remove them.
- Image answers are currently `data:` URLs inside `answers.answer_data` (2 MB client limit). Moving them to object storage is on the roadmap. Don't build new features on top of inline storage.
- Tags go through `crud.normalize_tags` (import and `create_question`). Filter tags with `.contains(json.dumps(tag), autoescape=True)` on the JSON text: non-ASCII is stored as `\u` escapes, and without `autoescape` PostgreSQL's `LIKE` treats `\` as an escape character (and `_`/`%` as wildcards) while SQLite doesn't.
- The organization is chosen on the client and sent as the `X-Organization-Id` header (set in `src/api.js` from `localStorage.organizationId`).
- A wide table scrolls inside `<div className="relative overflow-x-auto">`. Without `relative`, absolutely positioned children (an `sr-only` label in the last column) escape the scroll box and make the whole page scroll sideways (AC19). A menu opened from a table row must not be clipped by that box either: the Exams row menu is `fixed`, placed from its button (`ExamMenu`).

## Keep the docs current
When you finish a task, tick it in `docs/06-IMPLEMENTATION-PLAN.md`. Update `02-TRD.md` (architecture, API, key decisions), `03-APP-FLOW.md` (screens, routes) and `05-BACKEND-SCHEMA.md` (tables, permissions) when you change them. Record unresolved issues under "Open issues" in the plan.
