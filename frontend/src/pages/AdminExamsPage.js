import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LuPlus, LuClipboardList, LuEllipsis, LuTrash2, LuEyeOff, LuSend, LuPencil } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import { Alert, Button, Card, EmptyState, ErrorState, PageHeader, PageLoader, useConfirm } from '../components/ui';
import GetStarted from '../components/GetStarted';
import { useToast } from '../components/Toaster';
import { errorMessage, formatExamTime, formatShortDate, getTimeZone, isSameDay, timeZoneLabel } from '../utils';
import { msg, useI18n } from '../i18n';

// Draft until published; then scheduled, live or closed depending on the exam window
export function examStatus(exam, now = new Date()) {
  if (!exam.is_published) return { label: msg('Draft'), tone: 'neutral' };
  if (now < new Date(exam.start_time)) return { label: msg('Scheduled'), tone: 'info' };
  if (now <= new Date(exam.end_time)) return { label: msg('Live'), tone: 'brand', live: true };
  return { label: msg('Closed'), tone: 'neutral' };
}

// Status as an answer-bubble dot: filled when live, half when scheduled, empty for drafts
const STATUS_STYLE = {
  Draft: ['text-faint', ''],
  Scheduled: ['text-ink', 'bg-[linear-gradient(90deg,currentColor_50%,transparent_50%)]'],
  Live: ['text-brand font-medium', 'bg-current'],
  Closed: ['text-faint', 'bg-current opacity-50'],
};

export function StatusBadge({ exam }) {
  const { t } = useI18n();
  const { label } = examStatus(exam);
  const [text, dot] = STATUS_STYLE[label];
  return (
    <span className={`inline-flex items-center gap-2 text-sm ${text}`}>
      <span className={`status-dot ${dot}`} aria-hidden="true" />
      {t(label)}
    </span>
  );
}

// Printed tags naming the protections an exam uses
export function ProtectionIcons({ exam }) {
  const { t, tn } = useI18n();
  const items = [
    exam.require_fullscreen && [t('Fullscreen'), t('Fullscreen required')],
    (exam.shuffle_questions || exam.shuffle_options) && [t('Shuffle'), t('Shuffled per student')],
    exam.block_copy_paste && [t('No paste'), t('Copy and paste blocked')],
    exam.max_violations && [t('Limit {{n}}', { n: exam.max_violations }), tn(exam.max_violations, 'Submitted automatically after {{count}} violation', 'Submitted automatically after {{count}} violations')],
  ].filter(Boolean);
  if (!items.length) return <span className="text-xs text-faint">{t('No protections')}</span>;
  return (
    <span className="flex flex-wrap items-center gap-1">
      {items.map(([tag, label]) => (
        <span key={tag} title={label} className="tag uppercase">
          {tag}
          <span className="sr-only">: {label}</span>
        </span>
      ))}
    </span>
  );
}

