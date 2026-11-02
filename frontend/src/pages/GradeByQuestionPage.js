import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { LuArrowLeft, LuArrowRight, LuCircleCheck, LuInbox, LuImage } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import GradeControl from '../components/GradeControl';
import MathText from '../components/MathText';
import { Badge, Button, Card, Checkbox, EmptyState, ErrorState, PageHeader, PageLoader, ProgressBar, cx } from '../components/ui';
import { QUESTION_TYPE_LABELS, formatDateTime } from '../utils';
import { useI18n } from '../i18n';

// One written or image question at a time, every submitted answer to it on one page (/admin-exams/:examId/grade)
function GradeByQuestionPage() {
  const { examId, questionId } = useParams();
  const navigate = useNavigate();
  const { t, tn } = useI18n();
  const [overview, setOverview] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [sheetError, setSheetError] = useState(null);
  const [reload, setReload] = useState(0);
  const [hideNames, setHideNames] = useState(false);
  const [onlyUngraded, setOnlyUngraded] = useState(false);
  const marks = useRef([]);

  useEffect(() => {
    setLoadError(null);
    api.get(`/admin/exams/${examId}/grading`).then((res) => setOverview(res.data)).catch(setLoadError);
  }, [examId, reload]);

  const questions = overview?.questions || [];
  // Start at the first question with answers left to grade, and pin it in the address: otherwise the page
  // would jump to the next question the moment the last answer here is marked
  const initialId = (questions.find((q) => q.graded < q.answered) || questions[0])?.id;
  const current = questions.find((q) => q.id === questionId) || questions.find((q) => q.id === initialId);
  useEffect(() => {
    if (!questionId && initialId) navigate(`/admin-exams/${examId}/grade/${initialId}`, { replace: true });
  }, [examId, questionId, initialId, navigate]);

  const currentId = current?.id;
  const loadSheet = useCallback(() => {
    if (!currentId) return;
    setSheet(null);
    setSheetError(null);
    api.get(`/admin/exams/${examId}/grading/${currentId}`).then((res) => setSheet(res.data)).catch(setSheetError);
  }, [examId, currentId]);

  useEffect(() => { loadSheet(); }, [loadSheet]);

  // A saved mark updates this page without reloading the answers under the grader's hands
  const onSaved = (answerId, stored) => setSheet((s) => ({
    ...s,
    answers: s.answers.map((a) => (a.answer_id === answerId ? { ...a, score_awarded: stored.score, comment: stored.comment } : a)),
  }));
  // The question's count comes from its answers, so saving the same answer twice can't count it twice
  useEffect(() => {
    if (!sheet) return;
    const graded = sheet.answers.filter((a) => a.score_awarded != null).length;
    setOverview((o) => (o.questions.some((q) => q.id === sheet.question.id && q.graded !== graded)
      ? { ...o, questions: o.questions.map((q) => (q.id === sheet.question.id ? { ...q, graded } : q)) }
      : o));
  }, [sheet]);

  if (loadError) {
    return (
      <AppShell>
        <ErrorState error={loadError} onRetry={() => setReload((n) => n + 1)} action={<Link to={`/admin-exams/${examId}`} className="btn btn-secondary">{t('Back to the exam')}</Link>} />
      </AppShell>
    );
  }
  if (!overview) return <AppShell><PageLoader variant="list" /></AppShell>;

  const back = (
    <Link to={`/admin-exams/${examId}`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
      <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {overview.exam.title}
    </Link>
  );
  const header = <PageHeader eyebrow={t('Grade by question')} title={overview.exam.title} description={t('Mark one question for every student before moving to the next. Every mark saves as you go.')} />;

  if (questions.length === 0 || overview.submitted === 0) {
    return (
      <AppShell>
        {back}
        {header}
        <Card>
          {questions.length === 0 && overview.submitted > 0 ? (
            <EmptyState icon={LuCircleCheck} paige="sleeping" title={t('Nothing to grade')}>
              {t('Every question on this exam is graded automatically.')}
            </EmptyState>
          ) : (
            <EmptyState icon={LuInbox} paige="thinking" title={t('No answers yet')}>
              {t('Written and image answers show up here as students submit.')}
            </EmptyState>
          )}
        </Card>
      </AppShell>
    );
  }

  const index = questions.indexOf(current);
  const next = questions.slice(index + 1).concat(questions.slice(0, index)).find((q) => q.graded < q.answered);
  const shown = (sheet?.answers || []).map((a, i) => ({ ...a, number: i + 1 })).filter((a) => !onlyUngraded || a.score_awarded == null);
  const done = current.answered > 0 && current.graded >= current.answered;
  marks.current = [];

  return (
    <AppShell>
      {back}
      {header}
      <div className="grid gap-8 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <nav aria-label={t('Questions to grade')}>
          <ul className="space-y-2">
            {questions.map((q, i) => (
              <li key={q.id}>
                <button
                  type="button"
                  onClick={() => navigate(`/admin-exams/${examId}/grade/${q.id}`)}
                  aria-current={q.id === current.id ? 'true' : undefined}
                  className={cx('block w-full rounded border px-3.5 py-3 text-start transition-colors', q.id === current.id ? 'border-ink bg-surface' : 'border-line hover:border-line-strong hover:bg-surface')}
                >
                  <span className="flex items-center justify-between gap-2 text-xs text-muted">
                    <span>{t('Question {{n}}', { n: i + 1 })} · {t(QUESTION_TYPE_LABELS[q.type] || '')}</span>
                    {q.answered > 0 && q.graded >= q.answered && <LuCircleCheck className="h-4 w-4 text-brand" aria-label={t('All graded')} />}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-sm font-medium"><MathText text={q.title} /></span>
                  <ProgressBar value={q.answered ? q.graded / q.answered : 1} className="mt-2.5" label={t('{{n}} of {{total}} graded', { n: q.graded, total: q.answered })} />
                  <span className="tabular mt-1.5 block text-xs text-muted">{t('{{n}} of {{total}} graded', { n: q.graded, total: q.answered })}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <section aria-labelledby="grading-question" className="min-w-0">
          <Card className="mb-4 px-5 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs text-muted">{t(QUESTION_TYPE_LABELS[current.type] || '')} · {tn(current.worth, '{{count}} mark', '{{count}} marks')}</p>
                <h2 id="grading-question" dir="auto" className="mt-1 font-medium leading-relaxed"><MathText text={current.title} /></h2>
              </div>
              <Badge tone={done ? 'brand' : 'neutral'}>{t('{{n}} of {{total}} graded', { n: current.graded, total: current.answered })}</Badge>
            </div>
            {sheet?.question.notes && (
              <p className="mt-3 rounded bg-sunken px-3 py-2 text-sm"><span className="font-medium">{t('Notes for graders:')}</span> {sheet.question.notes}</p>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line pt-3">
              <Checkbox checked={hideNames} onChange={setHideNames}>{t('Hide names while grading')}</Checkbox>
              <Checkbox checked={onlyUngraded} onChange={setOnlyUngraded}>{t('Show only answers not graded yet')}</Checkbox>
              {sheet?.blank > 0 && <span className="text-sm text-muted">{tn(sheet.blank, '{{count}} student left it blank: 0 marks, nothing to grade', '{{count}} students left it blank: 0 marks, nothing to grade')}</span>}
            </div>
          </Card>

          {sheetError ? (
            <ErrorState error={sheetError} onRetry={loadSheet} />
          ) : !sheet ? (
            <PageLoader variant="list" />
          ) : sheet.answers.length === 0 ? (
            <Card><EmptyState icon={LuInbox} paige="sleeping" title={t('Nothing to grade here')}>{t('Everyone who had this question left it blank.')}</EmptyState></Card>
          ) : shown.length === 0 ? (
            <Card>
              <EmptyState icon={LuCircleCheck} paige="submitted" title={t('Every answer to this question is graded')} action={next && <Button iconRight={LuArrowRight} onClick={() => navigate(`/admin-exams/${examId}/grade/${next.id}`)}>{t('Next question')}</Button>}>
                {t('Turn off “Show only answers not graded yet” to look at them again.')}
              </EmptyState>
            </Card>
          ) : (
            <ol className="space-y-3">
              {shown.map((a, i) => (
                <li key={a.answer_id}>
                  <Card className={cx('overflow-hidden', a.score_awarded != null && 'border-brand/30')}>
                    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
                      <p className="text-sm font-medium">{hideNames ? t('Answer {{n}}', { n: a.number }) : a.student.name}</p>
                      <p className="text-xs text-muted">{t('Submitted {{date}}', { date: formatDateTime(a.submitted_at) })}</p>
                    </div>
                    <div className="px-5 py-4">
                      {current.type === 'image_upload' ? (
                        a.image ? (
                          <img src={a.image} alt={a.image_name || t('Uploaded answer')} className="max-h-[28rem] rounded border border-line bg-sunken object-contain" />
                        ) : (
                          <p className="flex items-center gap-2 text-sm text-muted"><LuImage className="h-4 w-4" />{a.image_name || t('No image uploaded')}</p>
                        )
                      ) : (
                        <p dir="auto" className="whitespace-pre-wrap rounded bg-sunken px-4 py-3 text-sm leading-relaxed">{a.text}</p>
                      )}
                    </div>
                    <div className="border-t border-line bg-sunken/30 px-5 py-4">
                      <GradeControl
                        ref={(el) => { marks.current[i] = el; }}
                        answerId={a.answer_id}
                        worth={a.worth}
                        score={a.score_awarded}
                        comment={a.comment}
                        onSaved={onSaved}
                        onNext={() => marks.current[i + 1]?.focus()}
                      />
                      {a.graded_by && !hideNames && <p className="mt-2 text-xs text-faint">{t('Last marked by {{name}}', { name: a.graded_by })}</p>}
                    </div>
                  </Card>
                </li>
              ))}
            </ol>
          )}

          {sheet && shown.length > 0 && next && (
            <div className="mt-6 flex justify-end">
              <Button variant={done ? 'primary' : 'secondary'} iconRight={LuArrowRight} onClick={() => navigate(`/admin-exams/${examId}/grade/${next.id}`)}>
                {t('Next question')}
              </Button>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

export default GradeByQuestionPage;
