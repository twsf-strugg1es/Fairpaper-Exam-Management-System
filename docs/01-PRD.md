# 1. Product Requirements Document (PRD): Fairpaper

> Renamed from TestKori to Fairpaper on 2026-10-28.

Purpose: define what the product must do and how success will be measured.
Status: living document · Last updated 2026-10-12 · Related: [TRD](02-TRD.md) · [App Flow](03-APP-FLOW.md) · [UI/UX Brief](04-UI-UX-BRIEF.md) · [Backend Schema](05-BACKEND-SCHEMA.md) · [Implementation Plan](06-IMPLEMENTATION-PLAN.md)

> Feature labels: **[Built]** exists in the code today. **[Planned]** is in the Implementation Plan.

## Product name and one-sentence idea

**Fairpaper** is an online exam platform where schools, coaching centers and hiring teams anywhere in the world run their own fair, auto-graded exams, without an invigilator in the room.

## Target users

| User | Who they are | What they need |
|---|---|---|
| **Organization owner/admin** | Coaching center director, school head, HR lead | A private space for the institution, control over staff and students, results they can trust |
| **Examiner** | Teacher, trainer, recruiter | Build question banks quickly, schedule exams, grade quickly, see who cheated |
| **Candidate** | HSC/admission/BCS student, school student, job applicant (often on a low-end Android phone) | Take exams reliably on a weak connection, clear rules, quick results |

**Market strategy: built for a global audience, launched in Bangladesh first.**
- **Launch market:** Bangladesh, starting with **coaching centers**. When pilot priorities conflict, decide in their favor.
- **Global market (after the pilot):** schools, training providers and hiring teams anywhere, starting with English-speaking and South Asian markets (India, Pakistan, Middle East, UK), then the EU/US once privacy compliance is in place.
- **Rule:** no feature may hardcode Bangladesh-only assumptions (language, currency, phone format, payment method, timezone, exam conventions). Local features like negative marking, merit lists, bKash and Bengali are **organization settings**, not defaults baked into the code.

| Market | Edge against competitors |
|---|---|
| Bangladesh / South Asia | Local fit: negative marking, merit list, bKash/SSLCommerz, Bengali UI, low price, works on cheap phones |
| Global | Strong integrity features at a lower price than Mercer Mettl or ExamSoft; simpler than Moodle; multi-organization accounts |

## Problem and current workaround

- **Problem:** institutions run exams on paper or on generic form tools. Nothing stops tab-switching or answer sharing, examiners get no record of suspicious behavior, and marking, merit lists and result sheets are done by hand.
- **Current workaround:** Google Forms or Microsoft Forms plus Excel for marks; WhatsApp/Facebook groups to distribute links and results; paper model tests for anything that "counts".

## Goal and success measure

**Goal (version one):** one real institution runs its regular exams on Fairpaper without developer help, and pays for it.

| Signal | Target |
|---|---|
| Real exams run by the pilot institution | ≥ 4 exams with ≥ 50 candidates each |
| Lost answers | 0 (hard ceiling: < 0.1% of saved answers) |
| Time from exam close to published objective results | < 10 minutes |
| Candidates who finish without a support request | ≥ 95% |
| Pilot converts to paid | Yes |

## Core features

