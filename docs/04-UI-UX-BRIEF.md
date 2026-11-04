# 4. UI and UX Design Brief: Fairpaper

Purpose: give the app a consistent, usable visual direction.
Status: living document · Last updated 2026-10-12 · Implemented in `frontend/src/index.css`, `frontend/tailwind.config.js`, `frontend/src/components/ui.js`.

> **The short version:** quiet, clear, fast. One obvious next step on every screen. Nothing moves unless it has to. It must feel instant on a 5-year-old Android phone on 3G.

## Audience and tone

- **Audience:** global, launching in Bangladesh. Students (mostly 15–25), teachers, trainers and HR teams, **on desktop and laptop browsers** (v1 is desktop only; phones get the landing page). Many use old, low-spec PCs and slow connections. **Design for the weakest PC, the slowest connection and a stressed user first.**
- **Three adjectives:** **calm · clear · trustworthy.**
- **Voice:** plain, specific, sentence case, short. Say what happens and why ("Leaving fullscreen hides the questions. It's recorded."). No hype, exclamation marks, emoji or jokes. Never claim cheating is impossible.
- **Avoid the "AI template" look:** purple/blue gradients, glassmorphism and blur, glowing shadows, oversized hero illustrations, decorative blobs, rows of identical cards with icons, gradient text, everything rounded to 24 px.

## Design principles

1. **One primary action per screen.** Exactly one filled (brand) button is visible at a time; everything else is secondary or ghost.
2. **Content over chrome.** No decorative containers. A card exists only to group things that belong together. Prefer whitespace and a 1 px line to boxes inside boxes.
3. **Sensible defaults, progressive disclosure.** Integrity protections are on by default; advanced settings sit behind "More options". A new examiner can publish an exam by touching only title, time and questions.
4. **Say it once.** No subtitles that repeat the title, and no helper text that states the obvious.
5. **Feedback without fuss.** Every action shows a result within 100 ms (pressed state, then a spinner if needed). Success is a quiet state change, not a celebration.
6. **Stillness by default.** Motion is used only to explain a change of state (a dialog opening), never for decoration.
7. **Fast is a feature.** If a design choice costs performance on a cheap phone (blur, large shadows, big images, web fonts in many weights), drop it.

## Reference products

| Product | Borrow | Avoid |
|---|---|---|
| Linear | Quiet density, restrained color, crisp lists | Dark-only look, tiny text |
| Stripe Dashboard | Tables, status badges, stat rows, empty states | Marketing gradients |
| Google Forms | Question layouts students already know | Weak hierarchy, no time/status feedback |
| Notion | Calm typography, generous line height | Too-hidden controls |
| Paper answer sheets | Green "official" color, ruled-line motif (login panel only) | Paper textures, skeuomorphism |

## Color palette

Colors are CSS variables in RGB channels (`--brand: 11 110 79`) so Tailwind can apply opacity (`bg-brand/10`). **Components use token names only, never hex.**

| Token | Role | Light | Dark |
|---|---|---|---|
| `paper` | Page background | `#F7F6F2` | `#0E1012` |
| `surface` | Cards, dialogs | `#FFFFFF` | `#16191D` |
| `sunken` | Inputs, table headers, wells | `#F1F0EB` | `#1D2126` |
| `ink` | Primary text | `#16181D` | `#ECEDEE` |
| `muted` | Secondary text | `#5F6570` | `#9AA0AA` |
| `line` | Borders, dividers | `#E3E1DA` | `#2C3037` |
| `brand` | The one primary action, active state | `#0B6E4F` | `#34B98A` |
| `brand-strong` / `-soft` / `-ink` | Hover / tint / text on the tint | `#08573F` / `#E2F1EA` / `#064E38` | `#52CCA0` / `#123429` / `#8CE1C0` |
| `danger` (+ soft/ink) | Destructive, high risk, violations | `#BE2732` | `#F0626A` |
| `warn` (+ soft/ink) | Needs review, time running low | `#B56A00` | `#E6A53C` |
| `info` (+ soft/ink) | Scheduled, neutral notices | `#2563C7` | `#6EA0F5` |
| `on-brand` | Text on brand buttons | `#FFFFFF` | `#06261C` |

