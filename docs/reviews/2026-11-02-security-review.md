# Security review (task 5.1)

**Date:** 2026-11-02. **Scope:** the API (88 endpoints), the web app and every dependency, on branch `milestone-1`.

**Method:**
1. Listed every endpoint from the OpenAPI schema and the guard each one uses.
2. Wrote tests for tenant isolation and answer secrecy, then broke the code on purpose to prove the tests catch it.
3. Audited dependencies with `pip-audit` and `npm audit`.
4. Read the code for sign-in, sessions, passwords, uploads and roles.
5. Ran Semgrep, Nuclei and a ZAP quick scan, on localhost only.

## Results against the definition of done

| Check | Result |
|---|---|
| Tenant isolation for every endpoint | **Holds.** `tests/test_tenant_isolation.py` has a case for each of the 71 organization-scoped endpoints, covering seven things (listed below). Breaking isolation on purpose made the tests fail (also below). No isolation bug was found. |
| No answer keys in candidate payloads | **Holds.** `tests/test_answer_secrecy.py` sits four exams as a candidate and searches every response (details below). It found nothing. When I added the key, or the grader notes, to the candidate payload, the tests failed. |
| Dependency audit clean | **Clean for everything that runs in production.** Backend: `pip-audit` reports no known vulnerabilities after the change below. Frontend: `npm audit --omit=dev` reports 0. Build tooling has open advisories (see Open). |

**What the isolation test covers.** For each endpoint:
- Organization B's staff and candidates use A's ids and get 403 or 404. B's lists show nothing of A.
- Naming organization A in the header without belonging to it gives 403.
- Each role is refused what it may not do.
- A candidate can't reach a classmate's attempt.
- B's own exams, groups, imports and papers can't point at A's rows.
- Afterwards, every row of A is unchanged, and no email has gone to A's people.
- A new endpoint without a case fails `test_every_endpoint_is_covered`.

**How the isolation tests were checked.** Two deliberate breaks, both caught:
- Removing the organization check from the exam lookup failed two tests.
- Removing the ownership check from one candidate endpoint failed three tests.

**What the secrecy test searches.** The four exams:
- one with every question type;
- one with a time limit per question;
- one with timed sections;
- one whose results are held for release, checked after it closes.

In every response it looks for:
- a filled-in `correct_answers` or `is_correct`;
- the key's values;
- an ordering question in its stored order, which is its answer;
- the staff-only grader notes.

## Fixed

| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | The API accepted any `SECRET_KEY`, including the 9-character `change-me` from `.env.example`. Tokens are HMAC-SHA256, so a short key can be guessed offline from one token. Then any account, owners included, can be forged | High | The API refuses to start with a key under 32 characters (RFC 7518 §3.2). `.env.example` no longer ships a value, and CI and the documented test commands use long dummy keys. Test: `test_secret_key.py` |
| 2 | Changing or resetting a password didn't sign anyone out, and `POST /token/refresh` renews any valid token. So a stolen token outlived the password forever | High | `users.tokens_valid_after` (migration 0021) is set by a password change or reset. Tokens carry `iat` to the microsecond, and older ones are refused, refreshes included. The Account page keeps its own session with the fresh token it gets back, and says other devices were signed out. Tokens issued before this release keep working until the account's next password change. Test: `test_sessions.py` |
| 3 | The 6-character password rule existed only in the browser. Signup, organization signup and change-password accepted any password through the API, even an empty one | Medium | One server-side rule, `schemas.Password` (6–200 characters), on all four paths |
| 4 | Wrong current passwords in Account settings were unlimited. Someone holding a stolen session could guess the password, change it and keep the account | Medium | Limited to 10 per 15 minutes per user, then 429 |
| 5 | An answer had no size limit on the server. The exam page stops photos at 2 MB, but the API took anything a candidate token sent | Medium | `AnswerCreate` refuses answers over 3 MiB of JSON (a 2 MB photo is about 2.7 MB as a `data:` URL) |
| 6 | `PUT /profile/student` and `POST /profile/change-password` took untyped bodies. Other types (a date of birth as text, an object for a name) caused 500s instead of clear errors | Low | Typed `ProfileUpdate` and `PasswordChange` schemas. Bad values get 422, and fields left out stay as they are |
| 7 | `python-jose` 3.5.0 (CVE-2026-85394, an incomplete fix of CVE-2024-33663), `ecdsa` 0.19.2 (CVE-2024-23342, never to be fixed) and `pyasn1` 0.6.4 (four CVEs). None was exploitable here: we sign HS256 with an explicit algorithm list and never sign with ECDSA | Low | Replaced `python-jose` with PyJWT 2.15, which removes all three. Existing tokens stay valid |
| 8 | The browser bundle shipped `axios` 1.13.2 and `react-router-dom` 7.9.6, both with high advisories | Medium | Updated to 1.21.0 and 7.18.5 (semver-compatible). CRA's build and test tooling moved to `devDependencies`, so `npm audit --omit=dev` now measures only what ships |
| 9 | Found during 5.2: the candidate's exam list, results and graded results carried the email of the staff member who published the exam. The app never showed it, but any candidate could read it | Low | Removed from all three; `test_answer_secrecy.py` now checks that no staff email reaches a candidate |