| # | Feature | User benefit | Priority | Status |
|---|---|---|---|---|
| F1 | Organizations, roles (owner/admin/examiner/candidate), multi-organization accounts | Each institution gets a private space; a student can belong to two centers | P0 | Built |
| F2 | Join codes for the organization and for each group; groups (batches/classes) | Students self-enroll in the right batch | P0 | Built |
| F3 | Question bank: single choice, multiple choice, short/written answer (typed in a text box, graded by staff), image upload; tags, difficulty | Reuse questions across exams | P0 | Built |
| F4 | Excel import with template and preview | Bring existing question sets in minutes | P0 | Built |
| F5 | Exams: schedule window, duration, question selection, target groups, publish/unpublish | Run timed exams for specific batches | P0 | Built (no editing after creation) |
| F6 | Exam taking: auto-save, resume after reload, timer, question navigator, flag for review | Weak connections and accidents don't cost answers | P0 | Built |
| F7 | Integrity: per-candidate shuffling, fullscreen, tab/app-switch detection (the exam blurs, its question text leaves the page, and it stays that way until the candidate clicks back in), copy/paste blocking, violation limit with automatic submission | Deters and records cheating | P0 | Built |
| F8 | Integrity report: risk level, time away, event timeline | Examiner knows whom to review | P0 | Built |
| F9 | Auto-grading (choice questions); manual grading of written and image answers | Marking takes minutes | P0 | Built |
| F10 | Results for examiners (per exam) and for candidates | Everyone sees outcomes | P0 | Built |
| F11 | Single-question create/edit form; edit exam before it opens | Fix a typo without re-importing | P0 | Built (3.2, 3.3) |
| F12 | Password reset, email verification | Users can recover their own accounts | P0 | Built (2.4 reset, 2.5 soft verification) |
| F13 | Bulk candidate import (CSV/XLSX) with invites | Enroll a 200-student batch at once | P0 | Built (3.6) |
| F14 | Email + SMS notifications (exam published, reminder, results) | Students show up on time | P0 | Planned |
| F15 | Negative marking; per-exam marks | Matches admission/BCS-style exams | P1 | Planned |
| F16 | Random question pools by tag/difficulty | Different paper per student, harder to share answers | P1 | Built (4.6): rules on the exam form ("Draw 5 random easy questions tagged physics, worth 1 each"); each attempt draws its own set when it starts and keeps it |
| F17 | Merit list / rank; result publishing control | What coaching centers sell on | P1 | Built (4.3, 4.4) |
| F18 | Export results (XLSX, PDF result cards) | Notice boards, parents, records | P1 | Built (4.5): Excel workbook from Exam results; result cards print one per A4 page, saved as PDF by the browser |
| F19 | More question types (true/false, fill-in-the-blank, numeric, matching, ordering), math (KaTeX), images in questions | Covers science and math subjects | P1 | Question types built (4.7): true or false, fill in the blank (several blanks, several accepted answers each), number with a ± margin, matching (with extra matches), ordering; all graded automatically, in the editor and the Excel import. Math and images: planned (4.8) |
| F20 | Sections, extra time per candidate, offline-tolerant saving, grade-by-question, analytics | Serious exam operations | P1 | Sections built (4.10): parts with their own title, instructions and optional time; timed parts are taken in order and lock behind the student. Grade by question with partial marks built (4.9); offline-tolerant saving built (3.8); extra time and analytics planned |
| F21 | Internationalization: translation-ready UI (English default, Bengali first translation), locale-aware dates and numbers, per-organization language/timezone/currency, right-to-left support | One codebase serves Bangladesh and global customers | P0 (framework) / P1 (languages) | Planned |
| F25 | Clipboard protection during exams: clipboard cleared when the exam starts and each time the candidate returns; every paste route blocked (keys, menu, drag-and-drop, middle-click); attempts flagged; question and option text can't be selected | Text copied before or outside the exam can't be pasted in, and question text can't be copied out or sent to a search or AI menu | P0 | Built (3.11, 3.11b) |
| F26 | Public landing page: product story, features, pricing placeholder, sign-up calls to action; responsive and phone-friendly; restrained scroll effects | Explains Fairpaper to institutions; the only phone experience in v1 | P0 | Planned |
| F27 | Launch waitlist: a public `/waitlist` page (linked from the landing page) where visitors leave their email and get one email when Fairpaper launches | Builds an audience before launch | P0 | Built (3.13); the landing page itself is still a prototype (3.12) |
| F28 | Product video on the landing page: YouTube embed (privacy-enhanced, loads only when played); a styled "video coming soon" placeholder until the owner sets the link | Shows the product in action without slowing the page | P0 | Planned |
| F29 | Per-question time limits: an exam's timing mode is either **whole exam** (today: one duration for the test) or **per question** (each question has its own limit that the teacher sets; MCQ and short answer alike). Per-question mode shows one question at a time, moves on automatically when its time ends, and doesn't allow going back | Matches timed quiz and rapid-fire formats; stops students spending all their time on one question or looking answers up | P1 | Planned |
| F24 | Global readiness: Stripe/Paddle card payments, GDPR tools (data export, deletion, data processing agreement, cookie consent), global SMS (Twilio), optional EU data hosting | Sell outside Bangladesh legally | P3 | Planned |
| F22 | Webcam snapshots + face checks, ID photo, Safe Exam Browser, live proctor dashboard | Higher-stakes exams and hiring | P2 | Planned |
| F23 | Plans, billing (bKash/SSLCommerz), branding, audit log, Google sign-in, paid public mock tests | Revenue and enterprise readiness | P3 | Planned |

## Platform: desktop web app (version one)

**Decision (2026-10-26): version one is a desktop web app. Phones get only the public landing page.**

| Surface | Desktop / laptop (1024 px and wider) | Tablet / phone (narrower) |
|---|---|---|
| Landing page (public) | Yes | Yes, fully responsive |
| Login, signup, join | Yes | Yes, so people can sign up from a link on their phone |
| Everything else: staff screens, candidate dashboard, **taking exams**, results | Yes | No: "Open Fairpaper on a computer" screen |

