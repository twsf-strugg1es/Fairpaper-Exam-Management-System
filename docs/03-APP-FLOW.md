# 3. App Flow: Fairpaper

Purpose: show each screen, user path, and the result of each tap or click.
Status: living document · Last updated 2026-10-12 · Routes are defined in `frontend/src/App.js` (source of truth). *(planned)* marks screens that don't exist yet.

## Entry points

| Entry | URL | Who |
|---|---|---|
| *(planned)* Landing page | `/` (signed out) | Institutions evaluating Fairpaper; anyone on a phone |
| Waitlist | `/waitlist` (linked from every landing-page call to action until launch; `?from=<label>` records which one, e.g. `?from=instagram`) | Anyone who wants to hear when Fairpaper launches |
| Direct visit / bookmark | `/` → redirects by state (see Navigation rules) | Everyone |
| Login | `/login` | Returning users |
| Student signup link with code | `/signup?code=K7M2QX9P` (code prefilled, upper-cased) | Candidates invited by an institution |
| Organization signup | `/signup/organization` | New institutions |
| Password reset email | `/reset-password/:token` → set a new password → `/login` with a notice | Anyone who asked for a reset |
| Confirmation email | `/verify-email/:token` → "confirmed" → continue (signed in) or log in | New accounts |
| Invite email link | `/invite/:token` → "Welcome to Fairpaper", set a password → `/login` with a notice → the organization's dashboard | Bulk-imported candidates and invited staff (phone-friendly) |
| *(planned)* Password reset link | `/reset-password/:token` | Anyone who forgot their password |
| *(planned)* Notification links | `/exam/:id` from email/SMS | Candidates |

## Screen inventory

