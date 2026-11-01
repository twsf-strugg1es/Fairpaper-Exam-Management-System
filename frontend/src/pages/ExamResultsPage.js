import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { LuArrowLeft, LuCalendar, LuClock, LuUsers, LuSearch, LuShieldAlert, LuPencil, LuInbox, LuFileSpreadsheet, LuPrinter } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import { Alert, Badge, Button, Card, Input, Stat, Tabs, EmptyState, ErrorState, PageLoader, NoResults } from '../components/ui';
import { ProtectionIcons, StatusBadge } from './AdminExamsPage';
import { useToast } from '../components/Toaster';
import { errorMessage, formatDateTime, formatDuration, formatExamTime, percent, suggestCorrection } from '../utils';
import { isManual } from '../questionTypes';
import { useI18n } from '../i18n';

export const RISK = {
  clean: { label: 'Clean', tone: 'brand' },
  review: { label: 'Review', tone: 'warn' },
  high: { label: 'High risk', tone: 'danger' },
};

export const SUBMIT_REASONS = {
  student: 'Submitted',
  time_up: 'Time ran out',
  violations: 'Auto-submitted for violations',
};

export function RiskBadge({ integrity }) {
  const { t } = useI18n();
  if (!integrity) return null;
  const risk = RISK[integrity.risk] || RISK.clean;
  return <Badge tone={risk.tone}>{t(risk.label)}</Badge>;
}