- The "use a computer" screen says what to do next ("Open Fairpaper on a laptop or desktop and sign in"), keeps the user signed in, and is never a dead end.
- Window width decides, not device sniffing: a 1024 px tablet in landscape counts as a computer.
- **Why:** integrity features (fullscreen, focus tracking, clipboard control, later Safe Exam Browser) work fully only in desktop browsers, and one well-designed layout ships faster than two.
- **Tradeoff, accepted for now:** many Bangladeshi students only own a phone. Pilot customers need computer access (labs, centers, hiring teams). Revisit after the pilot; a mobile candidate experience is planned work, not a non-goal.

**Acceptance:** AC19. Given a browser window 1024 px or wider, every journey in the App Flow works without horizontal scrolling. AC20. Given a phone at 390 px, the landing page, login and signup work fully, and any other route shows the "Open Fairpaper on a computer" screen with a working sign-out.

## Out of scope for version one

- Mobile and tablet use of the app itself (v1 is desktop only; phones get the landing page). A mobile candidate experience and a PWA come after the pilot.
- Live human video proctoring.
- LMS features: courses, lessons, assignments, attendance.
- Webcam/AI proctoring (P2), billing (P3). The pilot is free or invoiced manually.
- Any claim that cheating is *impossible*. Fairpaper detects, deters and records.
- Selling outside Bangladesh before the pilot is paid. The code must be global-ready (F21 framework); global sales, payments and compliance (F24) come after.

## User stories

**Organization and people**
- US1. As an owner, I want to register my institution and get a join code, so I can onboard students without creating accounts for them.
- US2. As an admin, I want to create groups (batches) with their own codes, so each student lands in the right batch.
- US3. As an admin, I want to add teachers as examiners, so they can run exams without managing the organization.
- US4. As a candidate in two coaching centers, I want one account, so I can switch between them.

**Questions and exams**
- US5. As an examiner, I want to import questions from Excel, so I can reuse my existing question sets.
- US6. As an examiner, I want to schedule an exam for specific groups with a window and a duration, so students can start any time in the window but get equal time.
- US7. As an examiner, I want integrity protections on by default, so I don't have to know what to configure.

**Taking an exam**
- US8. As a candidate, I want my answers saved as I go and restored after a reload, so a crash or power cut doesn't lose my work.
- US9. As a candidate, I want to see the rules and protections before I start, so I know what counts as a violation.
- US10. As a candidate, I want a clear timer and a question map, so I can manage my time.

**Grading and results**
- US11. As an examiner, I want choice questions graded automatically and written answers queued for me, so I only mark what needs a human.
- US12. As an examiner, I want each attempt labeled clean / review / high risk, so I check the suspicious ones first.
- US13. As a candidate, I want to see my score and, after the exam closes, the correct answers, so I can learn from mistakes.

**Planned (P0/P1)**
- US14. As any user, I want to reset my password by email, so I can get back in without contacting anyone.
- US15. As an admin, I want to upload a spreadsheet of students, so a whole batch is enrolled and invited at once.
- US16. As a coaching center, I want negative marking and a merit list, so results match admission-test practice.
- US18. As a teacher, I want to give each question its own time limit (or none), so the exam paces students the way a quiz-master would.
- US17. As an examiner, I want each student to get a random set of questions drawn from tagged pools, so answer sharing is less useful.

## Acceptance criteria

**Built behavior (regression tests must keep these true)**
- AC1 (US1). Given a visitor on "Register your organization", when they submit a valid name, email and password, then an organization with an 8-character join code is created, they become its owner, and they land on the Exams page.
- AC2 (US2, US4). Given a signed-in user, when they enter a group's join code, then they become a candidate of that organization *and* a member of that group; entering a code for an organization they already belong to does not duplicate the membership.
- AC3 (US6). Given an exam assigned to group A, when a candidate who is not in group A lists or starts exams, then that exam is not shown and starting it returns 404.
- AC4 (US6). Given an exam with a 60-minute duration whose window closes in 20 minutes, when a candidate starts it, then their deadline is the window's closing time (20 minutes), not 60 minutes.
- AC5 (US8). Given a candidate who answered 5 questions, when they reload the page, then the same attempt resumes with all 5 answers and the remaining time (the timer is not reset).
- AC6 (US8). Given an attempt whose deadline passed more than 30 s ago, when a save-answer request arrives, then it is rejected.
- AC7. Given a candidate who already started or submitted an exam, when they press Start again (even twice in parallel), then no second attempt is created.
- AC8 (US7). Given an exam with `max_violations = 3`, when the candidate leaves the exam tab a 3rd time, then the server submits the attempt with reason "violations" and the page shows the finished state.
- AC9 (US7). Given copy, paste or right-click during an exam, then a flag is recorded but the violation count does not increase.
- AC10. Given shuffling is on, when two candidates open the same exam, then their question orders differ (with ≥ 3 questions), each order stays the same across reloads, and grading is correct whatever the option order.
- AC11 (US11). Given a submitted attempt with choice and written questions, then choice questions are scored at once and the attempt appears under "Needs review" until written answers are graded.
- AC12 (US13). Given an exam that is still open for anyone, when a candidate views their result, then correct answers are not included in the response.
- AC13 (security). Given a staff member of organization X, when they request any question, exam, attempt or member of organization Y by ID, then the API returns 403 or 404.