## Checked, nothing to change

- **Roles:** only owners can grant, change or remove the owner role, and an organization always keeps at least one owner.
- **Image answers:** staff screens show only `data:image/` URLs, inside `<img>`, which can't run script.
- **Rendering:** there is no `dangerouslySetInnerHTML` in the app, and KaTeX runs with `trust: false`.
- **SQL:** no raw SQL is built from input; the only `text()` is the health check's `SELECT 1`.
- **CORS:** only the configured origins are allowed.
- **Sign-in:** errors don't reveal which emails exist, reset requests always get the same answer, and failures are counted for unknown emails too.
- **Bulk question delete:** it skips ids from other organizations; the isolation test confirms A's questions are untouched.

## Open (recommended, not done)

1. **The token lives in `localStorage`** (known gap). An XSS bug could read it; the CSP limits that. Moving to an httpOnly cookie session would close it, and refreshes would then work as true revocable sessions.
2. **Backend requirements aren't pinned.** Every build installs the latest releases, so builds aren't reproducible, and a compromised release would be pulled in automatically. Pin with hashes (for example `pip-compile --generate-hashes`), and pin the Docker base images, before the pilot.
3. **CRA's build tooling has 73 advisories** (13 high: svgo, workbox, webpack-dev-server, resolve-url-loader's old PostCSS, jest 27). None of it reaches users. Only moving off CRA (to Vite, already noted in the TRD) fixes them; `npm audit fix --force` would install a broken `react-scripts@0.0.0`.
4. ~~**Password minimum.**~~ Raised from 6 to 8 characters (NIST SP 800-63B), owner's decision 2026-11-04. Existing passwords still work; the rule applies to new ones.
5. **`passlib` is unmaintained** (last release 2020). It works today; plan a move to `pwdlib` or `argon2-cffi`.
6. **Rate limits are per process, and there's no audit log** (both known). Needed before running more than one API instance, and for compliance work.

## Scans

| Tool | Target | Result |
|---|---|---|
| Semgrep (`p/python`, `p/fastapi`, `p/javascript`, `p/react`, `p/secrets`, `p/security-audit`) | backend and frontend source | 0 findings |
| Nuclei | `http://localhost:8000`, `http://localhost:3000` | 0 findings |
| ZAP quick scan | `http://localhost:8000` | 0 alerts |
| pip-audit | backend venv, and a fresh install of `requirements.txt` | No known vulnerabilities |
| npm audit `--omit=dev` | frontend | 0 vulnerabilities |
