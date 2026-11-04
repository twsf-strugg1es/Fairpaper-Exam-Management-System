# Fairpaper

[![CI](https://github.com/twsf-strugg1es/Fairpaper-Exam-Management-System/actions/workflows/ci.yml/badge.svg)](https://github.com/twsf-strugg1es/Fairpaper-Exam-Management-System/actions/workflows/ci.yml)

An online exam platform for schools, coaching centers and hiring teams. Each organization runs its own question bank, exams, students and results. Students take timed exams that save as they go, and questions with a set answer (choice, true or false, fill in the blank, numbers, matching, ordering) are graded automatically. Built for a global audience, launching in Bangladesh first.

FastAPI + PostgreSQL backend, React + Tailwind frontend.

**Docs:** [PRD](docs/01-PRD.md) · [TRD](docs/02-TRD.md) · [App flow](docs/03-APP-FLOW.md) · [UI/UX brief](docs/04-UI-UX-BRIEF.md) · [Backend schema](docs/05-BACKEND-SCHEMA.md) · [Implementation plan](docs/06-IMPLEMENTATION-PLAN.md) · [Guide for coding agents](docs/AGENTS.md)

---

## Screenshots

### 1. Student Exam Interface
Clean, paper-styled exam experience with lettered answer bubbles, live countdown timer, bubble question navigation map, and violation tracking.
![Student Exam Interface](docs/screenshots/01-exam-interface.png)

### 2. Organization & Exam Management Dashboard
Centralized register for examiners and admins to monitor live, scheduled, and closed exams with configurable protections (`FULLSCREEN`, `SHUFFLE`, `VIOLATION LIMIT`).
![Exams Dashboard](docs/screenshots/02-exams-dashboard.png)

### 3. Anti-Cheating & Integrity Protections
Browser lockdown that detects and logs tab-switching, prevents copy/paste, and records time-away violations without making false accusations.
![Anti-Cheating & Integrity](docs/screenshots/04-anti-cheating-integrity.png)

### 4. Interactive Landing Page
Pre-launch showcase featuring live proctoring demonstrations and Paige, the Fairpaper mascot.
![Landing Hero](docs/screenshots/03-landing-hero.png)

### 5. Launch Waitlist
Integrated waitlist registration with honeypot bot filtering, connected directly to open-source PostgreSQL.
![Launch Waitlist](docs/screenshots/05-waitlist-page.png)

---

## Features

**Organizations and people**
- Any number of organizations, each with its own data
- Roles per organization: owner, admin, examiner (questions, exams, grading), candidate
- One account can belong to several organizations
- Groups (batches, classes, hiring rounds) decide who sees which exam
- Students join with an organization or group join code

**Exams and integrity**
- Question bank with Excel import: single choice, multiple choice, written text, image upload
- Scheduled exams with a window and a duration; answers save automatically and the exam resumes after a reload
- Question and option order shuffled per student, stable on reload
- Fullscreen required; leaving the tab, window or app is recorded as a violation and hides the questions
- Copy, paste, right-click and common shortcuts are blocked and flagged
- Optional automatic submission after a set number of violations, enforced by the server
- Integrity report per attempt: risk level, time away, event timeline
- One attempt per student per exam

**Grading and results**
- Choice questions graded on submit; written and image answers graded by staff
- Results for staff (per exam) and for students (correct answers shown only after the exam closes)

A browser can't physically stop someone from using another device. Fairpaper detects, deters and records; it doesn't promise that cheating is impossible.

## Requirements

- Python 3.10+
- Node.js 20
- PostgreSQL 14+ (16 recommended)
- Git

Docker is optional (see below). On a PC with 8 GB of RAM, the native setup is lighter.

## Setup (native)

### 1. Database

Install PostgreSQL and create the database. On Windows:

```bash
winget install -e --id PostgreSQL.PostgreSQL.16
```

Then create the database (using the `postgres` password you set during install):

```bash
psql -U postgres -c "CREATE DATABASE online_exam_system;"
```

### 2. Backend

```bash
cd backend
cp .env.example .env          # then edit DATABASE_URL and SECRET_KEY
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # creates or updates the tables; run again after every pull
python create_admin.py        # demo organization + owner; prints a random password once
python -m uvicorn app.main:app --reload --port 8000
```

- Generate a `SECRET_KEY` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- API docs: http://localhost:8000/docs · Health: http://localhost:8000/health
- To choose your own owner details: `python create_admin.py you@example.com yourpassword "Your School"`. New organizations can also sign up from the app.
- **Upgrading a database from before organizations existed?** `alembic upgrade head` keeps your data and moves it into a "Default Organization". Back up first.

### 3. Frontend

In a second terminal:

```bash
cd frontend
npm ci
npm start                     # http://localhost:3000
```

The frontend calls the API at `http://localhost:8000`. For another address, copy `frontend/.env.example` to `frontend/.env` and set `REACT_APP_API_URL` before `npm start` or `npm run build`.

### 4. Log in

Use `admin@example.com` and the password `create_admin.py` printed. Students sign up themselves and enter the join code it printed, or a group's code from Organization → Invite.

## Running with Docker (optional)

Docker needs a few GB of RAM. CI builds and checks the images on every push, so you don't need Docker to develop.

```bash
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))") docker compose up --build
docker compose exec api python create_admin.py
```

- Web: http://localhost:3000 · API: http://localhost:8000
- The API container runs `alembic upgrade head` before it starts.
- Data lives in the `db-data` volume; `docker compose down -v` deletes it.

## Tests

```bash
# backend (from backend/, venv active)
DATABASE_URL=sqlite:///:memory: SECRET_KEY=tests-only-key-never-use-it-anywhere-else python -m pytest tests/ -q

# same suite against PostgreSQL
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/tests DATABASE_URL=sqlite:///:memory: SECRET_KEY=tests-only-key-never-use-it-anywhere-else python -m pytest tests/ -q

# frontend (from frontend/)
npm test -- --watchAll=false
npm run build
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs all of these, plus migration checks, a Semgrep security scan, and a Docker build with health checks.

## Excel import

Download the template from Question bank → Import, or use `sample_questions.xlsx`.

| Column | Required | Example |
|---|---|---|
| `title` | yes | `What is 2 + 2?` |
| `complexity` | yes | `easy`, `medium` or `hard` |
| `type` | yes | `single_choice`, `multi_choice`, `text` or `image_upload` |
| `options` | for choice types | `["1", "2", "3", "4"]` |
| `correct_answers` | for choice types | `["4"]` |
| `max_score` | no (default 1) | `1` |
| `tags` | no | `math, arithmetic` |

Single choice needs the exact answer. Multiple choice needs all correct options and no wrong ones. Text and image answers are graded by staff.

## Project structure

```
backend/
  app/
    main.py             app, middleware, /health
    models.py           SQLAlchemy models and constants (roles, event types)
    schemas.py          Pydantic request/response models
    crud.py             business logic: grading, shuffling, deadlines, integrity
    permissions.py      organization membership and role checks
    security.py         passwords and JWT
    logging_config.py   JSON logs with request IDs
    database.py         engine and session
    routers/            auth, organizations, admin (staff), student, profile
  migrations/versions/  Alembic migrations (0001 onwards)
  tests/
  create_admin.py       seed an organization and owner
  Dockerfile, docker-entrypoint.sh
frontend/
  src/
    App.js              routes and role guards
    api.js              axios instance (auth + organization headers)
    components/         ui.js (design system), AppShell, AuthLayout
    context/            AuthContext, ThemeContext
    hooks/              useExamIntegrity
    pages/              one file per screen
    utils.js            formatting helpers
  Dockerfile, nginx.conf
docs/                   PRD, TRD, app flow, UI/UX brief, schema, plan, agent guide
docker-compose.yml
.github/workflows/ci.yml
```

## Troubleshooting

- **`DATABASE_URL environment variable is not set`**: create `backend/.env` from `.env.example`, or set the variables in your shell.
- **Port already in use**: start the API on another port (`--port 8001`) and set `REACT_APP_API_URL=http://localhost:8001` in `frontend/.env`.
- **`npm ci` fails**: check `node --version` is 20, delete `node_modules`, and run `npm ci` again. Don't delete `package-lock.json`.
- **`psql` not found on Windows**: it's in `C:\Program Files\PostgreSQL\16\bin`; add that folder to PATH or use the full path.
