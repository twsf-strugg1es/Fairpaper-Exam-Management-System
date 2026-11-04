import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  LuArrowLeft, LuMonitorOff, LuHistory, LuMinimize, LuClipboard, LuMousePointerClick, LuKeyboard,
  LuMonitorSmartphone, LuShieldCheck, LuInfo, LuPencil,
} from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import { Badge, Card, Stat, CardHeader, EmptyState, ErrorState, PageLoader, cx } from '../components/ui';
import { RISK, SUBMIT_REASONS } from './ExamResultsPage';
import { formatClock, formatDateTime, formatDuration } from '../utils';
import { useI18n } from '../i18n';

const PASTE_ACTIONS = {
  copy: 'Tried to copy (blocked)',
  cut: 'Tried to cut (blocked)',
  paste: 'Tried to paste (blocked)',
  drop: 'Tried to drop text in (blocked)',
  middle_click: 'Tried a middle-click paste (blocked)',
  insertFromPaste: 'Tried to paste from the menu (blocked)',
  insertFromPasteAsQuotation: 'Tried to paste from the menu (blocked)',
  insertFromDrop: 'Tried to drop text in (blocked)',
  insertFromYank: 'Tried to paste (blocked)',
};

const EVENT_INFO = {
  focus_lost: {
    icon: LuMonitorOff,
    label: (d, t) => (d?.tab_hidden ? t('Switched tab or minimized the browser') : t('Switched to another window or app')),
  },
  focus_returned: { icon: LuHistory, label: (d, t) => t('Came back after {{time}}', { time: formatDuration((d?.away_ms || 0) / 1000) }) },
  fullscreen_exit: { icon: LuMinimize, label: (d, t) => t('Exited fullscreen') },
  copy_paste: { icon: LuClipboard, label: (d, t) => t(PASTE_ACTIONS[d?.action] || 'Tried to copy or paste (blocked)') },
  context_menu: { icon: LuMousePointerClick, label: (d, t) => t('Right-clicked (blocked)') },
  blocked_shortcut: { icon: LuKeyboard, label: (d, t) => (d?.key ? t('Pressed {{key}}', { key: d.key }) : t('Pressed a blocked shortcut')) },
  multiple_screens: { icon: LuMonitorSmartphone, label: (d, t) => t('More than one screen connected') },
};

const RISK_EXPLANATIONS = {
  clean: 'Nothing was recorded during this attempt.',
  review: 'Some activity was recorded. Look at the timeline to judge whether it matters.',
  high: 'Auto-submitted, three or more violations, or at least a minute spent away from the exam.',
};

function IntegrityReportPage() {
  const { attemptId } = useParams();
  const { t } = useI18n();
  const [report, setReport] = useState(null);
  const [loadFailure, setLoadFailure] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.get(`/admin/attempts/${attemptId}/integrity`)
      .then((res) => setReport(res.data))
      .catch((err) => setLoadFailure(err));
  }, [attemptId, reload]);

  if (loadFailure) {
    return (
      <AppShell width="narrow">
        <ErrorState error={loadFailure} onRetry={() => { setLoadFailure(null); setReload((n) => n + 1); }} action={<Link to="/admin-exams" className="btn btn-secondary">{t('Back to exams')}</Link>} />
      </AppShell>
    );
  }
  if (!report) return <AppShell width="narrow"><PageLoader variant="detail" /></AppShell>;

  const { summary, student, exam, attempt, events } = report;
  const risk = RISK[summary.risk];
  const settings = [
    exam.require_fullscreen && t('Fullscreen required'),
    exam.block_copy_paste && t('Copy/paste blocked'),
    (exam.shuffle_questions || exam.shuffle_options) && t('Shuffled'),
    exam.max_violations ? t('Auto-submit after {{n}}', { n: exam.max_violations }) : t('No auto-submit'),
  ].filter(Boolean);

  return (
    <AppShell width="narrow">
      <Link to={`/admin-exams/${exam.id}`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {exam.title}
      </Link>

      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow mb-1.5">{t('Integrity report')}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{student.full_name || student.email}</h1>
          <p className="mt-1 text-sm text-muted">{student.full_name && `${student.email} · `}{t('Started {{date}}', { date: formatDateTime(attempt.start_time) })}</p>
        </div>
        <Badge tone={risk.tone} className="px-3 py-1 text-sm">{t(risk.label)}</Badge>
      </div>

      <Card className="mb-6">
        <div className="grid grid-cols-2 gap-6 p-5 sm:grid-cols-4">
          <Stat label={t('Violations')} value={summary.violations} tone={summary.violations ? 'danger' : undefined} hint={exam.max_violations ? t('limit {{n}}', { n: exam.max_violations }) : t('no limit')} />
          <Stat label={t('Flags')} value={summary.flags} hint={t('copy, right-click, keys')} />
          <Stat label={t('Time away')} value={formatDuration(summary.seconds_away)} />
          <Stat
            label={t('Ended')}
            value={<span className="text-base">{attempt.end_time ? t(SUBMIT_REASONS[attempt.submit_reason] || 'Submitted') : t('In progress')}</span>}
            hint={attempt.end_time ? formatDateTime(attempt.end_time) : undefined}
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3">
          <p className="text-sm text-muted">{t(RISK_EXPLANATIONS[summary.risk])}</p>
          <div className="flex flex-wrap gap-1.5">{settings.map((s) => <Badge key={s}>{s}</Badge>)}</div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title={t('Timeline')}
          description={t("Times are minutes:seconds after the attempt started, by the server's clock.")}
          action={
            attempt.end_time && (
              <Link to={`/admin-evaluate-answers/${attempt.id}`} className="btn btn-secondary btn-sm">
                <LuPencil className="h-4 w-4" /> {t('Answers')}
              </Link>
            )
          }
        />
        {events.length === 0 ? (
          <EmptyState icon={LuShieldCheck} paige="careful" title={t('No events recorded')}>
            {t('The student stayed in the exam, in fullscreen, the whole time.')}
          </EmptyState>
        ) : (
          <ol className="relative px-5 py-4">
            <span className="absolute bottom-6 start-[38px] top-6 w-px bg-line" aria-hidden />
            {events.map((event, i) => {
              const info = EVENT_INFO[event.type] || { icon: LuInfo, label: () => event.type };
              const Icon = info.icon;
              return (
                <li key={i} className="relative flex items-start gap-4 py-2.5">
                  <span
                    className={cx(
                      'relative z-[1] grid h-7 w-7 shrink-0 place-items-center rounded-full ring-4 ring-surface',
                      event.is_violation ? 'bg-danger-soft text-danger' : 'bg-sunken text-muted',
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  <span className="min-w-0 flex-1 pt-0.5">
                    <span className="flex flex-wrap items-center gap-2 text-sm">
                      <span className={event.is_violation ? 'font-medium' : ''}>{info.label(event.details, t)}</span>
                      {event.is_violation && <Badge tone="danger">{t('Violation')}</Badge>}
                    </span>
                  </span>
                  <span className="tabular pt-1 font-mono text-xs text-muted">{formatClock(event.seconds_into_attempt)}</span>
                </li>
              );
            })}
          </ol>
        )}
      </Card>

      <p className="mt-6 flex gap-2 text-xs leading-relaxed text-muted">
        <LuInfo className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        {t('These are signals, not proof. A notification or an accidental key press can take focus away too. Use the report together with the answers before deciding anything.')}
      </p>
    </AppShell>
  );
}

export default IntegrityReportPage;
