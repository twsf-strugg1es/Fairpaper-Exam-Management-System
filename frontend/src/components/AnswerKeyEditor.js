import React, { useRef } from 'react';
import { LuArrowDown, LuArrowRight, LuArrowUp, LuCheck, LuPlus, LuX } from 'react-icons/lu';
import { Alert, Button, Card, CardHeader, Field, Input, cx } from './ui';
import { blankCount, parseNumber } from '../questionTypes';
import { useI18n } from '../i18n';

// The answer key of a question in the editor, one card per type. The form keeps a field per type, so switching
// type and back loses nothing; keyPayload() sends only the current type's key.

const CHOICE_TYPES = ['single_choice', 'multi_choice'];
const MAX_ITEMS = 10;
const MAX_MATCHES = 15;
const LETTERS = 'ABCDEFGHIJ';

export const EMPTY_KEY = {
  options: ['', '', '', ''],
  correct: [],
  truth: '',
  blanks: [['']],
  number: { value: '', tolerance: '0' },
  pairs: [{ left: '', right: '' }, { left: '', right: '' }, { left: '', right: '' }],
  extras: [],
  items: ['', '', ''],
};

const strings = (list) => (Array.isArray(list) ? list.map(String) : []);

// The editor's fields for a stored question
export const keyFromQuestion = ({ type, options, correct_answers: key }) => {
  switch (type) {
    case 'single_choice':
    case 'multi_choice': {
      const list = strings(options);
      return { options: list.length ? list : EMPTY_KEY.options, correct: key == null ? [] : [].concat(key).map(String) };
    }
    case 'true_false': return { truth: key === 'true' || key === 'false' ? key : '' };
    case 'fill_blank': return { blanks: Array.isArray(key) && key.length ? key.map((accepted) => strings(accepted)) : [['']] };
    case 'numeric': return { number: { value: String(key?.value ?? ''), tolerance: String(key?.tolerance ?? 0) } };
    case 'matching': {
      const used = new Set(Object.values(key || {}));
      return {
        pairs: strings(options?.left).map((left) => ({ left, right: key?.[left] ?? '' })),
        extras: strings(options?.right).filter((right) => !used.has(right)),
      };
    }
    case 'ordering': return { items: strings(Array.isArray(key) && key.length ? key : options) };
    default: return {};
  }
};

const trim = (list) => list.map((v) => v.trim());
const blanksOf = (form) => Array.from({ length: blankCount(form.title) }, (_, i) => form.blanks[i] || ['']);

// What the API stores for the current type: { options, correct_answers }
export const keyPayload = (form) => {
  switch (form.type) {
    case 'single_choice': return { options: trim(form.options), correct_answers: (form.correct[0] || '').trim() };
    case 'multi_choice': return { options: trim(form.options), correct_answers: trim(form.correct) };
    case 'true_false': return { options: null, correct_answers: form.truth };
    case 'fill_blank': return { options: null, correct_answers: blanksOf(form).map((accepted) => trim(accepted).filter(Boolean)) };
    // Sent as typed: the server reads "9,8" and Bengali digits the same way it reads students' answers
    case 'numeric': return { options: null, correct_answers: { value: form.number.value.trim(), tolerance: form.number.tolerance.trim() || '0' } };
    case 'matching': {
      const pairs = form.pairs.map((p) => ({ left: p.left.trim(), right: p.right.trim() }));
      return {
        options: { left: pairs.map((p) => p.left), right: [...pairs.map((p) => p.right), ...trim(form.extras).filter(Boolean)] },
        correct_answers: Object.fromEntries(pairs.map((p) => [p.left, p.right])),
      };
    }
    case 'ordering': return { options: trim(form.items), correct_answers: trim(form.items) };
    default: return { options: null, correct_answers: null };
  }
};

const hasDuplicates = (list) => new Set(list).size !== list.length;