Usage rules:
- **About 90% of any screen is neutral** (paper, surface, ink, muted, line). Brand green marks the primary action and the current location only. Status colors appear only where there is a status.
- Semantic mapping: Live = brand · Scheduled = info · Draft/Closed = neutral · Clean = brand · Review = warn · High risk = danger.
- Status is never shown by color alone: badges always carry text.
- The login side panel is the only large area of color (`#0B3D2E`, faint ruled lines).

## Typography

| Use | Style |
|---|---|
| Page title | 24 px / semibold / tight tracking |
| Section / card title | 15 px / semibold |
| Body | 14 px / regular / 1.5 line height |
| Exam question text | **17 px** (mobile) – 18 px / 1.6 line height: the most important text in the product |
| Secondary, hints | 12–13 px / muted |
| Eyebrow label | 12 px / medium / uppercase / 0.08em |
| Numbers (stats, timer, scores, codes) | Tabular figures; IBM Plex Mono for join codes |

- **Fonts:** IBM Plex Sans (Latin), Hind Siliguri (Bengali), IBM Plex Mono (codes). Self-hosted, `font-display: swap`, **only weights 400 / 500 / 600**, subset per script. Add Noto fallbacks only when a new script ships.
- At most **two type sizes per component** and **three per screen** (excluding the page title).
- Max line length about 70 characters for reading text (questions, descriptions).

## Components

Use `src/components/ui.js`. Don't hand-roll alternatives, and don't add new variants without updating this brief.

| Component | Rules |
|---|---|
| `Button` | `primary` (one per view), `secondary`, `ghost`, `danger` (inside confirm dialogs only), `danger-ghost`. Heights: 32 / 36 / **44 px on touch screens for primary exam actions**. Label = verb ("Publish exam", not "OK") |
| `Input`, `Select`, `Textarea`, `Field` | Label above, never placeholder-only. Hint below; the error replaces the hint. Native `<select>` and date inputs (lighter and familiar on mobile) |
| `Switch` | Settings with a one-line description (integrity options) |
| `Checkbox` | Multi-select lists (groups, multiple-choice answers) |
| `Card` | 12 px radius, 1 px `line` border, near-invisible shadow. No nested cards |
| `Badge` | Status only; short text; one badge per row where possible |
| `Alert` | Inline, at the top of the area it concerns; dismissible unless it's blocking |
| `Tabs` | Max 4; counts optional |
| `Modal` / `useConfirm()` | Only for confirmation or a short focused task. No multi-step flows in modals |
| `EmptyState` | Icon or Paige pose (`paige="sleeping"`), one-line title, one sentence, one action. Paige only on first-run empties (no exams, no students, nothing to grade); search and filter misses keep the icon |
| `Paige` | The mascot as a decorative `<img>` (`alt=""`); the text beside her carries the meaning. Poses: hello, submitted, thinking, careful, marking, sleeping, pointing, join |
| `PageHeader`, `Stat`, `Spinner`, `PageLoader` | Standard scaffolding |

Tailwind rule: class names written literally (lookup objects like `BUTTON_VARIANTS`), never built as `` `bg-${x}` ``.

## Layout rules

- **Desktop first, 1024 px minimum.** Design at 1280 × 800 (the most common laptop), check at 1024 × 768 and 1920 × 1080. Narrower than 1024 px the app shows the `DesktopOnly` screen; only the landing page, login and signup are responsive down to 360 px.
- **Widths:** content `max-w-6xl`; forms and reading `max-w-3xl`; the exam question column `max-w-2xl`.
- **Spacing scale (4 px base):** 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64. Page gutter 32 px. 24–32 px between sections; 16–20 px inside cards.
- **Staff screens:** lists and tables over card grids; use the width (side-by-side panels, sticky filters) instead of stacking.
- **Exam screen:** question column centered at reading width, question map in a fixed right rail, timer and violation chip in a slim top bar. Everything works by keyboard (number keys pick answers, arrow keys move between questions).
- **Pointer and keyboard first:** hover states behind `@media (hover: hover)`, shortcuts shown in tooltips, click targets at least 32 px.

