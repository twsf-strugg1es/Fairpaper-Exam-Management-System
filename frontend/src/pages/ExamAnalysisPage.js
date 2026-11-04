import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { LuArrowLeft, LuChartColumn, LuChevronDown, LuCircleCheck, LuInfo, LuTriangleAlert } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import MathText from '../components/MathText';
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, PageHeader, PageLoader, Select, Stat, cx } from '../components/ui';
import { QUESTION_TYPE_LABELS } from '../utils';
import { useI18n } from '../i18n';

const pct = (share) => (share == null ? '—' : `${Math.round(share * 100)}%`);
const signed = (n) => (n == null ? '—' : `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toFixed(2)}`);

// A thin bar from the start edge: 4px rounded at the data end, square at the baseline
function Bar({ share, className }) {
  return (
    <span className={cx('block h-2.5 overflow-hidden rounded-sm bg-sunken', className)} aria-hidden="true">
      <span className="block h-full rounded-e-lg bg-brand" style={{ width: `${Math.round((share || 0) * 100)}%` }} />
    </span>
  );
}

// How the class's scores spread, in ten 10 % bands; hover shows a band's count, and the table is always one click away
function Distribution({ counts, total }) {
  const { t, tn } = useI18n();
  const [hover, setHover] = useState(null);
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(1, ...counts);
  const ticks = [...new Set([max, Math.round(max / 2), 0])];
  const band = (i) => (i === 9 ? '90–100%' : `${i * 10}–${i * 10 + 9}%`);
  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold">{t('How the scores spread')}</h2>
        <Button variant="ghost" size="sm" onClick={() => setAsTable(!asTable)}>{asTable ? t('Show as a chart') : t('Show as a table')}</Button>
      </div>
      {asTable ? (
        <table className="table">
          <thead><tr><th>{t('Score')}</th><th className="text-end">{t('Students')}</th></tr></thead>
          <tbody>{counts.map((n, i) => <tr key={i}><td className="tabular">{band(i)}</td><td className="tabular text-end">{n}</td></tr>)}</tbody>
        </table>
      ) : (
        <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3">
          <div className="relative h-44 text-end font-mono text-[11px] text-faint" aria-hidden="true">
            {ticks.map((tick) => (
              <span key={tick} className="tabular absolute end-0 -translate-y-1/2" style={{ top: `${100 - (tick / max) * 100}%` }}>{tick}</span>
            ))}
          </div>
          <div className="relative" aria-hidden="true">
            {ticks.filter((tick) => tick > 0).map((tick) => (
              <span key={tick} className="absolute inset-x-0 border-t border-line" style={{ top: `${100 - (tick / max) * 100}%` }} />
            ))}
            <div className="relative grid h-44 grid-cols-10 items-end gap-0.5 border-b border-line-strong">
              {counts.map((n, i) => (
                <div key={i} className="relative flex h-full items-end justify-center" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  {n > 0 && <span className={cx('block w-full max-w-[24px] rounded-t-lg bg-brand transition-opacity', hover !== null && hover !== i && 'opacity-50')} style={{ height: `${(n / max) * 100}%` }} />}
                  {hover === i && (
                    // Beside the column's top, inside the plot, so it never covers the title; the last columns open inward
                    <span
                      className={cx('pointer-events-none absolute z-10 whitespace-nowrap rounded border border-line bg-surface px-2.5 py-1.5 text-xs shadow-pop',
                        i >= 7 ? 'end-[calc(50%+16px)]' : 'start-[calc(50%+16px)]')}
                      style={{ bottom: `max(0px, calc(${(n / max) * 100}% - 2.5rem))` }}
                    >
                      <span className="block text-muted">{band(i)}</span>
                      <span className="tabular font-medium">{tn(n, '{{count}} student', '{{count}} students')}</span>
                    </span>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-1.5 grid grid-cols-10 gap-0.5 font-mono text-[11px] text-faint">
              {counts.map((_, i) => <span key={i} className="tabular text-center">{i * 10}</span>)}
            </div>
          </div>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">{t('Each column is a 10 % band of the score, from 0 % on the left; {{n}} papers in all.', { n: total })}</p>
      <table className="sr-only">
        <caption>{t('How the scores spread')}</caption>
        <tbody>{counts.map((n, i) => <tr key={i}><th scope="row">{band(i)}</th><td>{n}</td></tr>)}</tbody>
      </table>
    </Card>
  );
}

// Status tone and icon per flag; the words are in ItemRow, through t()
const FLAGS = {
  very_hard: { tone: 'warn', icon: LuTriangleAlert },
  very_easy: { tone: 'neutral', icon: null },
  weak: { tone: 'warn', icon: LuTriangleAlert },
  check_key: { tone: 'danger', icon: LuTriangleAlert },
};

function ItemRow({ item, index }) {
  const { t, tn } = useI18n();
  const [open, setOpen] = useState(false);
  const label = { very_hard: t('Very hard'), very_easy: t('Very easy'), weak: t('Weak discrimination'), check_key: t('Check the key') };
  return (
    <>
      <tr>
        <td className="tabular align-top text-muted">{index + 1}</td>
        <td className="max-w-[22rem] align-top">
          <p dir="auto" className="line-clamp-2 font-medium"><MathText text={item.title} /></p>
          <p className="mt-0.5 text-xs text-muted">
            {t(QUESTION_TYPE_LABELS[item.type] || '')} · {tn(item.papers, 'on {{count}} paper', 'on {{count}} papers')}
            {item.waiting > 0 && <> · <span className="text-warn-ink">{tn(item.waiting, '{{count}} answer not graded yet', '{{count}} answers not graded yet')}</span></>}
          </p>
        </td>
        <td className="align-top">
          <div className="flex items-center gap-2.5">
            <Bar share={item.difficulty} className="w-24" />
            <span className="tabular w-10 text-end text-sm">{pct(item.difficulty)}</span>
          </div>
        </td>
        <td className="tabular align-top text-end">{signed(item.discrimination)}</td>
        <td className="align-top">
          <div className="flex flex-wrap gap-1.5">
            {item.flags.map((flag) => {
              const f = FLAGS[flag];
              return <Badge key={flag} tone={f.tone} icon={f.icon}>{label[flag]}</Badge>;
            })}
          </div>
        </td>
        <td className="align-top text-end">
          {item.options && (
            <Button variant="ghost" size="sm" iconRight={LuChevronDown} aria-expanded={open} onClick={() => setOpen(!open)}
              className={cx('[&>svg]:transition-transform', open && '[&>svg]:rotate-180')}>
              {t('Options')}
            </Button>
          )}
        </td>
      </tr>
      {open && item.options && (
        <tr className="bg-sunken/40">
          <td />
          <td colSpan={5}>
            <ul className="max-w-xl space-y-2 py-1">
              {item.options.choices.map((choice) => (
                <li key={choice.option} className="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto] items-center gap-3 text-sm">
                  <span dir="auto" className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate">{choice.option === 'true' && item.type === 'true_false' ? t('True') : choice.option === 'false' && item.type === 'true_false' ? t('False') : choice.option}</span>
                    {choice.correct && <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-brand-ink"><LuCircleCheck className="h-3.5 w-3.5" />{t('Correct')}</span>}
                  </span>
                  <Bar share={item.papers ? choice.count / item.papers : 0} />
                  <span className="tabular w-16 text-end text-muted">{tn(choice.count, '{{count}} chose', '{{count}} chose')}</span>
                </li>
              ))}
              {item.options.blank > 0 && <li className="text-xs text-muted">{tn(item.options.blank, '{{count}} left it blank', '{{count}} left it blank')}</li>}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}

// How each question worked, the class per topic and the spread of scores (/admin-exams/:examId/analysis)
function ExamAnalysisPage() {
  const { examId } = useParams();
  const { t, tn } = useI18n();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [reload, setReload] = useState(0);
  const [sort, setSort] = useState('paper');

  useEffect(() => {
    setLoadError(null);
    api.get(`/admin/exams/${examId}/analytics`).then((res) => setData(res.data)).catch(setLoadError);
  }, [examId, reload]);

  if (loadError) {
    return <AppShell><ErrorState error={loadError} onRetry={() => setReload((n) => n + 1)} action={<Link to={`/admin-exams/${examId}`} className="btn btn-secondary">{t('Back to the exam')}</Link>} /></AppShell>;
  }
  if (!data) return <AppShell><PageLoader variant="list" /></AppShell>;

  const back = (
    <Link to={`/admin-exams/${examId}`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
      <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {data.exam.title}
    </Link>
  );
  const header = <PageHeader eyebrow={t('Question analysis')} title={data.exam.title} />;
  if (data.submitted === 0) {
    return (
      <AppShell>
        {back}
        {header}
        <Card><EmptyState icon={LuChartColumn} paige="thinking" title={t('Nothing to analyse yet')}>{t('The analysis appears once students submit.')}</EmptyState></Card>
      </AppShell>
    );
  }

  const order = {
    paper: (a, b) => a.i - b.i,
    hardest: (a, b) => (a.item.difficulty ?? 2) - (b.item.difficulty ?? 2),
    discrimination: (a, b) => (a.item.discrimination ?? 2) - (b.item.discrimination ?? 2),
  };
  const rows = data.items.map((item, i) => ({ item, i })).sort(order[sort]);
  const few = data.submitted < data.discrimination_needs;
  const waiting = data.items.reduce((n, item) => n + item.waiting, 0);
  const { summary } = data;

  return (
    <AppShell>
      {back}
      {header}
      <Card className="mb-6 grid grid-cols-2 gap-6 p-5 sm:grid-cols-4">
        <Stat label={t('Submitted')} value={data.submitted} />
        <Stat label={t('Average score')} value={pct(summary.mean)} />
        <Stat label={t('Median score')} value={pct(summary.median)} />
        <Stat label={t('Highest and lowest')} value={`${pct(summary.highest)} · ${pct(summary.lowest)}`} />
      </Card>

      {(few || waiting > 0) && (
        <div className="mb-6 space-y-2">
          {few && <p className="flex items-start gap-2 text-sm text-muted"><LuInfo className="mt-0.5 h-4 w-4 shrink-0" />{t('Discrimination needs at least {{n}} submitted papers, so it shows once more students have finished.', { n: data.discrimination_needs })}</p>}
          {waiting > 0 && <p className="flex items-start gap-2 text-sm text-muted"><LuInfo className="mt-0.5 h-4 w-4 shrink-0" />{tn(waiting, '{{count}} written answer isn’t graded yet. Each counts once it is.', '{{count}} written answers aren’t graded yet. Each counts once it is.')}</p>}
        </div>
      )}

      <div className="mb-6 grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Distribution counts={data.distribution} total={data.submitted} />
        <Card className="p-5">
          <h2 className="mb-1 text-[15px] font-semibold">{t('By topic')}</h2>
          <p className="mb-4 text-xs text-muted">{t('Share of the marks earned on questions with each tag, hardest first.')}</p>
          <ul className="space-y-3">
            {data.topics.map((topic) => (
              <li key={topic.tag ?? ''} className="text-sm">
                <div className="mb-1 flex items-baseline justify-between gap-3">
                  <span className={cx('truncate', topic.tag ? 'font-medium' : 'text-muted')}>{topic.tag ? `#${topic.tag}` : t('No tag')}</span>
                  <span className="tabular shrink-0 text-muted">{pct(topic.difficulty)} · {tn(topic.questions, '{{count}} question', '{{count}} questions')}</span>
                </div>
                <Bar share={topic.difficulty} />
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <CardHeader
          title={t('Questions')}
          description={t('Difficulty is the share of the marks students earned. Discrimination compares the top 27 % of students with the bottom 27 %: high is good, near 0 tells strong and weak students apart poorly, below 0 means strong students did worse, often a wrong key.')}
          action={(
            <Select value={sort} onChange={(e) => setSort(e.target.value)} aria-label={t('Sort questions')} className="h-9 w-auto">
              <option value="paper">{t('In paper order')}</option>
              <option value="hardest">{t('Hardest first')}</option>
              <option value="discrimination">{t('Lowest discrimination first')}</option>
            </Select>
          )}
        />
        <div className="relative overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th className="w-10">#</th>
                <th>{t('Question')}</th>
                <th>{t('Difficulty')}</th>
                <th className="text-end">{t('Discrimination')}</th>
                <th>{t('Look at')}</th>
                <th><span className="sr-only">{t('Options')}</span></th>
              </tr>
            </thead>
            <tbody>{rows.map(({ item, i }) => <ItemRow key={item.question_id} item={item} index={i} />)}</tbody>
          </table>
        </div>
      </Card>
    </AppShell>
  );
}

export default ExamAnalysisPage;
