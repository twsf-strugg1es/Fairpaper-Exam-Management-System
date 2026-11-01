import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { LuArrowLeft, LuImage, LuMessageSquare } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import { Badge, Card, ErrorState, PageLoader } from '../components/ui';
import { QUESTION_TYPE_LABELS, formatDateTime } from '../utils';
import { answerText, isManual } from '../questionTypes';
import { useI18n } from '../i18n';


// One submitted exam, with the examiner's grades and feedback on written answers
function StudentResultsPage() {
  const { attemptId } = useParams();
  const { t } = useI18n();
  const [result, setResult] = useState(null);
  const [loadFailure, setLoadFailure] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.get(`/student/attempts/${attemptId}/evaluated-results`)
      .then((res) => setResult(res.data))
      .catch((err) => setLoadFailure(err));
  }, [attemptId, reload]);

  if (loadFailure) {
    return (
      <AppShell width="narrow">
        <ErrorState error={loadFailure} onRetry={() => { setLoadFailure(null); setReload((n) => n + 1); }} action={<Link to="/student-exams" className="btn btn-secondary">{t('Back to results')}</Link>} />
      </AppShell>
    );
  }
  if (!result) return <AppShell width="narrow"><PageLoader variant="sheet" /></AppShell>;

  return (
    <AppShell width="narrow">
      <Link to="/student-exams" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {t('Results')}
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">{result.exam_title}</h1>
      <p className="mt-1 text-sm text-muted">{t('Submitted {{date}}', { date: formatDateTime(result.submitted_at) })}</p>

      {result.results_released === false ? (
        <Card className="mt-6 p-6">
          <p className="font-semibold">{t('Results aren’t released yet')}</p>
          <p className="mt-1 text-sm leading-relaxed text-muted">{t('Your answers are saved. Your score will appear here once your examiner releases it.')}</p>
        </Card>
      ) : (<>
      <Card className="mt-6 flex items-end justify-between gap-6 p-6">
        <div>
          <p className="text-sm text-muted">{t('Score')}</p>
          <p className="tabular mt-1 text-4xl font-semibold tracking-tight">
            {result.score}<span className="text-xl font-normal text-muted"> / {result.total_possible_score}</span>
          </p>
        </div>
        <div className="text-end">
          <p className="tabular text-3xl font-semibold text-brand">{Math.round(result.percentage)}%</p>
          {result.rank && (
            <p className="mt-1 text-sm text-muted">
              {result.rank.tied
                ? t('Joint {{n}} of {{total}}', { n: result.rank.position, total: result.rank.of })
                : t('Rank {{n}} of {{total}}', { n: result.rank.position, total: result.rank.of })}
            </p>
          )}
        </div>
      </Card>

      <h2 className="mb-3 mt-10 text-[15px] font-semibold">{t('Answers')}</h2>
      <div className="space-y-2.5">
        {result.answers_with_evaluations.map((answer, i) => {
          const evaluation = answer.evaluation;
          // An uploaded image shows its file name with an icon instead
          const text = answer.question_type === 'image_upload' ? null : answerText(answer.question_type, answer.answer_data, t);
          const manual = isManual(answer.question_type);
          return (
            <Card key={answer.id} className="px-5 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs text-muted">{t(QUESTION_TYPE_LABELS[answer.question_type] || '')}</p>
                  <p className="mt-0.5 text-sm font-medium"><span className="tabular me-2 text-muted">{i + 1}.</span>{answer.question_title}</p>
                </div>
                {manual && evaluation?.score_awarded != null && (
                  <Badge tone={evaluation.score_awarded >= (answer.question_max_score ?? Infinity) ? 'brand' : evaluation.score_awarded > 0 ? 'warn' : 'danger'}>
                    {answer.question_max_score != null
                      ? t('{{n}} of {{total}} marks', { n: evaluation.score_awarded, total: answer.question_max_score })
                      : t('{{n}} pts', { n: evaluation.score_awarded })}
                  </Badge>
                )}
                {manual && evaluation?.score_awarded == null && <Badge>{t('Not graded yet')}</Badge>}
              </div>
              <p className="mt-2 text-sm text-muted">
                {t('Your answer:')}{' '}
                {text ? <span className="whitespace-pre-wrap text-ink">{text}</span>
                  : answer.answer_data?.name ? <span className="inline-flex items-center gap-1 text-ink"><LuImage className="h-3.5 w-3.5" />{answer.answer_data.name}</span>
                    : <span>{t('no answer')}</span>}
              </p>
              {evaluation?.comment && (
                <p className="mt-3 flex gap-2 rounded-lg bg-sunken px-3 py-2.5 text-sm">
                  <LuMessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                  <span>{evaluation.comment}</span>
                </p>
              )}
            </Card>
          );
        })}
      </div>
      </>)}
    </AppShell>
  );
}

export default StudentResultsPage;
