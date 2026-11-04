import React, { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { LuArrowLeft, LuPrinter } from 'react-icons/lu';
import api from '../api';
import { Alert, Button, EmptyState, LogoMark, PageLoader } from '../components/ui';
import { errorMessage, formatDate, formatDateTime, formatDuration, formatNumber } from '../utils';
import { useI18n } from '../i18n';

/*
 * Printable result cards (task 4.5): one A4 card per submitted student, or one with ?attempt=.
 * "Print or save as PDF" uses the browser's own print dialog, which lays out every script correctly
 * (Bengali, Arabic) and saves a PDF without anything on the server. Outside AppShell so only the cards print.
 */

const marks = (value) => formatNumber(value, { maximumFractionDigits: 2 });

function ResultCard({ card, exam, submitted }) {
  const { t } = useI18n();
  const name = card.student.full_name || card.student.email;
  return (
    <article className="sheet mx-auto mb-10 w-full max-w-[210mm] px-10 pb-10 pt-9 shadow-sm print:mb-0 print:max-w-none print:break-after-page print:border-0 print:shadow-none">
      <header className="flex items-center justify-between gap-6 border-b-2 border-ink pb-4">
        <div className="flex items-center gap-2.5">
          <LogoMark size={22} />
          <span className="font-mono text-xs uppercase tracking-[0.08em] text-muted">{exam.organization}</span>
        </div>
        <span className="eyebrow">{t('Result card')}</span>
      </header>

      <h1 className="mt-6 text-2xl font-semibold leading-tight tracking-tight">{exam.title}</h1>
      <p className="mt-1 text-sm text-muted">{formatDate(exam.start_time)} · {t('{{n}} marks in total', { n: marks(exam.total_marks) })}</p>

      <section className="mt-8 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-6 border-b border-line pb-7">
        <div className="min-w-0">
          <p className="eyebrow">{t('Student')}</p>
          <p className="mt-1.5 text-xl font-semibold">{name}</p>
          {card.student.full_name && <p className="text-sm text-muted">{card.student.email}</p>}
        </div>
        <div className="text-end">
          <p className="eyebrow">{t('Score')}</p>
          <p className="tabular mt-1 text-4xl font-semibold leading-none tracking-tight">
            {marks(card.score)}<span className="text-xl font-normal text-muted"> / {marks(card.total)}</span>
          </p>
          <p className="tabular mt-1.5 text-sm font-medium text-brand">{t('{{n}}%', { n: formatNumber(card.percentage) })}</p>
        </div>
      </section>

      <dl className="grid grid-cols-3 gap-6 border-b border-line py-6 text-sm">
        {card.rank && (
          <div>
            <dt className="eyebrow">{t('Rank')}</dt>
            <dd className="tabular mt-1 font-medium">{card.tied ? t('{{rank}} (shared) of {{n}}', { rank: card.rank, n: submitted }) : t('{{rank}} of {{n}}', { rank: card.rank, n: submitted })}</dd>
          </div>
        )}
        <div>
          <dt className="eyebrow">{t('Time taken')}</dt>
          <dd className="tabular mt-1 font-medium">{formatDuration(card.time_taken_seconds || 0)}</dd>
        </div>
        <div>
          <dt className="eyebrow">{t('Submitted')}</dt>
          <dd className="tabular mt-1 font-medium">{formatDateTime(card.submitted_at)}</dd>
        </div>
      </dl>

      <section className="py-6">
        <h2 className="eyebrow mb-3">{t('Marks by question')}</h2>
        <ol className="grid grid-cols-5 gap-2">
          {card.questions.map((q) => (
            <li key={q.n} className="flex items-baseline justify-between gap-2 rounded border border-line px-2.5 py-1.5 text-sm">
              <span className="font-mono text-xs text-faint">{t('Q{{n}}', { n: q.n })}</span>
              <span className="tabular font-medium">
                {q.earned === null ? <span className="text-xs font-normal text-warn-ink">{t('Not graded')}</span> : `${marks(q.earned)} / ${marks(q.worth)}`}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <footer className="mt-10 flex items-end justify-between gap-6 text-xs text-faint">
        <span>{t('Printed {{date}} from Fairpaper', { date: formatDate(new Date().toISOString()) })}</span>
        <span className="w-48 border-t border-line-strong pt-1.5 text-center">{t("Examiner's signature")}</span>
      </footer>
    </article>
  );
}

function ResultCardsPage() {
  const { examId } = useParams();
  const [params] = useSearchParams();
  const only = params.get('attempt');
  const { t, tn } = useI18n();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(`/admin/exams/${examId}/result-cards`, { params: only ? { attempt: only } : undefined })
      .then((res) => setData(res.data))
      .catch((err) => setError(errorMessage(err, t('Could not load the result cards.'))));
  }, [examId, only, t]);

  if (!data && !error) return <div className="min-h-screen bg-paper"><PageLoader variant="sheet" /></div>;

  return (
    <div className="min-h-screen bg-paper print:bg-white">
      <header className="sticky top-0 z-10 border-b border-line bg-surface print:hidden">
        <div className="mx-auto flex max-w-[210mm] flex-wrap items-center gap-4 px-2 py-3">
          <Link to={`/admin-exams/${examId}`} className="btn btn-ghost btn-sm"><LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" />{t('Results')}</Link>
          <p className="min-w-0 flex-1 truncate text-sm">
            <span className="font-medium">{data?.exam.title}</span>
            {data && <span className="ms-3 font-mono text-xs text-faint">{tn(data.cards.length, '{{count}} card', '{{count}} cards')}</span>}
          </p>
          {only && <Link to={`/admin-exams/${examId}/cards`} className="btn btn-ghost btn-sm">{t('All cards')}</Link>}
          <Button icon={LuPrinter} disabled={!data?.cards.length} onClick={() => window.print()}>{t('Print or save as PDF')}</Button>
        </div>
      </header>

      <main className="px-4 py-10 print:p-0">
        {error && <Alert tone="danger" className="mx-auto mb-6 max-w-[210mm]">{error}</Alert>}
        {data && !data.exam.results_visible && (
          <Alert tone="info" className="mx-auto mb-6 max-w-[210mm] print:hidden">
            {t("Results aren't released yet, so students can't see them in Fairpaper. Printing cards doesn't release them.")}
          </Alert>
        )}
        {data && data.cards.length === 0 && (
          <EmptyState title={t('No result cards yet')}>{t('A card appears here for every student who has submitted.')}</EmptyState>
        )}
        {data?.cards.map((card) => <ResultCard key={card.attempt_id} card={card} exam={data.exam} submitted={data.submitted} />)}
      </main>
    </div>
  );
}

export default ResultCardsPage;