// The checks the server makes (question_types.clean), so the teacher sees them before saving
export const keyProblem = (form, t) => {
  if (CHOICE_TYPES.includes(form.type)) {
    const options = trim(form.options);
    if (options.some((o) => !o)) return t('Fill in every option or remove the empty ones.');
    if (options.length < 2) return t('Add at least two options.');
    if (hasDuplicates(options)) return t('Two options have the same text.');
    if (!form.correct.some((c) => options.includes(c.trim()))) return t('Mark the correct answer.');
    return null;
  }
  switch (form.type) {
    case 'true_false':
      return form.truth ? null : t('Mark whether the statement is true or false.');
    case 'fill_blank': {
      const blanks = blanksOf(form).map((accepted) => trim(accepted).filter(Boolean));
      if (blanks.some((accepted) => accepted.length === 0)) return t('Give at least one accepted answer for every blank.');
      if (blanks.some(hasDuplicates)) return t('Two accepted answers for one blank are the same.');
      return null;
    }
    case 'numeric': {
      if (parseNumber(form.number.value) === null) return t('Give the correct answer as a number.');
      const margin = parseNumber(form.number.tolerance.trim() || '0');
      if (margin === null) return t('Give the margin as a number, or 0 for an exact answer.');
      if (margin < 0) return t("The margin can't be negative.");
      return null;
    }
    case 'matching': {
      const pairs = form.pairs.map((p) => [p.left.trim(), p.right.trim()]);
      if (pairs.some(([left, right]) => !left || !right)) return t('Fill in both sides of every pair or remove the empty ones.');
      if (pairs.length < 2) return t('Add at least 2 pairs.');
      if (hasDuplicates(pairs.map(([left]) => left))) return t('Two items to match have the same text.');
      if (hasDuplicates([...pairs.map(([, right]) => right), ...trim(form.extras).filter(Boolean)])) return t('Two matches have the same text.');
      return null;
    }
    case 'ordering': {
      const items = trim(form.items);
      if (items.some((item) => !item)) return t('Fill in every item or remove the empty ones.');
      if (items.length < 2) return t('Add at least 2 items to put in order.');
      if (hasDuplicates(items)) return t('Two items have the same text.');
      return null;
    }
    default:
      return null;
  }
};

const replace = (list, i, value) => list.map((item, j) => (j === i ? value : item));
const without = (list, i) => list.filter((_, j) => j !== i);
const swap = (list, i, j) => {
  const next = [...list];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
};

function ChoiceKey({ form, setForm }) {
  const { t } = useI18n();
  const single = form.type === 'single_choice';
  const setOption = (i, text) => {
    const before = form.options[i];
    // A marked answer follows its option when the text changes
    setForm({ ...form, options: replace(form.options, i, text), correct: form.correct.map((c) => (c === before ? text : c)) });
  };
  const toggleCorrect = (text) => {
    if (single) return setForm({ ...form, correct: [text] });
    setForm({ ...form, correct: form.correct.includes(text) ? form.correct.filter((c) => c !== text) : [...form.correct, text] });
  };
  return (
    <Card>
      <CardHeader
        title={t('Answer options')}
        description={single ? t('Select the bubble of the one correct answer.') : t('Select the bubble of every correct answer.')}
      />
      <ul className="divide-y divide-line">
        {form.options.map((option, i) => {
          const correct = form.correct.includes(option) && option.trim() !== '';
          return (
            <li key={i} className="flex items-center gap-3 px-5 py-3">
              <label className="cursor-pointer">
                <input
                  type={single ? 'radio' : 'checkbox'}
                  name="correct"
                  className="peer sr-only"
                  checked={correct}
                  disabled={!option.trim()}
                  onChange={() => toggleCorrect(option)}
                />
                <span className={cx('bubble peer-focus-visible:ring-2 peer-focus-visible:ring-brand/40', correct && 'bubble-filled')} aria-hidden>{LETTERS[i]}</span>
                <span className="sr-only">{t('Option {{letter}} is correct', { letter: LETTERS[i] })}</span>
              </label>
              <Input value={option} onChange={(e) => setOption(i, e.target.value)} placeholder={t('Option {{letter}}', { letter: LETTERS[i] })} aria-label={t('Option {{letter}}', { letter: LETTERS[i] })} />
              <Button
                variant="ghost"
                size="sm"
                icon={LuX}
                onClick={() => setForm({ ...form, options: without(form.options, i), correct: form.correct.filter((c) => c !== option) })}
                disabled={form.options.length <= 2}
                aria-label={t('Remove option {{letter}}', { letter: LETTERS[i] })}
              />
            </li>
          );
        })}
      </ul>
      {form.options.length < MAX_ITEMS && (
        <div className="border-t border-line px-5 py-3">
          <Button variant="ghost" size="sm" icon={LuPlus} onClick={() => setForm({ ...form, options: [...form.options, ''] })}>{t('Add option')}</Button>
        </div>
      )}
    </Card>
  );
}