## Screen notes

| Screen | Hierarchy (top → bottom) |
|---|---|
| Login / signup | Logo · title · 2–3 fields · primary button · one line of links. Desktop only: dark-green panel with the value proposition and a static integrity preview |
| Staff · Exams | Title + **New exam** · list rows: title, status badge, window, question count, protection icons, ⋯ menu |
| Staff · New exam | Details & schedule → Questions (searchable picker, selected count) → Who can take it → Integrity (defaults on, collapsed under "More options" except the violation limit) → sticky **Publish** / Save draft |
| Staff · Exam results | Stat row (Started · Submitted · Average · Need review) → tabs → search → table (student, score, risk, violations, Report · Grade) |
| Staff · Integrity report | Summary → protections in effect → timeline → note that events are signals, not proof |
| Candidate · Exams | Continue where you left off (warn) → Open now → Upcoming → Done. Each card: title, time left / opens at, one button |
| Candidate · Rules | Exam title · duration · question count · each protection in one plain sentence · **Start exam** (bottom) |
| Candidate · Exam | Slim top bar (title, violation chip, timer) · question · answers as large tap rows · bottom bar: Previous · question map · Next/Submit. The question map opens as a sheet on phones |
| Candidate · Exam (per-question mode) | Same layout; a question timer next to the question number (mono, counts down; warn at 10 s, danger at 5 s, color only); "Next question" replaces Previous/Next; the question map greys out locked questions |
| Candidate · Blocked | Full-screen plain panel: what happened, that it was recorded, one button to return |
| Candidate · Finished | Outcome first (score or "Awaiting grading") · submit reason if not the student · View results |

## Flow rules

- **Candidate: two taps from the dashboard to the first question** (Start → Start exam). Never ask for anything else at exam time.
- **Examiner: create → publish in one screen.** No wizards.
- **Never lose input:** forms keep their values after an error; the exam saves continuously; leaving a page with unsaved changes asks first.
- **Undo over confirm** where it's cheap (removing a group member); **confirm** only for destructive or irreversible actions (delete exam, submit exam), and the confirm button repeats the verb ("Delete exam").
- **Errors explain the fix:** "This exam opens at 10:00 (Asia/Dhaka)", not "Bad request".
- Back always works; every screen has a URL.

## Motion

| Allowed | Duration | Where |
|---|---|---|
| Fade | 150 ms ease-out | Dialog/sheet backdrop, toasts |
| Short rise (6 px) | 150–200 ms | Dialog/sheet panel only |
| Color/opacity transition | 150 ms | Hover, pressed, focus |

- **Landing page exception:** restrained scroll-driven reveals and one signature scroll moment are allowed there (see `scroll-craft`), `transform` and `opacity` only, fully static under reduced motion. The app itself stays still.
- **Not allowed in the app:** page-load animations, staggered lists, parallax, bouncing, skeleton shimmer loops, animated gradients, looping or decorative animation.
- Spinners only after 300 ms of waiting (avoid flicker).
- The timer's last minute changes **color** (warn → danger); it does not pulse. The "Live" badge is static.
- Only `opacity` and `transform` are animated (GPU-cheap). Never animate layout, shadows or blur.
- `prefers-reduced-motion: reduce` turns all motion off.

## Performance budget (low-end PCs and slow connections)

Target device: an old office or lab PC (dual-core, 4 GB RAM, integrated graphics), Chrome or Edge, on a slow connection (throttled "Fast 3G": 1.6 Mbps, 150 ms RTT). The landing page is also budgeted for a mid-range phone.

