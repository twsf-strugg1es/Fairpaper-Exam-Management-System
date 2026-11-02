import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { LuArrowLeft, LuPencil, LuShieldAlert, LuCircleCheck, LuImage } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import GradeControl from '../components/GradeControl';
import MathText from '../components/MathText';
import { Badge, Card, EmptyState, ErrorState, PageLoader, cx } from '../components/ui';
import { QUESTION_TYPE_LABELS, formatDateTime } from '../utils';
import { useI18n } from '../i18n';

function AnswerCard({ answer, index, onSaved }) {
  const { t, tn } = useI18n();
  const max = answer.question_max_score;
  return (
    <Card className={cx('overflow-hidden', answer.is_evaluated && 'border-brand/30')}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <p className="text-xs text-muted">{t('Question {{n}}', { n: index + 1 })} · {t(QUESTION_TYPE_LABELS[answer.question_type] || '')} · {tn(max, '{{count}} pt', '{{count}} pts')}</p>
          <h2 dir="auto" className="mt-1 font-medium"><MathText text={answer.question_title} /></h2>
        </div>
        {answer.is_evaluated && (
          <Badge tone={answer.score_awarded >= max ? 'brand' : answer.score_awarded > 0 ? 'warn' : 'danger'}>
            {answer.score_awarded} / {max}
          </Badge>
        )}
      </div>

      <div className="px-5 py-4">
        <p className="eyebrow mb-2">{t("Student's answer")}</p>
        {answer.question_type === 'image_upload' ? (
          answer.uploaded_file_preview ? (
            <img
              src={answer.uploaded_file_preview}
              alt={answer.uploaded_file_name || t('Uploaded answer')}
              className="max-h-96 rounded-lg border border-line bg-sunken object-contain"
            />
          ) : (
            <p className="flex items-center gap-2 text-sm text-muted">
              <LuImage className="h-4 w-4" />
              {answer.uploaded_file_name || t('No image uploaded')}
            </p>
          )
        ) : answer.answer_text ? (
          <p dir="auto" className="whitespace-pre-wrap rounded-lg bg-sunken px-4 py-3 text-sm leading-relaxed">{answer.answer_text}</p>
        ) : (
          <p className="text-sm text-muted">{t('No answer given.')}</p>
        )}
      </div>

      <div className="border-t border-line bg-sunken/30 px-5 py-4">
        <GradeControl answerId={answer.answer_id} worth={max} score={answer.score_awarded} comment={answer.comment} onSaved={onSaved} />
      </div>
    </Card>
  );
}

// Grade the written and image answers of one attempt; questions with a set answer are graded automatically
function AdminEvaluateAnswersPage() {
  const { attemptId } = useParams();
  const { t } = useI18n();
  const [data, setData] = useState(null);
  const [loadFailure, setLoadFailure] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/admin/evaluations/attempts/${attemptId}`);
      setData(res.data);
      setLoadFailure(null);
    } catch (err) {
      setLoadFailure(err);
    }
  }, [attemptId]);

  useEffect(() => {
    load();
  }, [load]);

  // Counts follow each saved mark without reloading the page under the grader's hands
  const onSaved = (answerId, stored) => setData((d) => ({
    ...d,
    answers: d.answers.map((a) => (a.answer_id === answerId ? { ...a, is_evaluated: true, score_awarded: stored.score, comment: stored.comment } : a)),
  }));

  if (loadFailure && !data) {
    return (
      <AppShell width="narrow">
        <ErrorState error={loadFailure} onRetry={load} action={<Link to="/admin-exams" className="btn btn-secondary">{t('Back to exams')}</Link>} />
      </AppShell>
    );
  }
  if (!data) return <AppShell width="narrow"><PageLoader variant="sheet" /></AppShell>;

  const graded = data.answers.filter((a) => a.is_evaluated).length;
  const awarded = data.answers.reduce((sum, a) => sum + (a.is_evaluated ? a.score_awarded || 0 : 0), 0);
  const possible = data.answers.reduce((sum, a) => sum + (a.question_max_score || 0), 0);

  return (
    <AppShell width="narrow">
      <Link to={`/admin-exams/${data.exam.id}`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {data.exam.title}
      </Link>

      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-1.5">{t('Grading')}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{data.student.full_name || data.student.email}</h1>
          <p className="mt-1 text-sm text-muted">{t('Submitted {{date}}', { date: formatDateTime(data.submitted_at) })}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/admin-exams/${data.exam.id}/grade`} className="btn btn-secondary btn-sm">
            <LuPencil className="h-4 w-4" /> {t('Grade by question')}
          </Link>
          <Link to={`/admin-integrity/${attemptId}`} className="btn btn-secondary btn-sm">
            <LuShieldAlert className="h-4 w-4" /> {t('Integrity report')}
          </Link>
        </div>
      </div>

      {data.answers.length > 0 && (
        <Card className="mb-6 flex flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="h-2 w-40 overflow-hidden rounded-full bg-sunken">
              <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${(graded / data.answers.length) * 100}%` }} />
            </div>
            <span className="text-sm text-muted">{t('{{n}} of {{total}} graded', { n: graded, total: data.answers.length })}</span>
          </div>
          <span className="tabular text-sm">
            <span className="font-semibold">{awarded}</span><span className="text-muted"> / {t('{{n}} points awarded', { n: possible })}</span>
          </span>
        </Card>
      )}

      {data.answers.length === 0 ? (
        <Card>
          <EmptyState icon={LuCircleCheck} paige="sleeping" title={t('Nothing to grade')}>
            {t('This attempt has no written or image answers. Questions with a set answer were graded automatically.')}
          </EmptyState>
        </Card>
      ) : (
        <div className="space-y-4">
          {data.answers.map((answer, i) => <AnswerCard key={answer.answer_id} answer={answer} index={i} onSaved={onSaved} />)}
        </div>
      )}
    </AppShell>
  );
}

export default AdminEvaluateAnswersPage;
