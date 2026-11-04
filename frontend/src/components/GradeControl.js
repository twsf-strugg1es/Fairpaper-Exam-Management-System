import React, { forwardRef, useRef, useState } from 'react';
import { LuCheck } from 'react-icons/lu';
import api from '../api';
import { Input, cx } from './ui';
import { parseNumber } from '../questionTypes';
import { errorMessage } from '../utils';
import { useI18n } from '../i18n';

const COMMENT_LIMIT = 100;
const round = (n) => Math.round(n * 100) / 100;

// The mark for one written or image answer: quick buttons for none, half and full marks, a box for any mark in
// between, and a comment for the student. A quick button saves at once; the box and the comment save on Enter
// or when they lose focus. Enter in the box also moves on (onNext), so a pile of answers can be marked by keyboard.
const GradeControl = forwardRef(function GradeControl({ answerId, worth, score, comment, onSaved, onNext }, ref) {
  const { t } = useI18n();
  const [saved, setSaved] = useState({ score: score ?? null, comment: comment || '' });
  const [mark, setMark] = useState(score == null ? '' : String(score));
  const [note, setNote] = useState(comment || '');
  const [status, setStatus] = useState('idle'); // idle | saving | saved | error
  const [error, setError] = useState('');
  // The mark and comment last sent: leaving the box and pressing Enter both save, but the same values go once
  const sent = useRef(score == null ? null : `${score}|${comment || ''}`);

  const save = async (nextMark = mark, nextNote = note) => {
    if (String(nextMark).trim() === '' && saved.score === null) return true; // nothing given yet
    const value = parseNumber(nextMark);
    if (value === null || value < 0 || value > worth) {
      setStatus('error');
      setError(t('Give a mark from 0 to {{n}}.', { n: worth }));
      return false;
    }
    const next = { score: round(value), comment: nextNote.trim() };
    const key = `${next.score}|${next.comment}`;
    if (key === sent.current) return true;
    sent.current = key;
    setStatus('saving');
    setError('');
    try {
      const { data } = await api.post(`/admin/evaluations/answers/${answerId}/submit`, { score_awarded: next.score, comment: next.comment });
      const stored = { score: data.score_awarded, comment: next.comment };
      setSaved(stored);
      setMark(String(stored.score));
      setStatus('saved');
      onSaved?.(answerId, stored);
      return true;
    } catch (err) {
      sent.current = saved.score === null ? null : `${saved.score}|${saved.comment}`; // let the same values be tried again
      setStatus('error');
      setError(errorMessage(err, 'Could not save the mark. Try again.'));
      return false;
    }
  };

  const quick = [
    { value: 0, label: '0', name: t('No marks') },
    ...(worth >= 1 ? [{ value: round(worth / 2), label: String(round(worth / 2)), name: t('Half marks') }] : []),
    { value: worth, label: String(worth), name: t('Full marks') },
  ];
  const current = parseNumber(mark);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1" role="group" aria-label={t('Quick marks')}>
          {quick.map((q) => (
            <button
              key={q.name}
              type="button"
              onClick={() => { setMark(String(q.value)); save(q.value); }}
              className={cx('btn btn-sm tabular min-w-[2.5rem] border', current === q.value && saved.score === q.value ? 'border-brand bg-brand text-on-brand' : 'border-line-strong bg-surface hover:bg-sunken')}
              aria-label={`${q.name} (${q.value})`}
            >
              {q.label}
            </button>
          ))}
        </div>
        <label className="ms-2 flex items-center gap-2 text-sm text-muted">
          <span className="sr-only">{t('Mark')}</span>
          <Input
            ref={ref}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={mark}
            onChange={(e) => { setMark(e.target.value); if (status === 'error') setStatus('idle'); }}
            onBlur={() => save()}
            onKeyDown={async (e) => {
              if (e.key !== 'Enter') return;
              e.preventDefault();
              if (await save()) onNext?.();
            }}
            className="tabular h-8 w-16 px-2 text-center"
            aria-invalid={status === 'error' || undefined}
            aria-label={t('Mark out of {{n}}', { n: worth })}
          />
          <span className="tabular">/ {worth}</span>
        </label>
        <span className="ms-auto flex items-center gap-1.5 text-xs" aria-live="polite">
          {status === 'saving' && <span className="text-muted">{t('Saving…')}</span>}
          {status === 'saved' && <span className="flex items-center gap-1 text-brand"><LuCheck className="h-3.5 w-3.5" />{t('Saved')}</span>}
          {status === 'idle' && saved.score === null && <span className="text-muted">{t('Not graded yet')}</span>}
        </span>
      </div>
      <div>
        <Input
          type="text"
          value={note}
          maxLength={COMMENT_LIMIT}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => save(mark, note)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); save(mark, note); } }}
          placeholder={t('Comment for the student (optional)')}
          aria-label={t('Comment for the student')}
          className="h-9"
        />
        {note.length > COMMENT_LIMIT - 20 && <p className="hint text-end">{note.length}/{COMMENT_LIMIT}</p>}
      </div>
      {status === 'error' && error && <p className="text-sm text-danger" role="alert">{error}</p>}
    </div>
  );
});

export default GradeControl;