| Metric | Budget |
|---|---|
| Initial JS for candidate routes | ≤ 170 KB gzipped (staff screens are code-split and loaded separately) |
| CSS | ≤ 30 KB gzipped |
| Fonts on first load | ≤ 3 files, ≤ 120 KB total (Latin subset; Bengali loaded only when needed) |
| Exam page: Largest Contentful Paint | ≤ 2.5 s on the target device/network |
| Interaction to Next Paint (tap an answer) | ≤ 200 ms |
| Cumulative Layout Shift | ≤ 0.05 |
| Images | None in the UI chrome; question images lazy-loaded, sized, compressed (WebP) |

Rules that follow from the budget:
- **No `backdrop-blur`** anywhere (expensive on low-end GPUs); use solid or semi-opaque backgrounds. One deliberate exception (owner request, 2026-10-31): while a candidate is away from a running exam, the exam is blurred with a static `filter: blur` (Tailwind `blur-md`) under the "You left the exam" card. It's not `backdrop-filter`, it never animates, and what's under it is only placeholder bars.
- Shadows: only the two tokens (`card`, `pop`). Prefer borders.
- Route-level code splitting (`React.lazy`) so candidates never download staff screens.
- No heavy libraries for small jobs (date pickers, charts, animation libs). Native inputs and `Intl` first. Charts, when needed, load on demand.
- Lists over ~100 rows paginate or virtualize.
- Measure with Lighthouse (mobile) in CI once deployed. A PR that breaks the budget needs a written reason.

## Accessibility

- WCAG 2.2 AA: text contrast 4.5:1, UI elements 3:1, in both themes.
- Every input has a visible `<label>`; errors are announced (`role="alert"`); dialogs trap and restore focus; Esc closes.
- Full keyboard use with a visible focus ring (`:focus-visible`, 2 px solid brand, at least 3:1 against the page). Dialogs keep Tab inside and return focus to what opened them; starting an exam moves focus to the first question.
- Reduced motion (`prefers-reduced-motion`): transitions are instant and entrances fade without moving; spinners keep turning.
- Secondary ("faint") text keeps 4.5:1 on paper, surface and sunken backgrounds in both themes.
- Click targets at least 32 × 32 px; answers are full-width rows. Landing page touch targets at least 44 × 44 px.
- Text scales to 200% without breaking layout; no text in images.
- Theme follows `prefers-color-scheme` on first visit; the choice is remembered.

## Internationalization rules (global audience)

- **No hardcoded copy.** Every visible string goes through `t()` / `tn()` (task 1.8 done). Keep sentences whole (no concatenation); plurals via i18n rules.
- **Allow ~40% text expansion.** No fixed widths on text; buttons wrap gracefully.
- **Right-to-left ready (task 1.10 done).** Only logical utilities: `ms-*`/`me-*`, `ps-*`/`pe-*`, `start-*`/`end-*`, `text-start`/`text-end`, `border-s`/`border-e`, `rounded-s`/`rounded-e`. Never `ml-`, `pl-`, `left-`, `text-left`, `border-l`, `rounded-l`. Arrows that mean back/forward get `rtl:-scale-x-100`; anything moved with `translate-x` needs its `rtl:` opposite. Check with `?lang=en-XB` (pseudo-language laid out right to left). Latin pseudo-text shows punctuation in odd places under RTL; that's the browser's bidi algorithm, not a layout bug.
- **Fonts per script**, loaded only when that language is used.
- **Locale formatting** via `Intl` for dates, times, numbers and currency; show the timezone for exam windows when it differs from the viewer's.
- **Neutral sample data** (names, places) in empty states, previews and marketing.

## Interaction states