**Planned (written now so the build has a target)**
- AC14 (US14). Given a registered email, when a reset is requested, then an email with a single-use link valid for 30 minutes is sent; the API response is the same whether the email exists or not; a used or expired link is rejected.
- AC15 (US15). Given an XLSX file with 200 rows (3 invalid), when the admin uploads it, then a preview shows 197 valid and 3 errors with reasons; confirming creates or links 197 candidates in the chosen groups and sends invites.
- AC16 (US16). Given negative marking of 0.25, a candidate with 10 correct, 4 wrong and 6 blank answers on 1-mark questions scores 9.0.
- AC17 (US16). Given a closed exam, the merit list ranks by score (higher first), then by time taken (shorter first); tied candidates share a rank.
- AC21 (F25). Given an exam with copy/paste protection on, when the candidate presses Start exam, then the clipboard is cleared; pasting by Ctrl/Cmd+V, Shift+Insert, the context menu, drag-and-drop or middle-click inserts nothing and records a `copy_paste` flag.
- AC29 (F7). Given a running exam, when the candidate clicks outside the browser window or switches to another tab or app, then a `focus_lost` violation is recorded, the exam is blurred and its question text is no longer on the page; when they come back it stays that way until they click anywhere on the page or press **Return to the exam**.
- AC30 (F25). Given an exam with copy/paste protection on, the candidate can't select question or option text by dragging, double- or triple-clicking, or Ctrl/Cmd+A; selecting inside their own answer box still works.
- AC22 (F27). Given a visitor on `/waitlist`, when they submit a valid email, then they see "You're on the list" and the email is stored once (submitting it again shows the same message and creates no duplicate); an invalid email shows an inline error; the response never reveals whether an email was already on the list.
- AC23 (F27). Given the owner triggers the launch email, then every waitlisted address that hasn't unsubscribed gets exactly one email with an unsubscribe link.
- AC24 (F28). Given no video link is set, the landing page shows the "video coming soon" placeholder at 16:9 with no layout shift; given a link is set, the placeholder becomes a thumbnail with a play button, and the YouTube player loads only after a click.
- AC25 (F29). Given an exam in whole-exam mode, behavior is exactly today's: one timer, free navigation between questions until the deadline.
- AC26 (F29). Given an exam in per-question mode where question 3 has a 45-second limit, when the candidate opens question 3, then a 45-second countdown starts on the server; at 0 the current answer is kept, the question locks, and question 4 opens; pressing **Next** earlier also locks question 3; no request can change question 3's answer afterwards, and the candidate can't navigate back to it.
- AC27 (F29). Given a candidate in per-question mode reloads or loses connection, when they resume, then they return to the same open question with the server's remaining time (the countdown kept running), never a fresh timer.
- AC28 (F29). Given a per-question exam, the overall deadline still applies: the exam ends at whichever comes first, the last question's time running out or `start + duration` / the window closing. A question with "no limit" waits until the candidate presses Next.
- AC18 (US17). Given a pool rule "5 random easy questions tagged physics", each attempt gets 5 questions from that set, and the same 5 after a reload, even if the bank changes meanwhile.

## Open questions

1. **Pricing:** per active candidate per month, per attempt, or flat tiers per institution?
2. **SMS gateway:** SSL Wireless, BulkSMSBD or Alpha SMS? Who owns the sender ID?
3. **Pilot partner:** which institution, and which exams will they run first?
4. **Paid mock tests (F23):** do coaching centers want students to pay per test inside Fairpaper?
5. **Hosting region:** is a server outside Bangladesh acceptable to schools (latency, data residency)? When do EU customers justify an EU region?
8. **First global market:** which country or segment comes after Bangladesh (India coaching, Middle East schools, global hiring teams)?
10. **Waitlist email:** sender name and address, and whether waitlisted people also get a pilot invite before public launch.
9. **Global pricing:** USD pricing per region, or one global price with a lower BDT price?
6. **Brand:** new logo mark for Fairpaper. The current mark is the Bengali letter "প" from the old name, see the [UI/UX Brief](04-UI-UX-BRIEF.md).
7. **Retakes:** should examiners be able to allow a second attempt? This changes the one-attempt-per-exam rule.