function TrueFalseKey({ form, setForm }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader title={t('Correct answer')} description={t('Students choose True or False.')} />
      <div className="grid gap-2 p-5 sm:grid-cols-2" role="radiogroup" aria-label={t('Correct answer')}>
        {['true', 'false'].map((value) => {
          const chosen = form.truth === value;
          return (
            <label
              key={value}
              className={cx('flex cursor-pointer items-center gap-3 rounded border px-4 py-3 text-sm font-medium transition-colors', chosen ? 'border-brand bg-brand-soft text-brand-ink' : 'border-line-strong hover:bg-sunken')}
            >
              <input type="radio" name="truth" className="peer sr-only" checked={chosen} onChange={() => setForm({ ...form, truth: value })} />
              <span className={cx('bubble h-6 w-6 peer-focus-visible:ring-2 peer-focus-visible:ring-brand/40', chosen && 'bubble-filled')} aria-hidden>
                {chosen && <LuCheck className="h-3.5 w-3.5" />}
              </span>
              {value === 'true' ? t('True') : t('False')}
            </label>
          );
        })}
      </div>
    </Card>
  );
}

function FillBlankKey({ form, setForm }) {
  const { t } = useI18n();
  const blanks = blanksOf(form);
  const marked = /_{3,}/.test(form.title);
  // Answers for blanks beyond the current count are kept, in case a ___ comes back while the question is edited
  const setBlank = (i, accepted) => {
    const next = blanks.length > form.blanks.length ? [...blanks] : [...form.blanks];
    next[i] = accepted;
    setForm({ ...form, blanks: next });
  };
  return (
    <Card>
      <CardHeader title={t('Accepted answers')} description={t('Capitals, extra spaces and punctuation around an answer are ignored when grading.')} />
      {!marked && (
        <Alert tone="info" className="mx-5 mt-5">{t('Write ___ (three underscores) in the question where each blank goes. Without one, students answer in a box after the question.')}</Alert>
      )}
      <div className="space-y-6 p-5">
        {blanks.map((accepted, i) => (
          <fieldset key={i} className="min-w-0">
            <legend className="label">{blanks.length > 1 ? t('Blank {{n}}', { n: i + 1 }) : t('The blank')}</legend>
            <ul className="space-y-2">
              {accepted.map((answer, j) => (
                <li key={j} className="flex items-center gap-2">
                  <Input
                    type="text"
                    value={answer}
                    onChange={(e) => setBlank(i, replace(accepted, j, e.target.value))}
                    placeholder={j === 0 ? t('Correct answer') : t('Also accept')}
                    aria-label={t('Accepted answer {{n}} for blank {{blank}}', { n: j + 1, blank: i + 1 })}
                  />
                  <Button variant="ghost" size="sm" icon={LuX} disabled={accepted.length <= 1} onClick={() => setBlank(i, without(accepted, j))} aria-label={t('Remove accepted answer {{n}}', { n: j + 1 })} />
                </li>
              ))}
            </ul>
            {accepted.length < MAX_ITEMS && (
              <Button variant="ghost" size="sm" icon={LuPlus} className="mt-2" onClick={() => setBlank(i, [...accepted, ''])}>{t('Accept another answer')}</Button>
            )}
          </fieldset>
        ))}
      </div>
    </Card>
  );
}