function ExamMenu({ exam, onPublishToggle, onDelete }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <Button variant="ghost" size="sm" icon={LuEllipsis} onClick={() => setOpen(!open)} aria-label={t('More actions')} />
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute end-0 z-20 mt-1 w-48 animate-fade-in overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-pop">
            {!exam.edit_blocked && (
              <button
                type="button"
                onClick={() => { setOpen(false); navigate(`/admin-exams/${exam.id}/edit`); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-start text-sm hover:bg-sunken"
              >
                <LuPencil className="h-4 w-4 text-muted" />
                {t('Edit')}
              </button>
            )}
            <button
              type="button"
              onClick={() => { setOpen(false); onPublishToggle(exam); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-start text-sm hover:bg-sunken"
            >
              {exam.is_published ? <LuEyeOff className="h-4 w-4 text-muted" /> : <LuSend className="h-4 w-4 text-muted" />}
              {exam.is_published ? t('Unpublish') : t('Publish')}
            </button>
            <button
              type="button"
              onClick={() => { setOpen(false); onDelete(exam); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-start text-sm text-danger hover:bg-danger-soft"
            >
              <LuTrash2 className="h-4 w-4" />
              {t('Delete')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// Date on one line, times on the next; both dates when the window spans days
function ExamWindow({ exam }) {
  const { t, locale } = useI18n();
  const start = new Date(exam.start_time);
  const end = new Date(exam.end_time);
  const time = (d) => d.toLocaleTimeString(locale, { timeZone: getTimeZone(), hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const day = (d) => (isSameDay(d, new Date()) ? t('Today') : formatShortDate(d));
  const zone = timeZoneLabel(start);
  return (
    <>
      <span className="block">{isSameDay(start, end) ? day(start) : `${day(start)} – ${day(end)}`}</span>
      <span className="block text-faint">{time(start)} – {time(end)}{zone && ` ${zone}`}</span>
    </>
  );
}

function AdminExamsPage() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [exams, setExams] = useState(null);
  const [message, setMessage] = useState(null);
  const [loadFailure, setLoadFailure] = useState(null);
  const [confirmDialog, confirm] = useConfirm();
  const toast = useToast();
  const [checklist, setChecklist] = useState(false); // the Get started card is showing

  const fetchExams = async () => {
    try {
      const res = await api.get('/admin/exams/');
      // Newest first
      setExams([...res.data].sort((a, b) => new Date(b.start_time) - new Date(a.start_time)));
    } catch (err) {
      setLoadFailure(err); // an error, not "no exams yet"
    }
  };

  useEffect(() => {
    fetchExams();
  }, []);

  const togglePublish = async (exam) => {
    if (!exam.is_published) {
      const ok = await confirm({
        title: t('Publish “{{title}}”?', { title: exam.title }),
        description: exam.groups?.length
          ? t('Students in {{groups}} will see it and can start it from {{date}}.', { groups: exam.groups.map((g) => g.name).join(', '), date: formatExamTime(exam.start_time) })
          : t('Students in your organization will see it and can start it from {{date}}.', { date: formatExamTime(exam.start_time) }),
        confirmLabel: t('Publish'),
      });
      if (!ok) return;
    }
    try {
      await api.post(`/admin/exams/${exam.id}/${exam.is_published ? 'unpublish' : 'publish'}`);
      toast(exam.is_published
        ? { title: t('Exam unpublished'), body: t('Students can no longer see {{title}}. Publish it again whenever you like.', { title: exam.title }) }
        : { title: t('Exam published'), body: t('{{title}} opens {{when}}. Students see it on their dashboard.', { title: exam.title, when: formatExamTime(exam.start_time) }), action: { label: t('View exam'), to: `/admin-exams/${exam.id}` } });
      fetchExams();
    } catch (err) {
      setMessage({ tone: 'danger', text: errorMessage(err) });
    }
  };

  const deleteExam = async (exam) => {
    const ok = await confirm({
      title: t('Delete “{{title}}”?', { title: exam.title }),
      description: t('If students have started it, it is archived instead: hidden from lists and closed, with their results and integrity records kept.'),
      confirmLabel: t('Delete exam'),
      danger: true,
    });
    if (!ok) return;
    try {
      const { data } = await api.delete(`/admin/exams/${exam.id}`);
      setMessage({ tone: 'success', text: t(data.message) });
      fetchExams();
    } catch (err) {
      setMessage({ tone: 'danger', text: errorMessage(err) });
    }
  };

  return (
    <AppShell>
      <PageHeader
        title={t('Exams')}
        description={t('Schedule an exam from your question bank, then share it with one or more groups.')}
        actions={<Button icon={LuPlus} onClick={() => navigate('/admin-exams/new')}>{t('New exam')}</Button>}
      />

      {message && <Alert tone={message.tone} className="mb-6" onClose={() => setMessage(null)}>{message.text}</Alert>}

      <GetStarted onVisible={setChecklist} />

      {loadFailure ? (
        <Card><ErrorState error={loadFailure} onRetry={() => { setLoadFailure(null); fetchExams(); }} /></Card>
      ) : exams === null ? (
        <PageLoader />
      ) : exams.length === 0 ? (checklist ? null : (
        <Card>
          <EmptyState
            icon={LuClipboardList}
            paige="pointing"
            title={t('No exams yet')}
            action={<Button icon={LuPlus} onClick={() => navigate('/admin-exams/new')}>{t('Create your first exam')}</Button>}
          >
            {t('An exam picks questions from your question bank and runs in a time window you choose.')}
          </EmptyState>
        </Card>
      )) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[56rem] table-fixed">
            <colgroup>
              <col className="w-12" /><col /><col className="w-[11.5rem]" /><col className="w-[8.5rem]" /><col className="w-[14rem]" /><col className="w-[7.5rem]" />
            </colgroup>
            <thead>
              <tr>
                <th>{t('No.')}</th>
                <th>{t('Exam')}</th>
                <th>{t('Window')}</th>
                <th>{t('Status')}</th>
                <th>{t('Protections')}</th>
                <th><span className="sr-only">{t('Actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {exams.map((exam, i) => (
                <tr key={exam.id}>
                  <td className="tabular font-mono text-faint">{String(i + 1).padStart(2, '0')}</td>
                  <td>
                    <Link to={`/admin-exams/${exam.id}`} className="font-medium text-ink hover:text-brand">{exam.title}</Link>
                    <span className="mt-0.5 block truncate font-mono text-xs text-faint">
                      {exam.groups?.length ? exam.groups.map((g) => g.name).join(', ') : t('Everyone')} · {t('{{n}} min', { n: exam.duration_minutes })} · {t('{{n}} Q', { n: exam.questions?.length || 0 })}
                    </span>
                  </td>
                  <td className="tabular font-mono text-[13px] leading-snug"><ExamWindow exam={exam} /></td>
                  <td className="whitespace-nowrap"><StatusBadge exam={exam} /></td>
                  <td><ProtectionIcons exam={exam} /></td>
                  <td>
                    <div className="flex items-center justify-end gap-1">
                      {!exam.is_published && (
                        <Button variant="secondary" size="sm" onClick={() => togglePublish(exam)}>{t('Publish')}</Button>
                      )}
                      <ExamMenu exam={exam} onPublishToggle={togglePublish} onDelete={deleteExam} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {confirmDialog}
    </AppShell>
  );
}

export default AdminExamsPage;
