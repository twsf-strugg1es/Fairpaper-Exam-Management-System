import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { LuArrowDown, LuArrowLeft, LuArrowUp, LuImage, LuCircleAlert } from 'react-icons/lu';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import useExamIntegrity, { clearClipboard, enterFullscreen, exitFullscreen, fullscreenSupported } from '../hooks/useExamIntegrity';
import { Alert, Badge, Button, Card, Input, Logo, LogoMark, Modal, PageLoader, Paige, Select, Textarea, UploadProgress, cx } from '../components/ui';
import { answerText, blankCount, isAnswered, isManual, keyText, parseNumber, splitBlanks } from '../questionTypes';
import MathText from '../components/MathText';
import { errorMessage, formatClock, formatExamTime } from '../utils';
import { useI18n } from '../i18n';
import { createAnswerQueue, openStorage } from '../answerQueue';

const TEXT_SAVE_DELAY = 700; // save written answers once the student pauses typing
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;


// --- Before the exam: what will be enforced; the timer starts only when they press Start ---

function RulesScreen({ exam, resuming, onStart, starting, error }) {
  const { t, tn } = useI18n();
  const s = exam.integrity || {};
  // Before the window opens, say when (in the organization's time) instead of letting Start fail, and turn
  // Start on when it opens without a reload; after it closes, say so
  const opensAt = new Date(exam.start_time).getTime();
  const closesAt = new Date(exam.end_time).getTime();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (resuming || Date.now() >= opensAt) return undefined;
    const id = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(id);
  }, [opensAt, resuming]);
  const notYet = !resuming && now < opensAt;
  const closed = !resuming && now > closesAt;
  const fullscreen = s.require_fullscreen && fullscreenSupported();
  const rules = [
    fullscreen && { text: t('The exam runs in fullscreen. Questions are hidden whenever you leave fullscreen.') },
    { text: t('Clicking outside the exam, or switching to another tab, window or app, is recorded as a violation. The questions stay blurred until you click back into the exam.') },
    s.max_violations
      ? { text: tn(s.max_violations, 'After {{count}} violation your exam is submitted automatically.', 'After {{count}} violations your exam is submitted automatically.'), strong: true }
      : { text: t('Violations are recorded and shown to your examiner.') },
    s.block_copy_paste && { text: t("You can't select, copy or paste text, or right-click. Your clipboard is emptied when you start and each time you come back.") },
    (s.shuffle_questions || s.shuffle_options) && { text: t('Questions and options are in a different order for every student.') },
    exam.timed_sections && { text: t('The sections are taken in order, one at a time. A section closes when its time runs out or when you finish it, and you can’t go back to it.') },
    exam.timing_mode === 'per_question' && { text: t('Each question has its own time. When it runs out, or when you press Next, the next question opens and you can’t go back.') },
  ].filter(Boolean);

  return (
    <div className="min-h-screen bg-paper">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <Logo />
        <Link to="/student-account" className="btn btn-ghost btn-sm"><LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" />{t('Back')}</Link>
      </header>
      <main className="sheet sheet-margin mx-auto mb-16 mt-4 max-w-2xl px-6 pb-10 pt-9 sm:ps-14 sm:pe-12">
        <div className="flex items-baseline justify-between gap-4 border-b-2 border-ink pb-3.5">
          <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.02em]">{exam.title}</h1>
          <span className="eyebrow shrink-0">{resuming ? t('Continue') : t('Instructions')}</span>
        </div>
        <dl className="mt-4 grid grid-cols-3 gap-4 border-b border-line pb-4 font-mono text-sm">
          <div><dt className="eyebrow">{t('Time')}</dt><dd className="tabular mt-1">{t('{{n}} min', { n: exam.duration_minutes })}{exam.extra_minutes > 0 && <span className="text-brand"> + {t('{{n}} min extra', { n: exam.extra_minutes })}</span>}</dd></div>
          <div><dt className="eyebrow">{t('Questions')}</dt><dd className="tabular mt-1">{exam.question_count}</dd></div>
          <div><dt className="eyebrow">{t('Closes')}</dt><dd className="tabular mt-1">{formatExamTime(exam.end_time)}</dd></div>
        </dl>
        {exam.sections?.length > 0 && (
          <ol className="mt-4 space-y-1.5 border-b border-line pb-4 text-sm">
            {exam.sections.map((section, i) => (
              <li key={i} className="flex items-baseline justify-between gap-4">
                <span className="min-w-0"><span className="tabular me-2 font-mono text-faint">{String(i + 1).padStart(2, '0')}</span>{section.title}</span>
                <span className="tabular shrink-0 font-mono text-xs text-muted">
                  {tn(section.question_count, '{{count}} question', '{{count}} questions')}
                  {section.time_limit_minutes ? ` · ${t('{{n}} min', { n: section.time_limit_minutes })}` : ''}
                </span>
              </li>
            ))}
          </ol>
        )}

        {resuming && (
          <Alert tone="warn" className="mt-6" title={t('Your timer has been running')}>
            {t("It started when you first opened the exam and doesn't pause. Violations recorded earlier still count.")}
          </Alert>
        )}

        <ol className="mt-6">
          {rules.map(({ text, strong }, i) => (
            <li key={text} className="flex gap-4 border-b border-line py-3 last:border-b-0">
              <span className="tabular w-6 shrink-0 font-mono text-sm text-faint">{String(i + 1).padStart(2, '0')}</span>
              <p className={cx('text-[15px] leading-relaxed', strong && 'font-medium text-danger')}>{text}</p>
            </li>
          ))}
        </ol>

        <p className="mt-6 text-sm leading-relaxed text-muted">
          {resuming ? t('Your saved answers are restored.') : t('Once you start, the timer runs even if you close the page.')} {t('Answers save automatically as you go.')}
        </p>

        {notYet && (
          <Alert tone="info" className="mt-6" title={t('This exam opens {{when}}', { when: formatExamTime(exam.start_time) })}>
            {t('You can read the rules now. Start turns on when the exam opens; there is no need to reload.')}
          </Alert>
        )}
        {closed && (
          <Alert tone="warn" className="mt-6" title={t('This exam closed {{when}}', { when: formatExamTime(exam.end_time) })}>
            {t('Ask your examiner if you think you should still be able to take it.')}
          </Alert>
        )}
        {error && <Alert tone="danger" className="mt-6">{error}</Alert>}

        <Button size="lg" className="mt-8 w-full" onClick={onStart} loading={starting} disabled={notYet || closed}>
          {resuming ? t('Continue exam') : fullscreen ? t('Start exam in fullscreen') : t('Start exam')}
        </Button>
      </main>
    </div>
  );
}

// --- During the exam ---

function Timer({ seconds }) {
  const { t } = useI18n();
  const tone = seconds <= 60 ? 'text-danger' : seconds <= 300 ? 'text-warn' : 'text-ink';
  return (
    <span className={cx('tabular flex items-baseline gap-2 font-mono text-[1.35rem] font-semibold leading-none', tone)} aria-label={t('{{time}} left', { time: formatClock(seconds) })}>
      <span className="eyebrow">{t('Left')}</span>
      {formatClock(seconds)}
    </span>
  );
}

// The open question's own countdown in a per-question exam (warn at 10 s, danger at 5 s, color only)
function QuestionTimer({ seconds }) {
  const { t } = useI18n();
  const tone = seconds <= 5 ? 'text-danger' : seconds <= 10 ? 'text-warn' : 'text-ink';
  return (
    <span className={cx('tabular ms-auto font-mono text-[1.35rem] font-semibold leading-none', tone)} aria-label={t('{{time}} left for this question', { time: formatClock(seconds) })}>
      {formatClock(seconds)}
    </span>
  );
}

