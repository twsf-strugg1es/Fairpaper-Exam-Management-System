import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LuCheck, LuX } from 'react-icons/lu';
import api from '../api';
import { useAuth } from '../context/AuthContext';
import { msg, useI18n } from '../i18n';
import { Button, Card, cx } from './ui';

// The four steps from the first-use journey (03 App Flow), in order
const STEPS = [
  { key: 'students', title: msg('Invite your students'), body: msg('Share your join code, or import a list of emails.'), action: msg('Invite students'), to: '/admin-organization', manager: true },
  { key: 'groups', title: msg('Put them in groups'), body: msg('A group is a class or batch. Exams go to the groups you choose.'), action: msg('Create a group'), to: '/admin-organization', manager: true },
  { key: 'questions', title: msg('Add questions'), body: msg('Write them one at a time, or import a spreadsheet.'), action: msg('Open the question bank'), to: '/admin-questions' },
  { key: 'exams', title: msg('Create your first exam'), body: msg('Pick questions, set the time window, and choose who takes it.'), action: msg('New exam'), to: '/admin-exams/new' },
];

const hiddenKey = (orgId) => `setupHidden:${orgId}`;

// "Get started" checklist on the Exams page. Disappears once all four steps are done, or
// when someone hides it (remembered in this browser, per organization).
export default function GetStarted({ onVisible }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { currentMembership, isManager } = useAuth();
  const organizationId = currentMembership?.organization_id;
  const [progress, setProgress] = useState(null);
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem(hiddenKey(organizationId)) === '1'; } catch { return false; }
  });

  useEffect(() => {
    let live = true;
    api.get('/org/setup').then((res) => live && setProgress(res.data)).catch(() => live && setProgress(null));
    return () => { live = false; };
  }, [organizationId]);

  const visible = Boolean(progress && !progress.done && !hidden);
  useEffect(() => { onVisible?.(visible); }, [visible, onVisible]);
  if (!visible) return null;

  const doneCount = STEPS.filter((s) => progress.steps[s.key]).length;
  const nextKey = STEPS.find((s) => !progress.steps[s.key])?.key;
  const hide = () => {
    try { localStorage.setItem(hiddenKey(organizationId), '1'); } catch { /* hidden for this visit only */ }
    setHidden(true);
  };

  return (
    <Card className="mb-6 overflow-hidden" role="region" aria-labelledby="get-started-title">
      <div className="flex items-start justify-between gap-4 px-6 pb-4 pt-5">
        <div>
          <h2 id="get-started-title" className="text-lg font-semibold tracking-[-0.01em]">{t('Get started')}</h2>
          <p className="mt-1 text-sm text-muted">{t('Four steps to your first exam.')}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-muted tabular-nums">{t('{{n}} of 4 done', { n: doneCount })}</span>
          <Button variant="ghost" size="sm" icon={LuX} aria-label={t('Hide this checklist')} title={t('Hide this checklist')} onClick={hide} />
        </div>
      </div>
      <div className="flex gap-1 px-6 pb-1" aria-hidden="true">
        {STEPS.map((s) => (
          <span key={s.key} className={cx('h-1 flex-1 rounded-full', progress.steps[s.key] ? 'bg-brand' : 'bg-line')} />
        ))}
      </div>
      <ol className="mt-3 divide-y divide-line border-t border-line">
        {STEPS.map((s, i) => {
          const done = progress.steps[s.key];
          const allowed = !s.manager || isManager;
          return (
            <li key={s.key} className={cx('flex items-center gap-4 px-6 py-4', s.key === nextKey && 'bg-brand-soft/40')}>
              <span
                className={cx(
                  'grid h-8 w-8 shrink-0 place-items-center rounded-full border-[1.5px] font-mono text-xs font-semibold',
                  done ? 'border-brand bg-brand text-on-brand' : 'border-line-strong text-muted',
                )}
                aria-hidden="true"
              >
                {done ? <LuCheck className="h-4 w-4" /> : String(i + 1).padStart(2, '0')}
              </span>
              <div className="min-w-0 flex-1">
                <p className={cx('font-medium', done && 'text-muted line-through decoration-line-strong')}>
                  {t(s.title)}
                  <span className="sr-only">{done ? ` (${t('done')})` : ` (${t('to do')})`}</span>
                </p>
                {!done && <p className="mt-0.5 text-sm text-muted">{t(s.body)}</p>}
              </div>
              {!done && (allowed ? (
                <Button size="sm" variant={s.key === nextKey ? 'primary' : 'secondary'} onClick={() => navigate(s.to)}>{t(s.action)}</Button>
              ) : (
                <span className="text-xs text-muted">{t('An admin does this')}</span>
              ))}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