| Screen | Route | Purpose | Data required | Access |
|---|---|---|---|---|
| Login | `/login` | Sign in | — | Signed out |
| Student signup | `/signup` | Create a candidate account, optionally with a join code | — | Signed out |
| Organization signup | `/signup/organization` | Create an organization + owner account | — | Anyone |
| Forgot password | `/forgot-password` | Ask for a reset link (same answer for every email) | `/password-reset/request` | Signed out |
| Reset password | `/reset-password/:token` | Set a new password from the emailed link | `/password-reset/confirm` | Anyone with a link |
| Confirm email | `/verify-email/:token` | Confirms the address from the signup email | `/verify-email` | Anyone with a link |
| Organizations | `/organizations` | Pick the current organization, join with a code, create an organization | `/me` memberships | Signed in |
| Account | `/profile` | Name, gender, language (or the organization's default), password, list of organizations | `/profile/student` | Any member |
| **Staff** | | | | |
| Exams | `/admin-exams` | List exams with status (Draft/Scheduled/Live/Closed) and protections; publish/unpublish/delete | `/admin/exams/` | Staff |
| New exam | `/admin-exams/new` | Details, schedule, **Timing** (4.11b: *One timer for the whole exam* or *A time for each question*; per question, each chosen question gets a seconds box with its own default as the hint, and "Same time for every chosen question: [30] s **Apply**"; random questions use their bank time), **Sections** (4.10: **Split into sections** makes two; each has a title, optional minutes and instructions, a count of its questions, up/down and remove (its questions move to the section before); **Add a section**, **Back to one part**; the card explains that timed sections are taken in order and lock behind the student, and warns when timed sections add up to more than the exam's duration), questions (each chosen one gets a marks box, prefilled from the bank; changing it affects only this exam), **Random questions** under the picker (rules: "Draw [5] random [easy] questions tagged [physics] worth [1] pts each", a live "N match" count that turns red when the bank can't fill the rule, **Add a rule**; the badge shows questions per student and total points), groups, integrity settings, **Students see their results**: right after they submit / when the exam closes / when I release them. Until then students see "Results aren't released yet" on the finish screen and the results pages, and their averages leave that exam out | `/admin/questions/`, `/org/groups` | Staff |
| New question | `/admin-questions/new` (Question bank → New question) | Question, staff-only notes, type, difficulty, points, **Seconds** (its time when an exam gives each question its own; empty: no limit), then the answer key for the type: **choice**, 2–10 lettered options with the correct bubble(s) marked · **true or false**, which one is right · **fill in the blank**, `___` in the question for each blank (**Insert a blank** puts one at the cursor) and one or more accepted answers per blank · **number**, the answer and a ± margin ("Counts as correct: 9.75 to 9.85") · **matching**, 2–10 pairs plus optional extra matches · **ordering**, 2–10 items in the correct order, with up/down arrows · **written** and **image**, a note that an examiner grades them. The checks show by the Save button before anything is sent. Tags as chips with suggestions from the bank | `POST /admin/questions/` | Staff |
| Edit question | `/admin-questions/:id/edit` (pencil in the bank) | Same form. A question students have met shows why it's locked and a "Duplicate and edit the copy" button | `GET`/`PUT /admin/questions/{id}`, `POST …/duplicate` | Staff |
| Edit exam | `/admin-exams/:id/edit` (row menu → Edit, shown only while editable) | Same form, one "Save changes" button; a published exam stays published. Locked exams show the reason and a disabled form | `GET`/`PUT /admin/exams/{id}` | Staff |
| Exam results | `/admin-exams/:examId` | **Add time** on attempts in progress (dialog: +5/+10/+15/+30 min, or the total; toast "Sumaiya Akter now has until 10:55 AM"), "+10 min extra" under their status; an **Extra time** card (4.11): everyone with extra time ("+5 min · Not started", "+10 min · Writing · until 10:55 AM", "Submitted"), **Change**, **Give a student extra time** (choose a student, then minutes); release bar (exams not set to "Right after they submit"): "Results hidden" / "Results released" badge, **Release results** / **Hide results again**; stats, attempts with score/risk, filters, links to report and grading | `/admin/exams/`, `/admin/exams/:id/attempts` | Staff |
| Integrity report | `/admin-integrity/:attemptId` | Risk, violations, flags, time away, event timeline | `/admin/attempts/:id/integrity` | Staff |
| Grade answers | `/admin-evaluate-answers/:attemptId` | One student's written and image answers, each with the marks control (below) | `/admin/evaluations/attempts/:id`, `POST /admin/evaluations/answers/{id}/submit` | Staff |
| Question analysis | `/admin-exams/:examId/analysis` (Exam results → **Question analysis**, once someone has submitted) | Submitted, average, median, highest and lowest; **How the scores spread** (columns per 10 % band, hover for the count, **Show as a table**); **By topic** (share of marks per tag, hardest first); **Questions**: difficulty bar and %, discrimination (+1.00 … −1.00), *Look at* flags (Very hard, Very easy, Weak discrimination, Check the key), **Options** opens how many chose each option (the correct one marked), sort by paper order, hardest first or lowest discrimination first. Notes when fewer than 5 papers are in ("Discrimination needs at least 5 submitted papers…") or written answers wait for grading. Empty: "Nothing to analyse yet" | `GET /admin/exams/{id}/analytics` | Staff |
| Grade by question | `/admin-exams/:examId/grade/:questionId` (Exam results → **Grade by question**; without a question it opens the first with answers left and puts it in the address) | Questions to grade on the side ("12 of 50 graded" with a bar), and every submitted answer to the chosen one, in the order students submitted, with the question's staff notes as grading notes. Marks control per answer: **0**, half and full marks save with one click; a box takes any mark to two decimals ("2,5" works) and saves on Enter, which also moves to the next answer, or when it loses focus; a comment ≤ 100 chars; "Saved" / "Not graded yet"; "Give a mark from 0 to 4." for anything outside. **Hide names while grading** (answers become "Answer 1, 2…"), **Show only answers not graded yet**, "3 students left it blank: 0 marks, nothing to grade", **Next question** | `GET /admin/exams/{id}/grading`, `GET /admin/exams/{id}/grading/{question_id}`, `POST /admin/evaluations/answers/{id}/submit` | Staff |
| Question bank | `/admin-questions` | Search/filter, view, import from Excel, download template, bulk delete | `/admin/questions/` | Staff |
| Students | `/admin-students` | List and search candidates with performance; remove | `/admin/students/` | Staff |
| Organization | `/admin-organization` | Tabs: Invite & groups · Students · Staff · Settings (name; region and language: timezone, default language, country, currency) | `/org`, `/org/groups`, `/org/members` | Managers |
| **Candidate** | | | | |
| Exams (dashboard) | `/student-account` | Sections: Continue where you left off · Open now · Upcoming · Done | `/student/exams/`, `/student/unfinished-attempts/` | Candidate |
| Exam | `/exam/:id`, `/exam/resume/:attemptId` | Rules → take exam → finished | start/resume, answers, events | Candidate |
| Results list | `/student-exams` | Submitted exams with scores | `/student/completed-exams/` | Candidate |
| Result detail | `/exam-results/:attemptId` | Per-question breakdown, grader comments, correct answers once closed | `/student/attempts/:id/evaluated-results` | Candidate |
| *(planned)* Landing | `/` | Product story, features, video, pricing placeholder, calls to action | — | Signed out |
| Waitlist | `/waitlist` | Email field, one-line consent note, **Join the waitlist**; inline error for a malformed email; success state "You're on the list" (the same whether the email was new or already listed) | `POST /waitlist` | Anyone |
| Waitlist unsubscribe | `/waitlist/unsubscribe/:token` (link in every waitlist email) | One **Unsubscribe** button (a press, not just a visit, so mail scanners can't unsubscribe anyone) → "You're off the list"; "Join again" link | `POST /waitlist/unsubscribe` | Anyone |
| Bulk import students | Organization → Students → **Import students** (dialog) | Choose a CSV/XLSX and optional groups → **Check the list** (counts: new / with an account / already here; skipped rows with reasons) → **Add N students** → report | `/org/students/import/preview`, `/org/students/import` | Managers |
| Merit list | card under the attempts on Exam results | Rank ("=" when tied), student, score with %, time taken; "Provisional" while the exam is open. Exam form: **Show students their rank** puts "Rank 3 of 40" (or "Joint 3 of 40") on the student's result page | `/admin/exams/:id/merit` | Staff |
| Export to Excel | Exam results → **Export to Excel** (next to the title) | Downloads `<exam title> results.xlsx`: Results (rank, name, email, score, out of, percent, time taken, started, submitted, ended by, violations, flags, time away, risk), Marks by question ("Not graded" where a written answer waits), Questions, Exam. Times in the organization's timezone | `GET /admin/exams/{id}/export.xlsx` | Staff |
| Result cards | Exam results → **Result cards** (once someone has submitted), or **Card** on a student's row | `/admin-exams/:examId/cards` (`?attempt=` for one): one A4 card per submitted student (organization, exam, name, score and percent, rank when the exam shows ranks, time taken, submitted, marks by question, a signature line); **Print or save as PDF** opens the browser's print dialog, one card per page. A note (not printed) when results aren't released yet. Outside the app shell so only the cards print | `GET /admin/exams/{id}/result-cards` | Staff |

## Desktop only (version one)

Policy: see PRD "Platform: desktop web app".

| Route | Narrower than 1024 px |
|---|---|
| `/` landing page *(planned)* | Fully responsive |
| `/login`, `/signup`, `/signup/organization`, `/waitlist`, `/forgot-password`, `/reset-password/:token`, `/verify-email/:token`, `/invite/:token`, `/waitlist/unsubscribe/:token` | Work (phone-friendly; emailed links are often opened on a phone) |
| Every other route | `DesktopOnly` screen: logo, "Fairpaper works on a computer", one line on why (exams need a full browser), what to open, and **Sign out** |

- A `matchMedia("(min-width: 1024px)")` check, re-evaluated on resize, so widening a window or rotating a tablet lets the user straight in.
- A running exam is never interrupted by a resize: the attempt keeps running and the screen asks to widen the window. Leaving fullscreen is already recorded.

## Primary journeys

**J1. Institution onboarding (owner)**
`/signup/organization` → submit name, email, password → automatic login → `/admin-exams` (empty state "No exams yet") → sidebar **Organization** → copy join code or signup link → share with students.

**J2. Candidate onboarding**
Open `/signup?code=XXXX` → fill in name, email, password (code prefilled) → automatic login → organization selected → `/student-account`.
Without a code: signup → `/organizations` → enter a join code → `/student-account`.

**J3. Create and publish an exam (examiner)**
`/admin-exams` → **New exam** → fill in title, opens/closes, duration → pick questions (searchable) → pick groups (none = everyone) → review integrity switches (all on by default) and the optional violation limit → **Publish** (or **Save draft**) → back to `/admin-exams` with status Scheduled or Live.

**J4. Take an exam (candidate)** ← the critical path
`/student-account` → **Open now** → **Start** → `/exam/:id` **Rules** screen (duration, question count, protections) → **Start exam** (enters fullscreen if required; the timer starts on the server now) → answer questions (with sections, the section's title and instructions sit above each of its questions and the question map groups questions by section; choice and true or false: click, or press 1–9; fill in the blank: the boxes sit in the sentence; number: one box that says how it was read, "Read as 9.81"; matching: a dropdown per item, and a match picked twice moves; ordering: up/down arrows, first at the top, nothing saved until the first move); the navigator shows answered/flagged → **Submit** → confirm dialog "Submit your exam?" → **Finished** screen (score for objective questions, or "Awaiting grading").

**J4c. Take an exam in timed sections (candidate, 4.10)**
Rules screen lists the sections ("01 Part A: mechanics · 2 questions · 10 min") and says they're taken in order, one at a time → **Start exam** → only the open section's questions; its own countdown sits next to the exam's ("PART A: MECHANICS 9:41"); the question map shows finished sections as "Finished" and upcoming ones with their question count and time → **Finish section** → "Finish Part A? You can't come back to this section." (answered count, time left) → the next section opens with its full time and a notice "Part B has started" → … → in the last section **Submit exam** as usual. When a section's time runs out, pending answers are sent, the next section opens and the notice says "Time's up for Part A"; when the last one's runs out, the exam is submitted (time up). Reloading returns to the open section with the server's time left.

**J4b. Take a per-question timed exam (candidate, 4.11b)**
Rules screen also says "Each question has its own time. When it runs out, or when you press Next, the next question opens and you can't go back." → **Start exam** → one question at a time with its own countdown next to its number (warn at 10 s, red at 5 s; none for a question without a limit) and the exam's timer in the header → answer → **Next question** (unanswered: "Move on without answering? You can't come back to this question." **Stay on it** / **Next question**), or the countdown ends and the next question opens by itself → on the last question **Submit exam**; if its time runs out the exam is submitted. The side shows "2 of 3 question" and a map: done (grey), open now, still to come; nothing is clickable and there's no flagging or arrow-key moving. A reload returns to the open question with the time it has left.

**J4d. Extra time (examiner, 4.11)**
Before the exam: Exam results → **Extra time** → **Give a student extra time** → choose the student → **Choose minutes** → +5 → **Save**; their rules screen then says "Time 60 min + 5 min extra" and their timer includes it. During the exam: the attempt's **Add time** → +10 → **Save**; the student's page picks it up within a minute (or the moment their old time runs out) and says "You have more time: your examiner gave you extra time, 10 minutes in all".

**J5. Review and grade (examiner)**
`/admin-exams` → click an exam → `/admin-exams/:examId` → tab **Needs review** → risk badge → **Report** (`/admin-integrity/:attemptId`) to see the timeline → back → **Grade** (`/admin-evaluate-answers/:attemptId`) → a mark per answer (0, half or full in one click, or any mark to two decimals) and a comment → the score updates. Or **Grade by question** (`/admin-exams/:examId/grade`) to mark one question for every student.

**J6. See results (candidate)**
Sidebar **Results** → `/student-exams` → click an exam → `/exam-results/:attemptId`.

## Alternate journeys

| Journey | Path |
|---|---|
| Resume after a reload or crash | `/student-account` → **Continue where you left off** → `/exam/resume/:attemptId` → warning "Your timer has been running" → answers restored → continue |
| Resume after the deadline | Resume → the server submits with reason `time_up` → Finished screen |
| Leave the exam (click outside the window, tab/app switch, fullscreen exit) | The exam blurs and its question text leaves the page → violation recorded → coming back isn't enough: click anywhere on the page or press **Return to the exam** (re-enters fullscreen when required) → the violation chip updates |
| Violation limit reached | The server submits with reason `violations` → Finished screen explaining why |
| Time runs out | The page submits automatically → recorded as `time_up` |
| Cancel submit | The confirm dialog's **Cancel** returns to the exam; nothing changes |
| Unpublish | Exam menu → **Unpublish** → back to Draft; candidates no longer see it |
| Delete exam / questions | Menu → **Delete** → danger confirm dialog → removed |
| Excel import | Question bank → **Import** → choose file → **Preview** (every row checked the way the editor checks it; the first bad row is named, "Row 7: Add at least 2 items to put in order.") → **Import** (all rows or none) → list refreshes. The template has one sample row per type, and imports as it is |
| Switch organization | Sidebar organization button → `/organizations` → pick one → that organization's home |
| Join another organization | `/organizations` → enter code → it becomes available in the switcher |
| Add staff | Organization → Staff → email, optional name, role → **Add**. With an account: added, and emailed. Without one: account created, invite emailed, row shows **Invite pending** with **Resend invite** (older links stop working) until they set a password |
| Change role / remove member | Organization → Staff → role select / remove (only owners can touch owners; the last owner can't be removed) |
| Regenerate a join code | Organization → Invite → **New code** → confirm → the old code stops working |

## Action specification (key actions)

| Action | Trigger | Validation | Loading | Success | Error | Next |
|---|---|---|---|---|---|---|
| Log in | Submit on `/login` | Email format, required fields | Button spinner | Token stored, `/me` loaded | Inline alert "Incorrect username or password" | `/` → role home |
| Student signup | Submit on `/signup` | Email, password + confirmation match, valid join code if given | Button spinner | Auto login | Alert with server message (e.g. "Email already registered", invalid code) | `/student-account` or `/organizations` |
| Organization signup | Submit | Organization name 2–120 chars, email, password | Button spinner | Auto login as owner | Alert | `/admin-exams` |
| Join with code | Submit on `/organizations` | Non-empty code | Button spinner | Membership added | Alert "invalid code" | Organization home |
| Create exam | **Publish** / **Save draft** | Title, start < end, duration ≥ 1, ≥ 1 question; warns if window < duration | Button spinner | Exam created (+ published) | Alert with server detail | `/admin-exams` |
| Start exam | **Start exam** on the rules screen | Server: visible, published, inside window, not submitted | Full-page loader | Questions + deadline + saved answers | Error phase with message (not started yet / expired / already submitted) | Running |
| Answer choice | Click an option | Allowed only while running | Silent | Saved immediately | Save error shown (no offline queue yet; see `ExamPage.js`) | Same question |
| Answer text | Type | — | Silent (debounced) | Saved after a pause; flushed on submit | Same as above | — |
| Upload image answer | Choose file | Image type, ≤ 2 MB | Preview | Saved | "File too large" | — |
| Submit exam | Confirm dialog | — | Button spinner; pending saves flushed first | Score / awaiting grading | Alert; can retry. Offline with answers waiting: the dialog closes and an alert says the exam can't be submitted until they reconnect | Finished |
| Lose the connection mid-exam | — (automatic) | — | Header shows "Offline · N answers waiting" and a banner "You're offline. Keep going…"; answers are kept on this computer | Sent on reconnect (or on reopening the exam); header back to "Saved" | Rejected for good (e.g. after time's up): "Not saved" | Running |
| Grade answer | Correct / Incorrect + **Save** | Comment ≤ 100 chars | Button spinner | Progress bar updates | Alert | Next answer |
| Import Excel | **Preview**, then **Import** | `.xlsx/.xls`, required columns | Spinner | Count imported | Per-row errors in the preview | Question list |
| Publish/unpublish/delete exam | Exam menu | Delete needs confirmation | Menu disabled | List refreshes | Alert | `/admin-exams` |

## Navigation rules

- **Root redirect** (`/`): signed out → `/login`; signed in with no organization selected → `/organizations`; staff → `/admin-exams`; candidate → `/student-account`.
- **Guards:** a route for another role redirects to `/` (which then routes correctly). `/login` and `/signup` redirect to `/` when already signed in. Unknown URLs → `/`.
- **Legacy:** `/student-profile` → `/profile`.
- **Layout:** signed-in pages use `AppShell`: a fixed left sidebar on desktop (≥ 1024 px); a top bar with a slide-in menu on phones; the menu closes on navigation.
- **Sidebar:** staff: Exams, Question bank, Students, Organization (managers only), Account. Candidates: Exams, Results, Account. Plus the organization switcher, the theme toggle, and Log out.
- **Exam page:** no sidebar (distraction-free). Browser back during an exam leaves the page; the attempt keeps running and can be resumed from the dashboard.
- **Deep links:** every screen has a stable URL; IDs are UUIDs.

## Empty and blocked states

| Screen | State | What the user sees |
|---|---|---|
| Exams (staff) | No exams | "No exams yet" + **New exam** |
| New exam | Empty question bank | "Your question bank is empty" + link to import |
| Question bank | No questions / no matches | "No questions yet" + Import / "No matching questions" |
| Students (staff) | None / no matches | "No students yet" (share the join code) / "No matching students" |
| Organization | No groups / no students | Explains that students without a group see exams open to everyone / "Share the join code from the Invite tab" |
| Exam results | No attempts / filter empty | "No attempts yet" / "Nothing here" |
| Grade answers | Nothing to grade | "Nothing to grade" |
| Grade by question | No written or image questions / nobody has submitted / everyone left it blank / all graded with the filter on | "Nothing to grade" / "No answers yet" / "Nothing to grade here" / "Every answer to this question is graded" with **Next question** |
| Integrity report | No events | "No events recorded" |
| Candidate dashboard | No exams | "No exams yet" |
| Candidate results | None | "No results yet" |
| Exam | Not started / expired / already submitted / not published | Error phase with the server message and a link back |
| Exam | Away / back but not clicked in / out of fullscreen | The exam blurred behind a card ("You left the exam", violations so far, how many are left); question text replaced by placeholder bars; a click anywhere returns |
| Any | Loading | A skeleton in the page's shape; after 5 s a "connection seems slow" note |
| Any | Load failed | `ErrorState` where the content would be (offline / couldn't reach Fairpaper / our side / not found / no access), **Try again** and a way back; never shown as an empty list |
| Any list | Search or filters match nothing | "Nothing matches “…”", "Did you mean …?" when a word is close, **Clear search** |
| Any | Wrong role | `NoAccess`: who the page is for, who you're signed in as, **Go to my home page**, **Switch organization**. Signed out: to `/login`, then back to the same page |
| Any | Offline | Banner: what's on screen stays, saving waits; "You're back online" afterwards. The exam keeps its own banner and answer queue (3.8) |
| Any | Session ended (idle for 5 min without "keep me signed in", or the server refuses the session) | `/login` says why and that work is saved, keeps the email, and returns to the page after signing in; the exam and question forms offer back their unsaved changes |
| Imports, photo answers | Uploading | Real progress, then "Checking it…" |
| After create / publish / save / export | Success | A toast with the details and a next step |

## First-use journey

- **New institution:** organization signup → empty Exams page → Organization page (copy code, create groups) → Question bank (download template, import) → New exam. The Exams page shows a **Get started** checklist (3.10) until all four steps are done: Invite your students · Put them in groups · Add questions · Create your first exam. Each open step has a button to the right page (the next one is highlighted); examiners see "An admin does this" for the two manager steps. It replaces the "No exams yet" card while it shows, and **×** hides it in that browser for that organization. Data: `GET /org/setup` (staff).
- **New candidate:** signup with code → dashboard. Before their first exam, the **Rules** screen explains each protection in plain words and how violations work, before anything is recorded.
- **New staff member:** an owner/admin adds an existing account by email on Organization → Staff. *(planned)* email invitations for people without an account.