// Where a per-question exam is: questions done (locked), the open one, and those still to come
function StepMap({ progress }) {
  const { t } = useI18n();
  const label = (state, n) => (state === 'closed' ? t('Question {{n}}, done', { n })
    : state === 'open' ? t('Question {{n}}, open now', { n }) : t('Question {{n}}, still to come', { n }));
  return (
    <div>
      <ol className="grid grid-cols-5 gap-x-3 gap-y-2.5" aria-label={t('Questions')}>
        {progress.states.map((state, i) => (
          <li
            key={i}
            className={cx(
              'bubble h-[34px] w-[34px] text-[11px]',
              state === 'closed' && 'border-line bg-sunken text-faint',
              state === 'open' && 'bubble-filled shadow-[0_0_0_2px_rgb(var(--surface)),0_0_0_4px_rgb(var(--ink))]',
              state === 'upcoming' && 'text-faint',
            )}
            aria-label={label(state, i + 1)}
            aria-current={state === 'open' ? 'step' : undefined}
          >
            {String(i + 1).padStart(2, '0')}
          </li>
        ))}
      </ol>
      <p className="mt-5 border-t border-line pt-4 text-[13px] leading-relaxed text-muted">{t('Questions open one at a time. The ones you’ve left are locked.')}</p>
    </div>
  );
}

// The open section's own countdown (timed sections), next to the exam's
function SectionTimer({ title, seconds }) {
  const { t } = useI18n();
  const tone = seconds <= 10 ? 'text-danger' : seconds <= 60 ? 'text-warn' : 'text-ink';
  return (
    <span className="flex items-baseline gap-2 border-e border-line pe-5" aria-label={t('{{section}}: {{time}} left', { section: title, time: formatClock(seconds) })}>
      <span className="eyebrow max-w-[11rem] truncate">{title}</span>
      <span className={cx('tabular font-mono text-[1.1rem] font-semibold leading-none', tone)}>{formatClock(seconds)}</span>
    </span>
  );
}

function SaveStatus({ status, waiting }) {
  const { t, tn } = useI18n();
  const states = {
    saving: [t('Saving'), 'text-faint'],
    saved: [t('Saved'), 'text-brand'],
    offline: [tn(waiting, 'Offline · {{count}} answer waiting', 'Offline · {{count}} answers waiting'), 'text-warn'],
    error: [t('Not saved'), 'text-danger'],
  };
  if (!states[status]) return null;
  const [label, tone] = states[status];
  return (
    <span className="flex items-center gap-2 font-mono text-xs text-faint" role="status" title={status === 'offline' ? t('Your answers are kept on this computer and sent when you reconnect.') : undefined}>
      <span className={cx('status-dot', tone, status !== 'saving' && 'bg-current')} />
      {label}
    </span>
  );
}

function ViolationChip({ count, max }) {
  const { t } = useI18n();
  const hit = count > 0;
  return (
    <span
      className={cx('tabular rounded border px-2.5 py-1.5 font-mono text-xs font-medium tracking-[0.04em]', hit ? 'border-danger text-danger' : 'border-line-strong text-muted')}
      title={t('Times you left the exam')}
    >
      {t('LEFT EXAM')} <b className={hit ? 'text-danger' : 'text-ink'}>{count}</b>{max ? ` / ${max}` : ''}
    </span>
  );
}

// Shown over the blurred exam whenever the questions are hidden. A click anywhere brings the student back
// (the button is there for keyboard users, and gets focus).
function BlockedOverlay({ integrity }) {
  const { t, tn } = useI18n();
  const remaining = integrity.maxViolations ? integrity.maxViolations - integrity.violations : null;
  const left = integrity.isAway || integrity.needsReturn;
  return (
    <div className="fixed inset-0 z-40 grid cursor-pointer place-items-center bg-paper/40 p-6" onClick={integrity.returnToExam}>
      <Card className="max-w-md p-8 text-center" role="alertdialog" aria-modal="true" aria-labelledby="away-title" aria-describedby="away-text">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.08em] text-danger">{t('Recorded')}</p>
        <h2 id="away-title" className="mt-3 text-2xl font-semibold tracking-tight">
          {left ? t('You left the exam') : t('Fullscreen is required')}
        </h2>
        <p id="away-text" className="mt-3 text-[15px] leading-relaxed text-muted">
          {left ? t('The questions stay blurred until you click back into the exam.') : t('The questions are hidden until you come back to fullscreen.')}
          {integrity.violations > 0 && ` ${tn(integrity.violations, '{{count}} violation has been recorded.', '{{count}} violations have been recorded.')}`}
        </p>
        {remaining !== null && remaining > 0 && (
          <p className="mt-3 text-sm font-medium text-danger">
            {remaining === 1 ? t('One more violation and your exam is submitted automatically.') : t('{{n}} more and your exam is submitted automatically.', { n: remaining })}
          </p>
        )}
        {!left && (
          <p className="mt-3 text-sm leading-relaxed text-muted">
            {t("Your examiner asked for fullscreen, so the exam has your whole screen. If the button doesn't work, press F11 (Windows) or Control+Command+F (Mac). If your browser won't allow fullscreen, tell your examiner: they can turn it off for this exam.")}
          </p>
        )}
        <Button size="lg" className="mt-7" autoFocus onClick={(e) => { e.stopPropagation(); integrity.returnToExam(); }}>{t('Return to the exam')}</Button>
        <p className="mt-3 text-sm text-faint">{t('Or click anywhere on the page.')}</p>
      </Card>
    </div>
  );
}

// While the questions are hidden their text isn't on the page at all: an AI sidebar or an extension can read a
// page's text even when it's blurred. These bars only keep the shape of the page under the blur.
function HiddenQuestion() {
  return (
    <div aria-hidden="true">
      <div className="flex items-end gap-4 border-b border-line-strong pb-3.5">
        <span className="h-9 w-14 rounded bg-sunken" />
        <span className="h-3 w-36 rounded bg-sunken" />
      </div>
      <div className="my-7 space-y-3">
        <span className="block h-4 w-11/12 rounded bg-sunken" />
        <span className="block h-4 w-2/3 rounded bg-sunken" />
      </div>
      <div className="space-y-2.5">
        {[0, 1, 2, 3].map((i) => <span key={i} className="block h-12 rounded-lg border border-line bg-surface" />)}
      </div>
    </div>
  );
}