// Whether students can see their scores yet, and the button to release (or take back) them
function ResultsRelease({ exam, onChange, onError }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const mode = exam.results_release || 'immediate';
  if (mode === 'immediate') return null;
  const toggle = async () => {
    setBusy(true);
    try {
      const res = await (exam.results_released_at ? api.delete : api.post)(`/admin/exams/${exam.id}/results/release`);
      onChange({ ...exam, ...res.data });
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const visible = exam.results_visible;
  return (
    <Card className="mb-6 flex flex-wrap items-center justify-between gap-4 px-5 py-4">
      <div className="flex items-center gap-3">
        <Badge tone={visible ? 'brand' : 'warn'}>{visible ? t('Results released') : t('Results hidden')}</Badge>
        <p className="text-sm text-muted">
          {visible
            ? t('Students can see their scores and, once the exam has closed, the correct answers.')
            : mode === 'on_close'
              ? t('Students see their scores when the exam closes. Release them now to show them sooner.')
              : t('Students see that their exam was submitted, but not their score, until you release the results.')}
        </p>
      </div>
      {(exam.results_released_at || !visible) && (
        <Button size="sm" variant={exam.results_released_at ? 'secondary' : 'primary'} loading={busy} onClick={toggle}>
          {exam.results_released_at ? t('Hide results again') : t('Release results')}
        </Button>
      )}
    </Card>
  );
}

// Ranked by score, then time taken; candidates level on both share a rank (PRD AC17)
function MeritList({ examId }) {
  const { t } = useI18n();
  const [merit, setMerit] = useState(null);
  useEffect(() => {
    api.get(`/admin/exams/${examId}/merit`).then((res) => setMerit(res.data)).catch(() => setMerit({ rows: [] }));
  }, [examId]);
  if (!merit || merit.rows.length === 0) return null;
  return (
    <Card className="mt-6 overflow-hidden">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-5 pb-3 pt-4">
        <h2 className="text-[15px] font-semibold">{t('Merit list')}</h2>
        <p className="text-xs text-muted">
          {merit.closed ? t('Ranked by score, then by time taken.') : t('Provisional: the exam is still open.')}
        </p>
      </div>
      <div className="overflow-x-auto border-t border-line">
        <table className="table">
          <thead>
            <tr><th className="w-20">{t('Rank')}</th><th>{t('Student')}</th><th className="text-end">{t('Score')}</th><th className="text-end">{t('Time taken')}</th></tr>
          </thead>
          <tbody>
            {merit.rows.map((r) => (
              <tr key={r.attempt_id}>
                <td className="font-mono font-semibold tabular-nums">
                  {r.rank}{r.tied && <span className="ms-1 text-xs font-normal text-muted" title={t('Tied')}>=</span>}
                </td>
                <td>
                  <p className="font-medium">{r.student.full_name || r.student.email}</p>
                  {r.student.full_name && <p className="text-xs text-muted">{r.student.email}</p>}
                </td>
                <td className="text-end tabular-nums">{r.score} / {r.total_possible_score} <span className="ms-1 text-xs text-muted">{Math.round(r.percentage)}%</span></td>
                <td className="text-end tabular-nums text-muted">{formatDuration(r.time_taken_seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ExamResultsPage() {
  const { examId } = useParams();
  const { t, tn } = useI18n();
  const [exam, setExam] = useState(null);
  const [attempts, setAttempts] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [exporting, setExporting] = useState(false);
  const toast = useToast();
  const [loadFailure, setLoadFailure] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    Promise.all([api.get('/admin/exams/'), api.get(`/admin/exams/${examId}/attempts`)])
      .then(([examsRes, attemptsRes]) => {
        setExam(examsRes.data.find((e) => e.id === examId) || null);
        setAttempts(attemptsRes.data);
      })
      .catch((err) => setLoadFailure(err)); // an error, not "no attempts yet"
  }, [examId, reload]);

  const needsGrading = exam?.questions?.some((q) => isManual(q.type));

  const exportExcel = async () => {
    setExporting(true);
    try {
      const res = await api.get(`/admin/exams/${examId}/export.xlsx`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(exam?.title || 'Exam').replace(/[\\/:*?"<>|]+/g, ' ').trim()} results.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ title: t('Results downloaded'), body: t('“{{file}}” is in your downloads: results, marks by question, the questions and the exam, one sheet each.', { file: a.download }) });
    } catch (err) {
      setError(errorMessage(err, t('Could not export the results. Try again.')));
    } finally {
      setExporting(false);
    }
  };

  const stats = useMemo(() => {
    const list = attempts || [];
    const submitted = list.filter((a) => a.is_submitted);
    const flagged = list.filter((a) => a.integrity?.risk !== 'clean');
    const avg = submitted.length
      ? Math.round(submitted.reduce((sum, a) => sum + percent(a.score, a.total_possible_score), 0) / submitted.length)
      : null;
    return { started: list.length, submitted: submitted.length, flagged: flagged.length, avg };
  }, [attempts]);

  const shown = (attempts || [])
    .filter((a) => filter === 'all' || (filter === 'review' ? a.integrity?.risk !== 'clean' : !a.is_submitted))
    .filter((a) => {
      const q = search.toLowerCase();
      return !q || a.student?.email?.toLowerCase().includes(q) || a.student?.full_name?.toLowerCase().includes(q);
    })
    // Highest risk first, then by score
    .sort((a, b) => ['high', 'review', 'clean'].indexOf(a.integrity?.risk) - ['high', 'review', 'clean'].indexOf(b.integrity?.risk)
      || (b.score || 0) - (a.score || 0));

  if (loadFailure) {
    return (
      <AppShell>
        <ErrorState error={loadFailure} onRetry={() => { setLoadFailure(null); setReload((n) => n + 1); }} action={<Link to="/admin-exams" className="btn btn-secondary">{t('Back to exams')}</Link>} />
      </AppShell>
    );
  }
  if (attempts === null) return <AppShell><PageLoader variant="detail" /></AppShell>;

  return (
    <AppShell>
      <Link to="/admin-exams" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {t('Exams')}
      </Link>

      {error && <Alert tone="danger" className="mb-6">{error}</Alert>}

      {exam && (
        <div className="mb-8">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{exam.title}</h1>
            <StatusBadge exam={exam} />
            <div className="ms-auto flex flex-wrap gap-2">
              {stats.submitted > 0 && (needsGrading || exam.pool_rules?.length > 0) && (
                <Link to={`/admin-exams/${examId}/grade`} className="btn btn-primary btn-sm"><LuPencil className="h-4 w-4" /> {t('Grade by question')}</Link>
              )}
              <Button variant="secondary" size="sm" icon={LuFileSpreadsheet} loading={exporting} onClick={exportExcel}>{t('Export to Excel')}</Button>
              {stats.submitted > 0 && (
                <Link to={`/admin-exams/${examId}/cards`} className="btn btn-secondary btn-sm"><LuPrinter className="h-4 w-4" /> {t('Result cards')}</Link>
              )}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm text-muted">
            <span className="flex items-center gap-1.5"><LuCalendar className="h-3.5 w-3.5" />{formatDateTime(exam.start_time)} – {formatExamTime(exam.end_time)}</span>
            <span className="flex items-center gap-1.5"><LuClock className="h-3.5 w-3.5" />{t('{{n}} min', { n: exam.duration_minutes })}</span>
            <span className="flex items-center gap-1.5"><LuUsers className="h-3.5 w-3.5" />{exam.groups?.length ? exam.groups.map((g) => g.name).join(', ') : t('Everyone')}</span>
            <ProtectionIcons exam={exam} />
          </div>
        </div>
      )}

      {exam && <ResultsRelease exam={exam} onChange={setExam} onError={setError} />}

      <Card className="mb-6 grid grid-cols-2 gap-6 p-5 sm:grid-cols-4">
        <Stat label={t('Started')} value={stats.started} />
        <Stat label={t('Submitted')} value={stats.submitted} />
        <Stat label={t('Average score')} value={stats.avg === null ? '—' : `${stats.avg}%`} />
        <Stat label={t('Need review')} value={stats.flagged} tone={stats.flagged ? 'danger' : undefined} hint={t('Integrity flags or violations')} />
      </Card>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-end justify-between gap-3 px-4 pt-3">
          <Tabs
            value={filter}
            onChange={setFilter}
            className="border-b-0"
            tabs={[
              { value: 'all', label: t('All'), count: attempts.length },
              { value: 'review', label: t('Needs review'), count: stats.flagged },
              { value: 'progress', label: t('In progress'), count: attempts.length - stats.submitted },
            ]}
          />
          <div className="relative mb-2 w-full sm:w-64">
            <LuSearch className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search students')} className="h-9 ps-9" />
          </div>
        </div>

        {attempts.length === 0 ? (
          <EmptyState icon={LuInbox} paige="sleeping" title={t('No attempts yet')} className="border-t border-line">
            {t("Students' attempts appear here as soon as they start the exam.")}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto border-t border-line">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Student')}</th>
                  <th>{t('Status')}</th>
                  <th className="text-end">{t('Score')}</th>
                  <th>{t('Integrity')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {shown.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <p className="font-medium">{a.student?.full_name || a.student?.email}</p>
                      {a.student?.full_name && <p className="text-xs text-muted">{a.student.email}</p>}
                    </td>
                    <td>
                      {a.is_submitted ? (
                        <>
                          <p className={a.submit_reason === 'violations' ? 'font-medium text-danger' : ''}>
                            {t(SUBMIT_REASONS[a.submit_reason] || 'Submitted')}
                          </p>
                          <p className="text-xs text-muted">{formatDateTime(a.submitted_at)}</p>
                        </>
                      ) : (
                        <Badge tone="info">{t('In progress')}</Badge>
                      )}
                    </td>
                    <td className="tabular whitespace-nowrap text-end">
                      {a.is_submitted ? (
                        <>
                          <span className="font-medium">{a.score}</span>
                          <span className="text-muted"> / {a.total_possible_score}</span>
                          {needsGrading && !a.is_evaluated && <p className="text-xs text-warn">{t('Not graded yet')}</p>}
                        </>
                      ) : '—'}
                    </td>
                    <td>
                      <div className="flex flex-wrap items-center gap-2">
                        <RiskBadge integrity={a.integrity} />
                        {a.integrity?.violations > 0 && (
                          <span className="text-xs text-muted">
                            {tn(a.integrity.violations, '{{count}} violation', '{{count}} violations')}
                            {a.integrity.seconds_away > 0 && ` · ${t('away {{time}}', { time: formatDuration(a.integrity.seconds_away) })}`}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <Link to={`/admin-integrity/${a.id}`} className="btn btn-ghost btn-sm">
                          <LuShieldAlert className="h-4 w-4" /> {t('Report')}
                        </Link>
                        {a.is_submitted && (
                          <Link to={`/admin-exams/${examId}/cards?attempt=${a.id}`} className="btn btn-ghost btn-sm" aria-label={t('Result card for {{name}}', { name: a.student?.full_name || a.student?.email })}>
                            <LuPrinter className="h-4 w-4" /> {t('Card')}
                          </Link>
                        )}
                        {needsGrading && a.is_submitted && (
                          <Link to={`/admin-evaluate-answers/${a.id}`} className="btn btn-secondary btn-sm">
                            <LuPencil className="h-4 w-4" /> {t('Grade')}
                          </Link>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {shown.length === 0 && (
              <NoResults
                query={search}
                suggestion={search ? suggestCorrection(search, attempts.flatMap((a) => [a.student?.full_name, a.student?.email])) : null}
                onSuggest={setSearch}
                onClear={() => { setSearch(''); setFilter('all'); }}
              >
                {t('No attempts match this filter.')}
              </NoResults>
            )}
          </div>
        )}
      </Card>

      <MeritList examId={examId} />
    </AppShell>
  );
}

export default ExamResultsPage;
