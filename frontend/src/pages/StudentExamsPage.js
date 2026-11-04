import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { LuAward, LuArrowRight } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import { Card, Stat, EmptyState, ErrorState, PageHeader, PageLoader, cx } from '../components/ui';
import { formatDate } from '../utils';
import { useI18n } from '../i18n';

const scoreTone = (pct) => (pct >= 80 ? 'text-brand' : pct >= 50 ? 'text-warn' : 'text-danger');

// The student's submitted exams in the current organization
function StudentExamsPage() {
  const { t } = useI18n();
  const [exams, setExams] = useState(null);
  const [loadFailure, setLoadFailure] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.get('/student/completed-exams/')
      .then((res) => setExams([...res.data].sort((a, b) => new Date(b.end_time) - new Date(a.end_time))))
      .catch((err) => setLoadFailure(err)); // an error, not "no results yet"
  }, [reload]);

  // Averages count only the exams whose results have been released
  const scored = (exams || []).filter((e) => e.results_released !== false);
  const average = scored.length ? Math.round(scored.reduce((sum, e) => sum + (e.percentage || 0), 0) / scored.length) : null;
  const best = scored.length ? Math.max(...scored.map((e) => e.percentage || 0)) : null;

  return (
    <AppShell>
      <PageHeader title={t('Results')} description={t('Scores include written answers once your examiner has graded them.')} />
      {loadFailure ? (
        <Card><ErrorState error={loadFailure} onRetry={() => { setLoadFailure(null); setReload((n) => n + 1); }} /></Card>
      ) : exams === null ? (
        <PageLoader />
      ) : exams.length === 0 ? (
        <Card>
          <EmptyState icon={LuAward} paige="thinking" title={t('No results yet')}>{t('Your scores appear here after you submit an exam.')}</EmptyState>
        </Card>
      ) : (
        <>
          <Card className="mb-6 grid grid-cols-3 gap-6 p-5">
            <Stat label={t('Exams taken')} value={exams.length} />
            <Stat label={t('Average')} value={average === null ? '—' : `${average}%`} />
            <Stat label={t('Best')} value={best === null ? '—' : `${Math.round(best)}%`} tone="brand" />
          </Card>
          <Card className="divide-y divide-line overflow-hidden">
            {exams.map((exam) => (
              <Link
                key={exam.id}
                to={`/exam-results/${exam.id}`}
                className="group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-sunken/50"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{exam.exam_title}</p>
                  <p className="mt-0.5 text-xs text-muted">{formatDate(exam.end_time)}</p>
                </div>
                {exam.results_released === false ? (
                  <span className="text-sm text-muted">{t('Results not released yet')}</span>
                ) : (
                  <div className="text-end">
                    <p className={cx('tabular text-lg font-semibold', scoreTone(exam.percentage))}>{Math.round(exam.percentage)}%</p>
                    <p className="tabular text-xs text-muted">{exam.score} / {exam.total_possible_score}</p>
                  </div>
                )}
                <LuArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" />
              </Link>
            ))}
          </Card>
        </>
      )}
    </AppShell>
  );
}

export default StudentExamsPage;