function NumericKey({ form, setForm }) {
  const { t } = useI18n();
  const set = (field) => (e) => setForm({ ...form, number: { ...form.number, [field]: e.target.value } });
  const value = parseNumber(form.number.value);
  const margin = parseNumber(form.number.tolerance.trim() || '0');
  return (
    <Card>
      <CardHeader title={t('Correct answer')} description={t('Students type a number. Bengali digits and a decimal comma are understood.')} />
      <div className="grid gap-5 p-5 sm:grid-cols-2">
        <Field label={t('Answer')} htmlFor="numeric-value">
          <Input id="numeric-value" type="text" inputMode="decimal" autoComplete="off" value={form.number.value} onChange={set('value')} placeholder={t('e.g. 9.8')} />
        </Field>
        <Field label={t('Margin (±)')} htmlFor="numeric-margin" hint={t('Answers this close to the correct one also count. 0 means exact.')}>
          <Input id="numeric-margin" type="text" inputMode="decimal" autoComplete="off" value={form.number.tolerance} onChange={set('tolerance')} />
        </Field>
      </div>
      {value !== null && margin !== null && margin > 0 && (
        <p className="tabular border-t border-line px-5 py-3 text-sm text-muted">{t('Counts as correct: {{low}} to {{high}}', { low: +(value - margin).toPrecision(12), high: +(value + margin).toPrecision(12) })}</p>
      )}
    </Card>
  );
}

function MatchingKey({ form, setForm }) {
  const { t } = useI18n();
  const setPair = (i, side, text) => setForm({ ...form, pairs: replace(form.pairs, i, { ...form.pairs[i], [side]: text }) });
  const room = MAX_MATCHES - form.pairs.length - form.extras.length;
  return (
    <Card>
      <CardHeader title={t('Pairs')} description={t('Write each item and its match. Students pick the match for every item from a shuffled list.')} />
      <ul className="divide-y divide-line">
        {form.pairs.map((pair, i) => (
          <li key={i} className="flex items-center gap-2 px-5 py-3">
            <Input type="text" value={pair.left} onChange={(e) => setPair(i, 'left', e.target.value)} placeholder={t('Item {{n}}', { n: i + 1 })} aria-label={t('Item {{n}}', { n: i + 1 })} className="min-w-0 flex-1" />
            <LuArrowRight className="h-4 w-4 shrink-0 text-faint rtl:-scale-x-100" aria-hidden />
            <Input type="text" value={pair.right} onChange={(e) => setPair(i, 'right', e.target.value)} placeholder={t('Its match')} aria-label={t('Match for item {{n}}', { n: i + 1 })} className="min-w-0 flex-1" />
            <Button variant="ghost" size="sm" icon={LuX} disabled={form.pairs.length <= 2} onClick={() => setForm({ ...form, pairs: without(form.pairs, i) })} aria-label={t('Remove pair {{n}}', { n: i + 1 })} />
          </li>
        ))}
      </ul>
      {form.pairs.length < MAX_ITEMS && room > 0 && (
        <div className="border-t border-line px-5 py-3">
          <Button variant="ghost" size="sm" icon={LuPlus} onClick={() => setForm({ ...form, pairs: [...form.pairs, { left: '', right: '' }] })}>{t('Add pair')}</Button>
        </div>
      )}
      <div className="border-t border-line px-5 py-4">
        <p className="label mb-0.5">{t('Extra matches')} <span className="ms-1.5 font-normal text-muted">{t('optional')}</span></p>
        <p className="hint mt-0 mb-3">{t('Answers that match no item, so the last pair isn’t a free guess.')}</p>
        <ul className="space-y-2">
          {form.extras.map((extra, i) => (
            <li key={i} className="flex items-center gap-2">
              <Input type="text" value={extra} onChange={(e) => setForm({ ...form, extras: replace(form.extras, i, e.target.value) })} aria-label={t('Extra match {{n}}', { n: i + 1 })} />
              <Button variant="ghost" size="sm" icon={LuX} onClick={() => setForm({ ...form, extras: without(form.extras, i) })} aria-label={t('Remove extra match {{n}}', { n: i + 1 })} />
            </li>
          ))}
        </ul>
        {room > 0 && (
          <Button variant="ghost" size="sm" icon={LuPlus} className={cx(form.extras.length > 0 && 'mt-2')} onClick={() => setForm({ ...form, extras: [...form.extras, ''] })}>{t('Add extra match')}</Button>
        )}
      </div>
    </Card>
  );
}