// The question map: one answer bubble per question. Filled = answered, ring = current, red dot = flagged
function QuestionNav({ questions, answers, flagged, current, onJump, sections = [] }) {
  const { t, tn } = useI18n();
  const all = questions.map((q, i) => ({ q, i }));
  // With sections, each gets its own group; a timed exam lists its finished and upcoming sections without questions
  const groups = sections.length
    ? sections.map((section) => ({ section, items: all.filter(({ q }) => q.section_id === section.id) }))
    : [{ section: null, items: all }];
  return (
    <div>
      {groups.map(({ section, items }) => (
        <div key={section?.id || 'all'} className={cx(section && 'mb-5')}>
          {section && (
            <p className="mb-2 flex items-baseline justify-between gap-2 text-xs">
              <span className={cx('truncate font-medium', section.state === 'closed' || section.state === 'upcoming' ? 'text-faint' : 'text-ink')}>{section.title}</span>
              {section.state === 'closed' && <span className="shrink-0 font-mono text-faint">{t('Finished')}</span>}
            </p>
          )}
          {items.length === 0 ? (
            section && section.state === 'upcoming' && (
              <p className="font-mono text-xs text-faint">
                {tn(section.question_count, '{{count}} question', '{{count}} questions')}
                {section.time_limit_minutes ? ` · ${t('{{n}} min', { n: section.time_limit_minutes })}` : ''}
              </p>
            )
          ) : (
            <div className="grid grid-cols-5 gap-x-3 gap-y-2.5">
              {items.map(({ q, i }) => {
                const answered = isAnswered(answers[q.id]);
                return (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => onJump(i)}
                    className={cx(
                      'bubble relative h-[34px] w-[34px] text-[11px]',
                      answered ? 'bubble-filled' : 'bg-transparent hover:border-ink hover:text-ink',
                      i === current && 'shadow-[0_0_0_2px_rgb(var(--surface)),0_0_0_4px_rgb(var(--ink))]',
                    )}
                    aria-label={[t('Question {{n}}', { n: i + 1 }), answered && t('answered'), flagged.has(q.id) && t('flagged for review')].filter(Boolean).join(', ')}
                    aria-current={i === current ? 'step' : undefined}
                  >
                    {String(i + 1).padStart(2, '0')}
                    {flagged.has(q.id) && <span className="absolute -end-[3px] -top-[3px] h-[9px] w-[9px] rounded-full border-2 border-surface bg-danger" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      ))}
      <div className="mt-5 space-y-2 border-t border-line pt-4 text-[13px] text-muted">
        <p className="flex items-center gap-2.5"><span className="bubble bubble-filled h-4 w-4" />{t('Answered')}</p>
        <p className="flex items-center gap-2.5"><span className="bubble h-4 w-4" />{t('Not answered')}</p>
        <p className="flex items-center gap-2.5"><span className="relative"><span className="bubble h-4 w-4" /><span className="absolute -end-1 -top-1 h-2 w-2 rounded-full bg-danger" /></span>{t('Flagged')}</p>
      </div>
    </div>
  );
}

const LETTERS = 'ABCDEFGHIJ';

// An answer row: lettered bubble, the option, and its keyboard key
function ChoiceOption({ type, index, label, checked, onChange }) {
  return (
    <label
      className={cx(
        'flex cursor-pointer items-center gap-4 border-b border-line px-3 py-3.5 transition-colors',
        checked ? 'bg-brand-soft' : 'hover:bg-sunken/60',
      )}
    >
      <input type={type} className="peer sr-only" checked={checked} onChange={onChange} />
      <span className={cx('bubble peer-focus-visible:ring-2 peer-focus-visible:ring-brand peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-paper', checked && 'bubble-filled')} aria-hidden="true">
        {LETTERS[index]}
      </span>
      <span className="flex-1 text-base">{typeof label === 'string' ? <MathText text={label} /> : label}</span>
      {index < 9 && <span className="kbd hidden sm:inline-block" aria-hidden="true">{index + 1}</span>}
    </label>
  );
}

const TITLE_STYLE = 'my-7 max-w-[62ch] text-[1.2rem] font-normal leading-relaxed [text-wrap:pretty]';

// The question text. A fill-in-the-blank question has its answer boxes where the blanks are, or one after the text.
// The teacher's text sets its own direction (dir="auto"), so an English sentence keeps its blanks in reading order
// in a right-to-left interface, and the other way round.
function QuestionText({ question, value, onChange }) {
  const { t } = useI18n();
  if (question.type !== 'fill_blank') return <h2 dir="auto" className={TITLE_STYLE}><MathText text={question.title} /></h2>;
  const parts = splitBlanks(question.title);
  const count = question.options?.blanks || blankCount(question.title);
  const given = Array.isArray(value) ? value : [];
  const set = (i, text) => onChange(Array.from({ length: count }, (_, j) => (j === i ? text : given[j] || '')), { debounce: true });
  const box = (i) => (
    <input
      key={`blank-${i}`}
      type="text"
      className="input mx-1 inline-block h-9 w-44 max-w-full px-2 align-baseline text-base"
      value={given[i] || ''}
      onChange={(e) => set(i, e.target.value)}
      aria-label={count > 1 ? t('Blank {{n}} of {{total}}', { n: i + 1, total: count }) : t('The blank')}
      autoComplete="off"
      spellCheck={false}
    />
  );
  if (parts.length === 1) {
    return (
      <>
        <h2 dir="auto" className={TITLE_STYLE}><MathText text={question.title} /></h2>
        <p className="eyebrow mb-2">{t('Your answer')}</p>
        {box(0)}
      </>
    );
  }
  const text = (part, i) => <MathText key={`text-${i}`} text={part} />;
  return <h2 dir="auto" className={TITLE_STYLE}>{parts.flatMap((part, i) => (i === 0 ? [text(part, i)] : [box(i - 1), text(part, i)]))}</h2>;
}

// Items to put in order: arrows move one place at a time, and focus follows the moved item
function OrderingAnswer({ question, value, onChange }) {
  const { t } = useI18n();
  const list = useRef(null);
  const [said, setSaid] = useState('');
  // Until the first move the order shown is the shuffled one, which is never the answer, and nothing is saved
  const items = Array.isArray(value) && value.length ? value : question.options || [];
  const move = (i, j, direction) => {
    const next = [...items];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
    setSaid(t('{{item}} moved to position {{n}} of {{total}}', { item: items[i], n: j + 1, total: items.length }));
    requestAnimationFrame(() => {
      const row = list.current?.querySelector(`[data-row="${j}"]`);
      (row?.querySelector(`[data-move="${direction}"]:not(:disabled)`) || row?.querySelector('[data-move]:not(:disabled)'))?.focus();
    });
  };
  return (
    <div>
      <p className="mb-2 font-mono text-xs text-faint">{t('Put these in order with the arrows, first at the top')}</p>
      <ol ref={list} className="border-t border-line">
        {items.map((item, i) => (
          <li key={i} data-row={i} className="flex items-center gap-3 border-b border-line px-3 py-3">
            <span className="bubble" aria-hidden="true">{i + 1}</span>
            <span className="min-w-0 flex-1 text-base"><MathText text={item} /></span>
            <Button variant="ghost" size="sm" icon={LuArrowUp} data-move="up" disabled={i === 0} onClick={() => move(i, i - 1, 'up')} aria-label={t('Move {{item}} up', { item })} />
            <Button variant="ghost" size="sm" icon={LuArrowDown} data-move="down" disabled={i === items.length - 1} onClick={() => move(i, i + 1, 'down')} aria-label={t('Move {{item}} down', { item })} />
          </li>
        ))}
      </ol>
      <p className="sr-only" aria-live="polite">{said}</p>
    </div>
  );
}

function QuestionBody({ question, value, onChange, onImage, onPickFile, upload }) {
  const { t } = useI18n();
  if (question.type === 'true_false') {
    return (
      <div className="border-t border-line" role="radiogroup" aria-label={t('Answer')}>
        {['true', 'false'].map((option, i) => (
          <ChoiceOption key={option} type="radio" index={i} label={option === 'true' ? t('True') : t('False')} checked={value === option} onChange={() => onChange(option)} />
        ))}
      </div>
    );
  }
  if (question.type === 'numeric') {
    const typed = typeof value === 'string' || typeof value === 'number' ? String(value) : '';
    const number = typed.trim() ? parseNumber(typed) : null;
    return (
      <div>
        <label htmlFor={`answer-${question.id}`} className="eyebrow mb-2 block">{t('Your answer')}</label>
        <Input
          id={`answer-${question.id}`}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          value={typed}
          onChange={(e) => onChange(e.target.value, { debounce: true })}
          placeholder={t('Type a number')}
          aria-describedby={`answer-${question.id}-read`}
          className="tabular h-12 max-w-xs text-lg"
        />
        <p id={`answer-${question.id}-read`} className="mt-2 min-h-5 text-sm text-muted" aria-live="polite">
          {typed.trim() !== '' && number === null && <span className="text-warn-ink">{t('That isn’t a number yet. Use digits, like 9.8 or 1,000.')}</span>}
          {number !== null && String(number) !== typed.trim() && t('Read as {{n}}', { n: number })}
        </p>
      </div>
    );
  }
  if (question.type === 'matching') {
    const left = question.options?.left || [];
    const right = question.options?.right || [];
    const chosen = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    // Each match is used once: choosing one that another item has moves it here
    const pick = (item, match) => {
      const next = Object.fromEntries(Object.entries(chosen).filter(([k, v]) => k !== item && v !== match));
      if (match) next[item] = match;
      onChange(next);
    };
    return (
      <div>
        <p className="mb-2 font-mono text-xs text-faint">{t('Pick the match for each item. Each match is used once.')}</p>
        <ul className="border-t border-line">
          {left.map((item, i) => (
            <li key={item} className="grid items-center gap-x-4 gap-y-2 border-b border-line px-3 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,16rem)]">
              <span className="flex items-center gap-4 text-base">
                <span className="bubble" aria-hidden="true">{LETTERS[i]}</span>
                <MathText text={item} />
              </span>
              <Select value={chosen[item] || ''} onChange={(e) => pick(item, e.target.value)} aria-label={t('Match for {{item}}', { item })}>
                <option value="">{t('Choose a match')}</option>
                {right.map((match) => {
                  const holder = Object.keys(chosen).find((k) => k !== item && chosen[k] === match);
                  return <option key={match} value={match}>{holder ? t('{{match}} (used for {{item}})', { match, item: holder }) : match}</option>;
                })}
              </Select>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (question.type === 'ordering') return <OrderingAnswer question={question} value={value} onChange={onChange} />;
  if (question.type === 'fill_blank') return null; // the answer boxes sit in the question text
  if (question.type === 'single_choice') {
    return (
      <div className="border-t border-line" role="radiogroup" aria-label={t('Answer')}>
        {(question.options || []).map((option, i) => (
          <ChoiceOption key={option} type="radio" index={i} label={option} checked={value === option} onChange={() => onChange(option)} />
        ))}
      </div>
    );
  }
  if (question.type === 'multi_choice') {
    const selected = Array.isArray(value) ? value : [];
    return (
      <div>
        <p className="mb-2 font-mono text-xs text-faint">{t('Select all that apply')}</p>
        <div className="border-t border-line">
          {(question.options || []).map((option, i) => (
            <ChoiceOption
              key={option}
              type="checkbox"
              index={i}
              label={option}
              checked={selected.includes(option)}
              onChange={() => onChange(selected.includes(option) ? selected.filter((o) => o !== option) : [...selected, option])}
            />
          ))}
        </div>
      </div>
    );
  }
  if (question.type === 'text') {
    return (
      <div>
        <label htmlFor={`answer-${question.id}`} className="eyebrow mb-2 block">{t('Your answer')}</label>
        <Textarea
          id={`answer-${question.id}`}
          rows={9}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value, { debounce: true })}
          placeholder={t('Type your answer here')}
          className="text-base"
          spellCheck={false}
        />
      </div>
    );
  }
  if (question.type === 'image_upload') {
    return (
      <div>
        <label
          className="flex cursor-pointer flex-col items-center rounded border-[1.5px] border-dashed border-line-strong px-6 py-10 text-center transition-colors hover:border-ink hover:bg-surface"
          onClick={onPickFile}
        >
          <LuImage className="h-7 w-7 text-muted" />
          <span className="mt-3 text-sm font-medium">{value?.name ? t('Choose a different image') : t('Upload an image of your answer')}</span>
          <span className="mt-1 font-mono text-xs text-faint">{t('JPG or PNG, up to 2 MB')}</span>
          <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files[0] && onImage(e.target.files[0])} />
        </label>
        {value?.preview && (
          <img src={value.preview} alt={t('Your uploaded answer')} className="mt-4 max-h-80 rounded border border-line object-contain" />
        )}
        {upload !== null && upload !== undefined && (
          <UploadProgress value={upload} className="mt-3" hint={t('On a slow connection, a smaller or cropped photo uploads faster.')} />
        )}
      </div>
    );
  }
  return null;
}

// --- After the exam ---

// English is the translation key; ResultsScreen passes these through t()
const SUBMIT_MESSAGES = {
  violations: { tone: 'danger', title: 'Your exam was submitted automatically', text: 'The violation limit was reached. Your examiner can see what was recorded.' },
  time_up: { tone: 'warn', title: 'Time ran out', text: 'Your exam was submitted with the answers you had saved.' },
};

function ResultsScreen({ results, submitReason }) {
  const { t } = useI18n();
  const attempt = results.attempt || {};
  const exam = results.exam || {};
  const answerMap = Object.fromEntries((attempt.answers || []).map((a) => [a.question_id, a.answer_data]));
  const objective = (exam.questions || []).filter((q) => !isManual(q.type));
  const objectivePoints = objective.reduce((sum, q) => sum + (q.max_score || 0), 0);
  const manual = (exam.questions || []).some((q) => isManual(q.type));
  const reason = SUBMIT_MESSAGES[submitReason || attempt.submit_reason];
  const pose = (submitReason || attempt.submit_reason) === 'violations' ? 'careful' : attempt.results_released === false ? 'thinking' : 'submitted';

  // The server marks each answer once the answers are out (fill-in and number answers need its rules)
  const isCorrect = (q) => (typeof q.is_correct === 'boolean' ? q.is_correct : null);

  return (
    <div className="min-h-screen bg-paper">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-5 py-5">
        <Logo />
        <Link to="/student-account" className="btn btn-secondary btn-sm">{t('Back to exams')}</Link>
      </header>
      <main className="mx-auto max-w-2xl px-5 pb-16 pt-6">
        <div className="flex items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow mb-2">{t('Submitted')}</p>
            <h1 className="text-3xl font-semibold tracking-tight">{exam.title}</h1>
          </div>
          <Paige pose={pose} className="-mb-3 h-24 w-24 shrink-0 sm:h-28 sm:w-28" />
        </div>

        {reason && <Alert tone={reason.tone} title={t(reason.title)} className="mt-6">{t(reason.text)}</Alert>}

        {attempt.results_released === false ? (
          <Card className="mt-6 p-6">
            <p className="font-semibold">{t('Results aren’t released yet')}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted">{t('Your answers are saved. Your score will appear under Results once your examiner releases it.')}</p>
          </Card>
        ) : (
        <Card className="mt-6 flex flex-wrap items-center justify-between gap-6 p-6">
          <div>
            <p className="text-sm text-muted">{manual ? t('Score so far') : t('Your score')}</p>
            {manual && objectivePoints === 0 ? (
              <p className="mt-1 text-2xl font-semibold tracking-tight">{t('Awaiting grading')}</p>
            ) : (
              <p className="tabular mt-1 text-4xl font-semibold tracking-tight">
                {attempt.score ?? 0}
                <span className="text-xl font-normal text-muted"> / {manual ? objectivePoints : attempt.total_possible_score}</span>
              </p>
            )}
          </div>
          <p className="max-w-xs text-sm leading-relaxed text-muted">
            {manual
              ? t('Questions with a set answer are graded. Written and image answers are graded by your examiner; check Results later for your final score.')
              : t('All questions were graded automatically.')}
          </p>
        </Card>
        )}

        <h2 className="mb-3 mt-10 text-[15px] font-semibold">{t('Your answers')}</h2>
        {exam.answers_revealed === false && (
          <Alert tone="info" className="mb-4">{t('Correct answers are shown after the exam closes for everyone ({{date}}).', { date: formatExamTime(exam.end_time) })}</Alert>
        )}
        <div className="space-y-2.5">
          {(exam.questions || []).map((q, i) => {
            const correct = isCorrect(q);
            return (
              <Card key={q.id} className="px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <p dir="auto" className="text-sm font-medium"><span className="tabular me-2 text-muted">{i + 1}.</span><MathText text={q.title} /></p>
                  {correct === true && <Badge tone="brand">{t('Correct')}</Badge>}
                  {correct === false && <Badge tone="danger">{t('Incorrect')}</Badge>}
                  {correct === null && isManual(q.type) && <Badge>{t('Graded later')}</Badge>}
                </div>
                <p className="mt-2 text-sm text-muted">{t('Your answer:')} <span className="text-ink">{answerText(q.type, answerMap[q.id], t) ?? '—'}</span></p>
                {exam.answers_revealed && q.correct_answers != null && correct === false && (
                  <p className="mt-1 text-sm text-muted">{t('Correct answer:')} <span className="font-medium text-brand">{keyText(q.type, q.correct_answers, t)}</span></p>
                )}
              </Card>
            );
          })}
        </div>
      </main>
    </div>
  );
}

// --- The page ---

function ExamPage() {
  const { id: examIdParam, attemptId: resumeAttemptId } = useParams();
  const navigate = useNavigate();
  const { refreshSession } = useAuth();
  const { t, tn } = useI18n();

  const [phase, setPhase] = useState('loading'); // loading | rules | running | finished | error
  const [meta, setMeta] = useState(null); // exam summary for the rules screen
  const [session, setSession] = useState(null); // { exam, attempt, integrity } from start/resume
  const [answers, setAnswers] = useState({});
  const [current, setCurrent] = useState(0);
  const [flagged, setFlagged] = useState(new Set());
  const [secondsLeft, setSecondsLeft] = useState(null);
  const [imageUpload, setImageUpload] = useState(null); // { questionId, value 0..1 } while a photo uploads
  const [saveStatus, setSaveStatus] = useState(null);
  const [waiting, setWaiting] = useState(0); // answers kept on this computer, not yet on the server
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState(null);
  const [submitReason, setSubmitReason] = useState(null);
  const [showWarning, setShowWarning] = useState(false);
  const [sectionLeft, setSectionLeft] = useState(null); // seconds left in the open section (timed sections)
  const [sectionNotice, setSectionNotice] = useState(null); // { timedOut, from, to } after moving on
  const [confirmFinish, setConfirmFinish] = useState(false);
  const [finishingSection, setFinishingSection] = useState(false);
  const sectionDeadline = useRef(null);
  const advancing = useRef(false);
  const [questionLeft, setQuestionLeft] = useState(null); // seconds left on the open question (per-question exams)
  const [confirmSkip, setConfirmSkip] = useState(false); // moving on from an unanswered question
  const questionDeadline = useRef(null);
  const [timeNotice, setTimeNotice] = useState(null); // extra minutes, after staff gave more time
  const checkingClock = useRef(false);

  const deadline = useRef(null);
  const saveTimers = useRef({}); // questionId -> { id, flush } for written answers waiting to be saved
  const finishing = useRef(false);
  const queue = useRef(null); // offline-tolerant answer queue for this attempt (see answerQueue.js)
  const attemptId = session?.attempt?.id;

  // Load the exam summary (and any unfinished attempt) for the rules screen
  useEffect(() => {
    Promise.all([api.get('/student/exams/'), api.get('/student/unfinished-attempts/')])
      .then(([examsRes, unfinishedRes]) => {
        const attempt = resumeAttemptId
          ? unfinishedRes.data.find((a) => a.id === resumeAttemptId)
          : unfinishedRes.data.find((a) => a.exam_id === examIdParam);
        const examId = resumeAttemptId ? attempt?.exam_id : examIdParam;
        const exam = examsRes.data.find((e) => e.id === examId);
        if (!exam) throw new Error(t('This exam is not available to you.'));
        if (exam.is_submitted && !attempt) throw new Error(t("You've already submitted this exam."));
        setMeta({ ...exam, resumeAttemptId: attempt?.id });
        setPhase('rules');
      })
      .catch((err) => {
        setError(err.response ? errorMessage(err) : err.message);
        setPhase('error');
      });
  }, [examIdParam, resumeAttemptId, t]);

  const finish = useCallback(async (reason) => {
    if (finishing.current) return;
    finishing.current = true;
    Object.values(saveTimers.current).forEach((pending) => clearTimeout(pending.id));
    queue.current?.clear();
    if (reason) setSubmitReason(reason);
    exitFullscreen();
    setPhase('finished');
    try {
      const res = await api.get(`/student/attempts/${attemptId}/results`);
      setResults(res.data);
    } catch (err) {
      setError(errorMessage(err, 'Your exam was submitted, but the results could not be loaded.'));
    }
  }, [attemptId]);

  const integrity = useExamIntegrity({
    attemptId,
    settings: session?.integrity,
    active: phase === 'running',
    initialViolations: session?.integrity?.violations || 0,
    onSubmitted: (reason) => finish(reason),
  });

  // Show the warning banner for a few seconds after each violation
  useEffect(() => {
    if (!integrity.lastViolation) return undefined;
    setShowWarning(true);
    const t = setTimeout(() => setShowWarning(false), 7000);
    return () => clearTimeout(t);
  }, [integrity.lastViolation]);

  // The server's remaining times, counted down here: the exam's and, with timed sections, the open section's
  const applyClocks = useCallback((data) => {
    deadline.current = Date.now() + data.exam.time_remaining_seconds * 1000;
    setSecondsLeft(data.exam.time_remaining_seconds);
    const open = (data.exam.sections || []).find((section) => section.state === 'open');
    sectionDeadline.current = open && open.seconds_left != null ? Date.now() + open.seconds_left * 1000 : null;
    setSectionLeft(open?.seconds_left ?? null);
    const step = data.exam.progress;
    questionDeadline.current = step?.seconds_left != null ? Date.now() + step.seconds_left * 1000 : null;
    setQuestionLeft(step?.seconds_left ?? null);
  }, []);

  const start = async () => {
    setError('');
    setStarting(true);
    // Fullscreen and clipboard access must happen directly in the click, before any network call
    if (meta.integrity?.require_fullscreen) enterFullscreen();
    if (meta.integrity?.block_copy_paste) clearClipboard();
    try {
      const res = meta.resumeAttemptId
        ? await api.post(`/student/attempts/${meta.resumeAttemptId}/resume`)
        : await api.post(`/student/exams/${meta.id}/start`);

      if (res.data.exam?.auto_submitted) {
        setSession(res.data);
        setSubmitReason('time_up');
        exitFullscreen();
        setPhase('finished');
        setResults((await api.get(`/student/attempts/${res.data.attempt.id}/results`)).data);
        return;
      }

      const id = res.data.attempt.id;
      const saved = await api.get(`/student/attempts/${id}/answers`);
      queue.current?.stop();
      queue.current = createAnswerQueue({
        attemptId: id,
        storage: await openStorage(),
        send: (row) => {
          const photo = Boolean(row.value && typeof row.value === 'object' && row.value.preview);
          const body = { question_id: row.questionId, answer_data: row.value, client_seq: row.seq };
          if (!photo) return api.post(`/student/attempts/${id}/save-answer`, body);
          // Photos are big: show the real upload progress
          return api.post(`/student/attempts/${id}/save-answer`, body, {
            onUploadProgress: (e) => { if (e.total) setImageUpload({ questionId: row.questionId, value: e.loaded / e.total }); },
          }).finally(() => setImageUpload(null));
        },
        onChange: ({ status, waiting: n }) => { setSaveStatus(status); setWaiting(n); },
        onClosed: () => finish(),
      });
      // Anything this computer kept from a previous visit is newer than the server's copy
      const unsent = await queue.current.restore();
      setAnswers({ ...Object.fromEntries(saved.data.map((a) => [a.question_id, a.answer_data])), ...unsent });
      try {
        setFlagged(new Set(JSON.parse(sessionStorage.getItem(`flagged:${res.data.attempt.id}`) || '[]')));
      } catch {
        // nothing flagged
      }
      applyClocks(res.data);
      setSession(res.data);
      setPhase('running');
    } catch (err) {
      exitFullscreen();
      setError(errorMessage(err, 'Could not start the exam'));
    } finally {
      setStarting(false);
    }
  };

  const submit = useCallback(async () => {
    setSubmitting(true);
    try {
      // Send any answer still waiting for its typing pause
      await Promise.all(Object.values(saveTimers.current).map((pending) => pending.flush()));
      if (queue.current && !(await queue.current.flush())) {
        setConfirmSubmit(false);
        setError(t("You're offline, so your exam can't be submitted yet. Your answers are kept on this computer. Reconnect and press Submit again."));
        return;
      }
      const res = await api.post(`/student/attempts/${attemptId}/submit`);
      setConfirmSubmit(false);
      finish(res.data.submit_reason);
    } catch (err) {
      if (err.response?.status === 400) finish(); // already submitted (e.g. by the violation limit)
      else setError(errorMessage(err, 'Could not submit. Check your connection and try again.'));
    } finally {
      setSubmitting(false);
    }
  }, [attemptId, finish, t]);

  // Close the open section (Finish section, or its time ran out) and carry on in the next one
  const advanceSection = useCallback(async (timedOut) => {
    const open = (session?.exam?.sections || []).find((section) => section.state === 'open');
    if (!open || advancing.current) return;
    advancing.current = true;
    setFinishingSection(true);
    try {
      await Promise.all(Object.values(saveTimers.current).map((pending) => pending.flush()));
      await queue.current?.flush();
      // On time-out the server has already closed it; resuming hands over the next section
      const res = timedOut
        ? await api.post(`/student/attempts/${attemptId}/resume`)
        : await api.post(`/student/attempts/${attemptId}/sections/${open.id}/finish`);
      setConfirmFinish(false);
      if (res.data.exam?.auto_submitted) return finish('time_up');
      const next = (res.data.exam.sections || []).find((section) => section.state === 'open');
      applyClocks(res.data);
      setSession(res.data);
      if (next?.id === open.id) return; // this computer's clock ran ahead: the server still has it open
      setCurrent(0);
      setSectionNotice({ timedOut, from: open.title, to: next?.title });
    } catch (err) {
      setError(errorMessage(err, 'Could not move to the next section. Check your connection and try again.'));
    } finally {
      advancing.current = false;
      setFinishingSection(false);
    }
  }, [attemptId, session, finish, applyClocks]);

  // Per-question exams: lock the open question (Next, or its time ran out) and open the next one
  const advanceQuestion = useCallback(async (timedOut) => {
    const open = session?.exam?.questions?.[0];
    if (!open || advancing.current) return;
    advancing.current = true;
    setFinishingSection(true);
    try {
      await Promise.all(Object.values(saveTimers.current).map((pending) => pending.flush()));
      await queue.current?.flush();
      const res = timedOut
        ? await api.post(`/student/attempts/${attemptId}/resume`)
        : await api.post(`/student/attempts/${attemptId}/questions/${open.id}/next`);
      setConfirmSkip(false);
      if (res.data.exam?.auto_submitted) return finish('time_up');
      applyClocks(res.data);
      setSession(res.data);
      setCurrent(0);
    } catch (err) {
      setError(errorMessage(err, 'Could not open the next question. Check your connection and try again.'));
    } finally {
      advancing.current = false;
      setFinishingSection(false);
    }
  }, [attemptId, session, finish, applyClocks]);

  // The open question's countdown: when it ends, the next question opens (after the last, the exam is submitted)
  useEffect(() => {
    if (phase !== 'running' || session?.exam?.timing_mode !== 'per_question') return undefined;
    const tick = setInterval(() => {
      if (questionDeadline.current == null) return;
      const left = Math.max(0, Math.round((questionDeadline.current - Date.now()) / 1000));
      setQuestionLeft(left);
      if (left > 0) return;
      questionDeadline.current = null;
      const step = session.exam.progress;
      if (step && step.position === step.total - 1) submit();
      else advanceQuestion(true);
    }, 1000);
    return () => clearInterval(tick);
  }, [phase, session, submit, advanceQuestion]);

  // The open section's countdown: when it ends, the next section opens (or, after the last, the exam is submitted)
  useEffect(() => {
    if (phase !== 'running' || !session?.exam?.timed_sections) return undefined;
    const tick = setInterval(() => {
      if (sectionDeadline.current == null) return;
      const left = Math.max(0, Math.round((sectionDeadline.current - Date.now()) / 1000));
      setSectionLeft(left);
      if (left > 0) return;
      sectionDeadline.current = null;
      const sections = session.exam.sections;
      if (sections[sections.length - 1]?.state === 'open') submit();
      else advanceSection(true);
    }, 1000);
    return () => clearInterval(tick);
  }, [phase, session, submit, advanceSection]);

  // The server's time left: staff may have given extra time while the student writes (task 4.11)
  const checkClock = useCallback(async () => {
    try {
      const { data } = await api.get(`/student/attempts/${attemptId}/clock`);
      if (data.submitted) return false;
      const later = Date.now() + data.time_remaining_seconds * 1000;
      if (later - deadline.current > 30 * 1000) setTimeNotice(data.extra_minutes);
      deadline.current = later;
      setSecondsLeft(data.time_remaining_seconds);
      return data.time_remaining_seconds > 0;
    } catch {
      return false; // offline or unreachable: submit as before, which waits for the connection
    }
  }, [attemptId]);

  // Countdown from the server's remaining time; at zero it asks the server once more, then submits
  useEffect(() => {
    if (phase !== 'running') return undefined;
    const tick = setInterval(() => {
      const left = Math.max(0, Math.round((deadline.current - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left > 0 || checkingClock.current) return;
      checkingClock.current = true;
      checkClock().then((more) => {
        checkingClock.current = false;
        if (more) return;
        clearInterval(tick);
        submit();
      });
    }, 1000);
    return () => clearInterval(tick);
  }, [phase, submit, checkClock]);

  // Pick up extra time early, not only when the clock runs out
  useEffect(() => {
    if (phase !== 'running') return undefined;
    const poll = setInterval(checkClock, 60 * 1000);
    return () => clearInterval(poll);
  }, [phase, checkClock]);

  // Keep the student signed in for the whole exam
  useEffect(() => {
    if (phase !== 'running') return undefined;
    refreshSession();
    const keepAlive = setInterval(refreshSession, 60 * 1000);
    return () => clearInterval(keepAlive);
  }, [phase, refreshSession]);

  const persist = useCallback((questionId, value) => queue.current?.enqueue(questionId, value), []);

  // Send what's waiting as soon as the connection comes back; stop the queue when leaving
  useEffect(() => {
    if (phase !== 'running') return undefined;
    const online = () => queue.current?.flush();
    window.addEventListener('online', online);
    return () => window.removeEventListener('online', online);
  }, [phase]);
  useEffect(() => () => queue.current?.stop(), []);

  const answer = (questionId, value, { debounce = false } = {}) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
    clearTimeout(saveTimers.current[questionId]?.id);
    delete saveTimers.current[questionId];
    if (!debounce) {
      persist(questionId, value);
      return;
    }
    setSaveStatus('saving');
    // setTimeout returns a plain number in browsers, so keep the timer and its flush together
    const pending = {
      id: setTimeout(() => pending.flush(), TEXT_SAVE_DELAY),
      flush: () => {
        clearTimeout(pending.id);
        delete saveTimers.current[questionId];
        return persist(questionId, value);
      },
    };
    saveTimers.current[questionId] = pending;
  };

  const uploadImage = (questionId, file) => {
    if (file.size > MAX_IMAGE_BYTES) {
      setError(t('That image is larger than 2 MB. Take a smaller photo or crop it.'));
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => answer(questionId, {
      name: file.name, size: file.size, type: file.type, lastModified: file.lastModified, preview: e.target.result,
    });
    reader.readAsDataURL(file);
  };

  const toggleFlag = (questionId) => {
    const next = new Set(flagged);
    next.has(questionId) ? next.delete(questionId) : next.add(questionId);
    setFlagged(next);
    try {
      sessionStorage.setItem(`flagged:${attemptId}`, JSON.stringify([...next]));
    } catch {
      // flags just won't survive a reload
    }
  };

  const questions = useMemo(() => session?.exam?.questions || [], [session]);
  const answeredCount = questions.filter((q) => isAnswered(answers[q.id])).length;

  // Keyboard: number keys choose an answer, arrow keys move, F flags. Typing in an answer box is left alone.
  useEffect(() => {
    if (phase !== 'running') return undefined;
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || integrity.blocked || confirmSubmit) return;
      if (e.target.closest?.('input[type="text"], textarea, select, [contenteditable="true"]')) return;
      const q = questions[current];
      if (!q) return;
      const rtl = document.documentElement.dir === 'rtl';
      const [nextKey, prevKey] = rtl ? ['ArrowLeft', 'ArrowRight'] : ['ArrowRight', 'ArrowLeft'];
      const stepping = session?.exam?.timing_mode === 'per_question';
      if (!stepping && e.key === nextKey && current < questions.length - 1) { e.preventDefault(); setCurrent(current + 1); return; }
      if (!stepping && e.key === prevKey && current > 0) { e.preventDefault(); setCurrent(current - 1); return; }
      if (!stepping && e.key.toLowerCase() === 'f') { e.preventDefault(); toggleFlag(q.id); return; }
      const n = Number(e.key);
      const choosable = ['single_choice', 'multi_choice', 'true_false'].includes(q.type);
      const option = choosable && Number.isInteger(n) && n >= 1 ? q.options?.[n - 1] : undefined;
      if (option === undefined) return;
      e.preventDefault();
      if (q.type === 'single_choice' || q.type === 'true_false') answer(q.id, option);
      if (q.type === 'multi_choice') {
        const selected = Array.isArray(answers[q.id]) ? answers[q.id] : [];
        answer(q.id, selected.includes(option) ? selected.filter((o) => o !== option) : [...selected, option]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if (phase === 'loading') return <div className="min-h-screen bg-paper"><PageLoader variant="exam" /></div>;

  if (phase === 'error') {
    return (
      <div className="grid min-h-screen place-items-center bg-paper p-6">
        <Card className="max-w-md p-8 text-center">
          <LuCircleAlert className="mx-auto h-8 w-8 text-muted" />
          <p className="mt-4 font-medium">{error}</p>
          <Button variant="secondary" className="mt-6" onClick={() => navigate('/student-account')}>{t('Back to exams')}</Button>
        </Card>
      </div>
    );
  }

  if (phase === 'rules') {
    return <RulesScreen exam={meta} resuming={Boolean(meta.resumeAttemptId)} onStart={start} starting={starting} error={error} />;
  }

  if (phase === 'finished') {
    if (results) return <ResultsScreen results={results} submitReason={submitReason} />;
    return (
      <div className="min-h-screen bg-paper">
        {error ? <div className="mx-auto max-w-md p-10"><Alert tone="warn">{error}</Alert></div> : <PageLoader label={t('Submitting…')} />}
      </div>
    );
  }

  const question = questions[current];
  const isLast = current === questions.length - 1;
  const remainingViolations = integrity.maxViolations ? integrity.maxViolations - integrity.violations : null;

  const sections = session.exam.sections || [];
  const openSection = sections.find((section) => section.state === 'open');
  const lastSectionOpen = openSection && sections[sections.length - 1]?.id === openSection.id;
  const sectionOf = question && sections.find((section) => section.id === question.section_id);
  const step = session.exam.timing_mode === 'per_question' ? session.exam.progress : null;
  const lastStep = step && step.position === step.total - 1;
  const moveOn = () => (isAnswered(answers[question?.id]) ? advanceQuestion(false) : setConfirmSkip(true));

  const typeLabel = {
    single_choice: t('Single answer'), multi_choice: t('Multiple answers'), true_false: t('True or false'),
    fill_blank: t('Fill in the blank'), numeric: t('Number answer'), matching: t('Matching'), ordering: t('Put in order'),
    text: t('Written answer'), image_upload: t('Image answer'),
  };

  return (
    <div className={cx('min-h-screen bg-paper', session.integrity.block_copy_paste && 'select-none [-webkit-touch-callout:none]')}>
      {integrity.blocked && <BlockedOverlay integrity={integrity} />}

      {/* A static blur (never animated) while the questions are hidden; nothing behind it can be clicked or focused */}
      <div
        className={cx('grid min-h-screen grid-rows-[auto_1fr_auto]', integrity.blocked && 'pointer-events-none blur-md')}
        inert={integrity.blocked}
        aria-hidden={integrity.blocked || undefined}
      >
        <header className="sticky top-0 z-30 border-b border-line bg-surface">
          <div className="flex items-center gap-5 px-6 py-3">
            <LogoMark size={22} />
            <p className="min-w-0 flex-1 truncate text-sm font-medium">
              {session.exam.title}
              {/* With timed sections only the open one's questions are here, so count the whole exam */}
              <span className="ms-3 font-mono text-xs font-normal text-faint">{tn(step ? step.total : sections.length ? sections.reduce((n, section) => n + section.question_count, 0) : questions.length, '{{count}} question', '{{count}} questions')}</span>
            </p>
            <SaveStatus status={saveStatus} waiting={waiting} />
            <ViolationChip count={integrity.violations} max={integrity.maxViolations} />
            {session.exam.timed_sections && openSection && sectionLeft != null && <SectionTimer title={openSection.title} seconds={sectionLeft} />}
            <Timer seconds={secondsLeft ?? 0} />
          </div>
          {saveStatus === 'offline' && (
            <div className="border-t border-warn/25 bg-warn-soft px-4 py-2 text-center text-sm text-warn-ink" role="status">
              {t("You're offline. Keep going: your answers are kept on this computer and sent when you reconnect.")}
            </div>
          )}
          {showWarning && (
            <div className="border-t border-danger/25 bg-danger-soft px-4 py-2 text-center text-sm text-danger-ink" role="alert">
              {integrity.maxViolations
                ? t('Violation recorded ({{n}} of {{max}}).', { n: integrity.violations, max: integrity.maxViolations })
                : t('Violation recorded ({{n}}).', { n: integrity.violations })}
              {remainingViolations === 1 && ` ${t('One more and your exam is submitted automatically.')}`}
              {remainingViolations > 1 && ` ${t('{{n}} more and your exam is submitted automatically.', { n: remainingViolations })}`}
            </div>
          )}
        </header>

        <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_300px]">
          <main className="min-w-0 px-8 pb-12 pt-12">
            <div className="mx-auto max-w-[42rem]">
              {error && <Alert tone="danger" className="mb-6" onClose={() => setError('')}>{error}</Alert>}
              {timeNotice != null && (
                <Alert tone="info" className="mb-6" onClose={() => setTimeNotice(null)} title={t('You have more time')}>
                  {t('Your examiner gave you extra time: {{n}} minutes in all. The timer shows your new time left.', { n: timeNotice })}
                </Alert>
              )}
              {sectionNotice && (
                <Alert
                  tone="info"
                  className="mb-6"
                  onClose={() => setSectionNotice(null)}
                  title={sectionNotice.timedOut ? t('Time’s up for {{section}}', { section: sectionNotice.from }) : t('{{section}} has started', { section: sectionNotice.to })}
                >
                  {sectionNotice.timedOut
                    ? t('{{next}} has started. {{done}} is closed and its answers are saved.', { next: sectionNotice.to, done: sectionNotice.from })
                    : t('{{done}} is closed and its answers are saved.', { done: sectionNotice.from })}
                </Alert>
              )}
              {question && integrity.blocked && <HiddenQuestion />}
              {question && !integrity.blocked && (
                <article>
                  {sectionOf && (
                    <div className="mb-5">
                      <p className="eyebrow">{sectionOf.title}</p>
                      {sectionOf.instructions && <p dir="auto" className="mt-1.5 max-w-[62ch] text-sm leading-relaxed text-muted">{sectionOf.instructions}</p>}
                    </div>
                  )}
                  <div className="flex items-baseline gap-4 border-b border-line-strong pb-3.5">
                    <span className="tabular font-mono text-[2.5rem] font-semibold leading-[0.9] tracking-[-0.02em]">{String((step ? step.position : current) + 1).padStart(2, '0')}</span>
                    <span className="font-mono text-xs leading-relaxed text-faint">
                      <b className="font-medium text-muted">{typeLabel[question.type] || t('Question')}</b> · {tn(question.max_score, '{{count}} mark', '{{count}} marks')}
                      <br />{step ? t('Question {{n}} of {{total}}', { n: step.position + 1, total: step.total }) : t('Question {{n}} of {{total}}', { n: current + 1, total: questions.length })}
                    </span>
                    {step && questionLeft != null && <QuestionTimer seconds={questionLeft} />}
                    {!step && <Button
                      variant="ghost"
                      size="sm"
                      className={cx('ms-auto', flagged.has(question.id) && 'text-danger hover:text-danger')}
                      onClick={() => toggleFlag(question.id)}
                      aria-pressed={flagged.has(question.id)}
                    >
                      {flagged.has(question.id) ? t('Flagged for review') : t('Flag for review')}
                    </Button>}
                  </div>
                  <QuestionText question={question} value={answers[question.id]} onChange={(value, opts) => answer(question.id, value, opts)} />
                  <QuestionBody
                    question={question}
                    value={answers[question.id]}
                    onChange={(value, opts) => answer(question.id, value, opts)}
                    onImage={(file) => uploadImage(question.id, file)}
                    upload={imageUpload?.questionId === question.id ? imageUpload.value : null}
                    onPickFile={integrity.allowFilePicker}
                  />
                  {['single_choice', 'multi_choice', 'true_false'].includes(question.type) && (
                    <p className="mt-5 flex flex-wrap items-center gap-2 font-mono text-xs text-faint" aria-hidden="true">
                      <span className="kbd">1</span>–<span className="kbd">{Math.min(9, question.options?.length || 1)}</span> {t('choose')}
                      {!step && <> · <span className="kbd">←</span><span className="kbd">→</span> {t('move')} · <span className="kbd">F</span> {t('flag')}</>}
                    </p>
                  )}
                </article>
              )}
            </div>
          </main>

          <aside className="border-s border-line bg-surface px-7 py-8" aria-label={t('Questions')}>
            <div className="sticky top-24">
              {step ? (
                <>
                  <p className="tabular font-mono text-xs text-muted"><b className="block text-xl font-semibold text-ink">{t('{{n}} of {{total}}', { n: step.position + 1, total: step.total })}</b>{t('question')}</p>
                  <div className="mt-5"><StepMap progress={step} /></div>
                </>
              ) : (
                <>
                  <p className="tabular font-mono text-xs text-muted"><b className="block text-xl font-semibold text-ink">{t('{{n}} of {{total}}', { n: answeredCount, total: questions.length })}</b>{t('answered')}</p>
                  <div className="mt-5">
                    <QuestionNav questions={questions} answers={answers} flagged={flagged} current={current} onJump={setCurrent} sections={sections} />
                  </div>
                </>
              )}
            </div>
          </aside>
        </div>

        <footer className="sticky bottom-0 z-20 flex items-center gap-3 border-t border-line bg-surface px-6 py-3">
          {!step && (
            <>
              <Button variant="secondary" disabled={current === 0} onClick={() => setCurrent(current - 1)}>{t('Previous')}</Button>
              <Button variant="secondary" disabled={isLast} onClick={() => setCurrent(current + 1)}>{t('Next')}</Button>
            </>
          )}
          <span className="flex-1" />
          {step && !lastStep
            ? <Button onClick={moveOn} loading={finishingSection}>{t('Next question')}</Button>
            : session.exam.timed_sections && openSection && !lastSectionOpen
            ? <Button onClick={() => setConfirmFinish(true)}>{t('Finish section')}</Button>
            : <Button onClick={() => setConfirmSubmit(true)}>{t('Submit exam')}</Button>}
        </footer>
      </div>

      <Modal
        open={confirmSkip}
        onClose={() => setConfirmSkip(false)}
        title={t('Move on without answering?')}
        description={t("You can't come back to this question.")}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmSkip(false)}>{t('Stay on it')}</Button>
            <Button onClick={() => advanceQuestion(false)} loading={finishingSection}>{t('Next question')}</Button>
          </>
        }
      />

      <Modal
        open={confirmFinish}
        onClose={() => setConfirmFinish(false)}
        title={t('Finish {{section}}?', { section: openSection?.title || '' })}
        description={t("You can't come back to this section. Questions you haven't answered stay unanswered.")}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmFinish(false)}>{t('Keep working')}</Button>
            <Button onClick={() => advanceSection(false)} loading={finishingSection}>{t('Finish section')}</Button>
          </>
        }
      >
        <div className="space-y-2 text-sm">
          <p className="flex justify-between"><span className="text-muted">{t('Answered')}</span><span className="tabular font-medium">{t('{{n}} of {{total}}', { n: answeredCount, total: questions.length })}</span></p>
          {sectionLeft != null && <p className="flex justify-between"><span className="text-muted">{t('Time left in this section')}</span><span className="tabular font-mono">{formatClock(sectionLeft)}</span></p>}
          {answeredCount < questions.length && (
            <Alert tone="warn" className="mt-3">{tn(questions.length - answeredCount, '{{count}} question is unanswered.', '{{count}} questions are unanswered.')}</Alert>
          )}
        </div>
      </Modal>

      <Modal
        open={confirmSubmit}
        onClose={() => setConfirmSubmit(false)}
        title={t('Submit your exam?')}
        description={t("You can't change your answers after submitting.")}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmSubmit(false)}>{t('Keep working')}</Button>
            <Button onClick={submit} loading={submitting}>{t('Submit exam')}</Button>
          </>
        }
      >
        <div className="space-y-2 text-sm">
          <p className="flex justify-between"><span className="text-muted">{t('Answered')}</span><span className="tabular font-medium">{t('{{n}} of {{total}}', { n: answeredCount, total: questions.length })}</span></p>
          {flagged.size > 0 && <p className="flex justify-between"><span className="text-muted">{t('Flagged for review')}</span><span className="tabular font-medium">{flagged.size}</span></p>}
          <p className="flex justify-between"><span className="text-muted">{t('Time left')}</span><span className="tabular font-mono">{formatClock(secondsLeft ?? 0)}</span></p>
          {answeredCount < questions.length && (
            <Alert tone="warn" className="mt-3">{tn(questions.length - answeredCount, '{{count}} question is unanswered.', '{{count}} questions are unanswered.')}</Alert>
          )}
        </div>
      </Modal>
    </div>
  );
}

export default ExamPage;