| State | Treatment |
|---|---|
| Hover (pointer only) | Background `sunken` or `brand-strong`; no movement |
| Pressed | Slightly darker immediately (the 100 ms feedback rule) |
| Focus | 2 px brand ring with offset, keyboard only |
| Disabled | 50% opacity, no pointer events, with a reason nearby when not obvious |
| Loading | Button: spinner replaces the icon, label kept. Page: `PageLoader` draws a **skeleton in the page's shape** (`variant`: `list`, `detail`, `cards`, `sheet`, `exam`), never a lone spinner; after 5 s it adds "Still loading. Your connection seems slow…" |
| Load error | `ErrorState` in place of the content, never an empty list: what happened and whose side it's on (offline · couldn't reach Fairpaper · our side, your work is safe · no access · not found · session ended), and **Try again** when retrying can help, plus a way back |
| Error after an action | Inline `Alert` with the server's message saying how to fix it |
| Form validation | On the exact field (`Field error`, `aria-invalid`), saying how to fix it ("for example 60"); focus moves to the first bad field; a one-line summary by the buttons. Email fields catch common domain typos (`EmailSuggestion`: "Did you mean …@gmail.com?") |
| Success | A toast (`useToast`): what happened, the details worth repeating (when it opens, for whom, the file name) and the next step (**View exam**, **Write another question**). Inline changes for small toggles; no success dialogs |
| Empty | `EmptyState`: why there's nothing yet and one next step |
| No search results | `NoResults`: what was searched, "Did you mean …" (closest word from titles, names, tags), **Clear search** / **Clear filters** |
| Offline | `OfflineBanner` under the browser bar on every page except the exam (it has its own): what's on screen stays, reading works, saving waits; "You're back online" for a few seconds after |
| Slow upload | `UploadProgress`: the real percentage, then "Checking it…"; photo answers add the lighter path (a smaller or cropped photo) |
| Permission | Role: `NoAccess` (who the page is for, who you're signed in as, home and switch organization) instead of a silent redirect. Browser fullscreen: why it's required, the keyboard shortcut, and asking the examiner to turn it off |
| Session ended | Idle sign-out or a refused session (401): the sign-in page says why and that work is safe, keeps the email and returns to the same page. Long forms (exam, question) keep unsaved changes on this computer (`useDraft`) and offer them back (`DraftNotice`) |
| Time running low | Timer color warn (5 min) → danger (1 min); no animation |

## Assets needed

| Asset | Status |
|---|---|
| **Fairpaper logo mark + wordmark** | **Done (1.1, changed 2026-10-28):** a row of four answer bubbles, the third filled in, on the brand green (owner's pick from `scrollcraft/builds/fairpaper-landing/logo-explorations.html`, option 2). `LogoMark` / `Logo` in `ui.js` (inline SVG, theme tokens, works in both themes); wordmark "Fairpaper" in IBM Plex Sans semibold |
| Favicon, PWA icons, `index.html` title, `manifest.json` | **Done (1.1):** `public/favicon.svg`, `favicon.ico` (16–64), `logo192.png`, `logo512.png`, all from the same 32-unit geometry |
| Icons | Lucide via `react-icons/lu`, 16–18 px, stroke 1.75–2; only icons that add meaning |
| Illustrations | **Paige, the mascot (sketch, 2026-10-29):** a sheet of exam paper with the logo's bubbles as a badge. Single source `design/paige/paige.js` (8 poses); `node design/paige/build.mjs` writes `frontend/public/paige/*.svg` and the landing page copies. Used on the exam finish screen (submitted; careful after a violations auto-submit; thinking while results are held), first-run empty states, and the waitlist page. **Owner: an illustrator polishes the final artwork**; keep the pose names and the 160 × 160 viewBox so the art drops in without code changes |
| Email templates | Plain HTML: logo, one heading, one paragraph, one button; works without images |
| Marketing screenshots | After the pilot UI is final |

## Current code vs. this brief (to fix)

- ~~`backdrop-blur` on the app shell header, modal backdrop, exam header and exam-form footer~~ Removed (1.11).
- ~~Timer and "Live" badge pulse~~ Now static color states (1.11).
- ~~Page-level `animate-rise-in` on auth forms~~ Removed with the new auth sheet (1.11).
- No route-level code splitting yet → add `React.lazy` for staff routes.
- Fonts load the full families → subset, and load Bengali only when needed.

These are tracked as task 5.4 in the Implementation Plan.
