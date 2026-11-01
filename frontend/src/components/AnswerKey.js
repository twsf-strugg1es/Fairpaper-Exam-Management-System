import React from 'react';
import { LuArrowRight, LuCheck } from 'react-icons/lu';
import { cx } from './ui';
import { isManual } from '../questionTypes';
import { useI18n } from '../i18n';

const BOX = 'rounded-lg border px-3 py-2 text-sm';

// A question's answer key, read-only, as the question bank shows it
export default function AnswerKey({ question }) {
  const { t } = useI18n();
  const { type, options, correct_answers: key } = question;
  if (isManual(type) || key == null) {
    return <p className="rounded-lg bg-sunken px-4 py-3 text-sm text-muted">{t('Graded by an examiner after the exam.')}</p>;
  }

  if (type === 'single_choice' || type === 'multi_choice' || type === 'true_false') {
    const correct = [].concat(key).map(String);
    const list = type === 'true_false' ? ['true', 'false'] : options || [];
    return (
      <ul className="space-y-1.5">
        {list.map((option) => {
          const right = correct.includes(String(option));
          return (
            <li key={option} className={cx(BOX, 'flex items-center justify-between gap-3', right ? 'border-brand/40 bg-brand-soft/50' : 'border-line')}>
              {type === 'true_false' ? (option === 'true' ? t('True') : t('False')) : option}
              {right && <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-brand-ink"><LuCheck className="h-3.5 w-3.5" />{t('Correct')}</span>}
            </li>
          );
        })}
      </ul>
    );
  }

  if (type === 'fill_blank') {
    return (
      <ul className="space-y-1.5">
        {key.map((accepted, i) => (
          <li key={i} className={cx(BOX, 'flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-line')}>
            <span className="text-muted">{key.length > 1 ? t('Blank {{n}}', { n: i + 1 }) : t('The blank')}</span>
            <span className="font-medium">{accepted.join(' / ')}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (type === 'numeric') {
    return (
      <p className={cx(BOX, 'tabular border-brand/40 bg-brand-soft/50 font-medium')}>
        {key.tolerance ? `${key.value} ± ${key.tolerance}` : key.value}
      </p>
    );
  }

  if (type === 'matching') {
    const used = Object.values(key);
    const extras = (options?.right || []).filter((match) => !used.includes(match));
    return (
      <div>
        <ul className="space-y-1.5">
          {Object.entries(key).map(([item, match]) => (
            <li key={item} className={cx(BOX, 'flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-line')}>
              <span>{item}</span>
              <span className="flex items-center gap-2 font-medium"><LuArrowRight className="h-3.5 w-3.5 text-faint rtl:-scale-x-100" aria-hidden />{match}</span>
            </li>
          ))}
        </ul>
        {extras.length > 0 && <p className="mt-2 text-xs text-muted">{t('Also offered: {{list}}', { list: extras.join(', ') })}</p>}
      </div>
    );
  }

  if (type === 'ordering') {
    return (
      <ol className="space-y-1.5">
        {key.map((item, i) => (
          <li key={item} className={cx(BOX, 'flex items-center gap-3 border-line')}>
            <span className="tabular w-5 shrink-0 font-mono text-muted">{i + 1}.</span>
            {item}
          </li>
        ))}
      </ol>
    );
  }
  return null;
}