function OrderingKey({ form, setForm }) {
  const { t } = useI18n();
  const list = useRef(null);
  // Focus follows the moved item, so it can be walked up or down with repeated presses
  const move = (i, j, direction) => {
    setForm({ ...form, items: swap(form.items, i, j) });
    requestAnimationFrame(() => {
      const row = list.current?.querySelector(`[data-row="${j}"]`);
      (row?.querySelector(`[data-move="${direction}"]:not(:disabled)`) || row?.querySelector('[data-move]:not(:disabled)'))?.focus();
    });
  };
  return (
    <Card>
      <CardHeader title={t('Items in the correct order')} description={t('Students see them shuffled and put them back in this order.')} />
      <ol ref={list} className="divide-y divide-line">
        {form.items.map((item, i) => (
          <li key={i} data-row={i} className="flex items-center gap-2 px-5 py-3">
            <span className="tabular w-6 shrink-0 font-mono text-sm text-muted">{i + 1}.</span>
            <Input type="text" value={item} onChange={(e) => setForm({ ...form, items: replace(form.items, i, e.target.value) })} placeholder={t('Item {{n}}', { n: i + 1 })} aria-label={t('Item {{n}}', { n: i + 1 })} />
            <Button variant="ghost" size="sm" icon={LuArrowUp} data-move="up" disabled={i === 0} onClick={() => move(i, i - 1, 'up')} aria-label={t('Move item {{n}} up', { n: i + 1 })} />
            <Button variant="ghost" size="sm" icon={LuArrowDown} data-move="down" disabled={i === form.items.length - 1} onClick={() => move(i, i + 1, 'down')} aria-label={t('Move item {{n}} down', { n: i + 1 })} />
            <Button variant="ghost" size="sm" icon={LuX} disabled={form.items.length <= 2} onClick={() => setForm({ ...form, items: without(form.items, i) })} aria-label={t('Remove item {{n}}', { n: i + 1 })} />
          </li>
        ))}
      </ol>
      {form.items.length < MAX_ITEMS && (
        <div className="border-t border-line px-5 py-3">
          <Button variant="ghost" size="sm" icon={LuPlus} onClick={() => setForm({ ...form, items: [...form.items, ''] })}>{t('Add item')}</Button>
        </div>
      )}
    </Card>
  );
}

export default function AnswerKeyEditor({ form, setForm }) {
  const { t } = useI18n();
  if (CHOICE_TYPES.includes(form.type)) return <ChoiceKey form={form} setForm={setForm} />;
  switch (form.type) {
    case 'true_false': return <TrueFalseKey form={form} setForm={setForm} />;
    case 'fill_blank': return <FillBlankKey form={form} setForm={setForm} />;
    case 'numeric': return <NumericKey form={form} setForm={setForm} />;
    case 'matching': return <MatchingKey form={form} setForm={setForm} />;
    case 'ordering': return <OrderingKey form={form} setForm={setForm} />;
    case 'text': return <Alert tone="info">{t('Students type their answer. An examiner grades it.')}</Alert>;
    default: return <Alert tone="info">{t('Students upload a photo of their work. An examiner grades it.')}</Alert>;
  }
}
