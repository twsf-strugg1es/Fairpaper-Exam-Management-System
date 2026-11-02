import React, { useEffect, useMemo, useRef, useState } from 'react';
import { LuDownload, LuFileSpreadsheet, LuFileQuestion, LuSearch, LuTrash2, LuUpload, LuEye, LuPencil, LuPlus } from 'react-icons/lu';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import AppShell from '../components/AppShell';
import AnswerKey from '../components/AnswerKey';
import MathText from '../components/MathText';
import { UploadProgress, Alert, Badge, Button, Card, Checkbox, Input, Modal, Select, EmptyState, ErrorState, PageHeader, PageLoader, cx, useConfirm, NoResults } from '../components/ui';
import { QUESTION_TYPE_LABELS, errorMessage, suggestCorrection } from '../utils';
import { keyText } from '../questionTypes';
import { useI18n } from '../i18n';

const COMPLEXITY_TONES = { easy: 'brand', medium: 'warn', hard: 'danger' };


function ImportDialog({ open, onClose, onImported }) {
  const { t, tn } = useI18n();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null); // 'preview' | 'import'
  const [progress, setProgress] = useState(null); // upload, 0..1
  const inputRef = useRef(null);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setError('');
  };

  const close = () => {
    reset();
    onClose();
  };

  const send = async (path) => {
    const formData = new FormData();
    formData.append('file', file);
    setProgress(0);
    return api.post(path, formData, { onUploadProgress: (e) => { if (e.total) setProgress(e.loaded / e.total); } });
  };

  const handlePreview = async () => {
    setError('');
    setBusy('preview');
    try {
      setPreview((await send('/admin/preview-questions/')).data);
    } catch (err) {
      setError(errorMessage(err, 'Could not read this file'));
    } finally {
      setBusy(null);
      setProgress(null);
    }
  };

  const handleImport = async () => {
    setError('');
    setBusy('import');
    try {
      const res = await send('/admin/upload-questions/');
      onImported(res.data.rows_imported);
      close();
    } catch (err) {
      setError(errorMessage(err, 'Import failed'));
    } finally {
      setBusy(null);
      setProgress(null);
    }
  };

  return (
    <Modal
      open={open}
      onClose={close}
      size={preview ? 'lg' : 'md'}
      title={t('Import questions from Excel')}
      description={t('Columns: title, complexity, type, options, correct_answers, max_score, and optionally tags and description. The template shows the format.')}
      footer={
        <>
          <Button variant="secondary" onClick={close}>{t('Cancel')}</Button>
          {!preview ? (
            <Button onClick={handlePreview} disabled={!file} loading={busy === 'preview'}>{t('Preview')}</Button>
          ) : (
            <Button onClick={handleImport} icon={LuUpload} loading={busy === 'import'}>
              {tn(preview.count, 'Import {{count}} question', 'Import {{count}} questions')}
            </Button>
          )}
        </>
      }
    >
      {!preview ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className={cx(
            'flex w-full flex-col items-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors',
            file ? 'border-brand/50 bg-brand-soft/40' : 'border-line hover:border-muted/50 hover:bg-sunken/50',
          )}
        >
          <LuFileSpreadsheet className={cx('h-8 w-8', file ? 'text-brand' : 'text-muted')} />
          <span className="mt-3 text-sm font-medium">{file ? file.name : t('Choose an .xlsx file')}</span>
          <span className="mt-1 text-xs text-muted">{file ? t('Click to choose a different file') : t('Excel 2007 or newer')}</span>
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={(e) => { setFile(e.target.files[0] || null); setError(''); }}
          />
        </button>
      ) : (
        <div className="space-y-2">
          {preview.questions.map((q, i) => (
            <div key={i} className="rounded-lg border border-line px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm font-medium"><span className="tabular me-2 text-muted">{i + 1}.</span><MathText text={q.title} /></p>
                <div className="flex gap-1.5">
                  <Badge>{t(QUESTION_TYPE_LABELS[q.type] || '')}</Badge>
                  <Badge tone={COMPLEXITY_TONES[q.complexity]}>{t(q.complexity)}</Badge>
                </div>
              </div>
              {q.correct_answers != null && (
                <p className="mt-1.5 text-xs text-muted">
                  {(q.type === 'single_choice' || q.type === 'multi_choice') && <>{t('Options:')} {q.options.join(' · ')}. </>}
                  {t('Answer:')} <span className="font-medium text-ink">{keyText(q.type, q.correct_answers, t)}</span>
                </p>
              )}
            </div>
          ))}
        </div>
      )}
      {busy && progress !== null && <UploadProgress value={progress} className="mt-4" />}
      {error && <Alert tone="danger" className="mt-4">{error}</Alert>}
    </Modal>
  );
}

function QuestionDialog({ question, onClose }) {
  const { t, tn } = useI18n();
  if (!question) return null;
  return (
    <Modal open onClose={onClose} title={<MathText text={question.title} />} description={question.description} size="md">
      <div className="mb-4 flex flex-wrap gap-1.5">
        <Badge>{t(QUESTION_TYPE_LABELS[question.type] || '')}</Badge>
        <Badge tone={COMPLEXITY_TONES[question.complexity]}>{t(question.complexity)}</Badge>
        <Badge tone="info">{tn(question.max_score, '{{count}} point', '{{count}} points')}</Badge>
        {(question.tags || []).map((tag) => <Badge key={tag}>#{tag}</Badge>)}
      </div>
      <AnswerKey question={question} />
    </Modal>
  );
}

function AdminQuestionsPage() {
  const { t, tn } = useI18n();
  const [questions, setQuestions] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [message, setMessage] = useState(null);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [complexityFilter, setComplexityFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [viewing, setViewing] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const navigate = useNavigate();
  const [confirmDialog, confirm] = useConfirm();

  const fetchQuestions = async () => {
    try {
      const res = await api.get('/admin/questions/');
      setQuestions(res.data || []);
    } catch (err) {
      setLoadError(err); // an error, not an empty bank
    }
  };

  useEffect(() => {
    fetchQuestions();
  }, []);

  const filtered = useMemo(() => (questions || []).filter((q) =>
    (!search || q.title.toLowerCase().includes(search.toLowerCase()))
    && (!typeFilter || q.type === typeFilter)
    && (!complexityFilter || q.complexity === complexityFilter)
    && (!tagFilter || (q.tags || []).includes(tagFilter))), [questions, search, typeFilter, complexityFilter, tagFilter]);

  // Every tag in the bank, most used first, for the filter
  const allTags = useMemo(() => {
    const counts = new Map();
    (questions || []).forEach((q) => (q.tags || []).forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [questions]);

  const allSelected = filtered.length > 0 && filtered.every((q) => selected.has(q.id));

  const toggle = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(filtered.map((q) => q.id)));

  const downloadTemplate = async () => {
    try {
      const res = await api.get('/admin/questions-template', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'questions_template.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setMessage({ tone: 'danger', text: errorMessage(err, 'Could not download the template') });
    }
  };

  const deleteQuestions = async (ids) => {
    const many = ids.length > 1;
    const ok = await confirm({
      title: many ? t('Delete {{n}} questions?', { n: ids.length }) : t('Delete this question?'),
      description: t('Questions used in an exam are archived instead: they leave the bank, but past results keep them. Unused questions are deleted.'),
      confirmLabel: t('Delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      let text;
      if (many) {
        const { data } = await api.post('/admin/questions/delete-bulk', { question_ids: ids });
        text = [data.deleted && t('{{n}} deleted', { n: data.deleted }), data.archived && t('{{n}} archived (used in exams, kept for results)', { n: data.archived })]
          .filter(Boolean).join(', ') || t('Nothing changed');
      } else {
        text = t((await api.delete(`/admin/questions/${ids[0]}`)).data.message);
      }
      setMessage({ tone: 'success', text });
      setSelected(new Set());
      fetchQuestions();
    } catch (err) {
      setMessage({ tone: 'danger', text: errorMessage(err, 'Failed to delete') });
    }
  };

  const filtersActive = search || typeFilter || complexityFilter || tagFilter;

  return (
    <AppShell>
      <PageHeader
        title={t('Question bank')}
        description={t('Questions you can reuse across exams. Questions with a set answer are graded automatically; written and image answers are graded by an examiner.')}
        actions={
          <>
            <Button variant="secondary" icon={LuDownload} onClick={downloadTemplate}>{t('Template')}</Button>
            <Button variant="secondary" icon={LuUpload} onClick={() => setImportOpen(true)}>{t('Import from Excel')}</Button>
            <Button icon={LuPlus} onClick={() => navigate('/admin-questions/new')}>{t('New question')}</Button>
          </>
        }
      />

      {message && <Alert tone={message.tone} className="mb-6" onClose={() => setMessage(null)}>{message.text}</Alert>}
      {loadError ? (
        <Card><ErrorState error={loadError} onRetry={() => { setLoadError(null); fetchQuestions(); }} /></Card>
      ) : questions === null ? (
        <PageLoader />
      ) : questions.length === 0 ? (
        <Card>
          <EmptyState
            icon={LuFileQuestion}
            paige="thinking"
            title={t('No questions yet')}
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button icon={LuPlus} onClick={() => navigate('/admin-questions/new')}>{t('Write a question')}</Button>
                <Button variant="secondary" icon={LuUpload} onClick={() => setImportOpen(true)}>{t('Import from Excel')}</Button>
                <Button variant="ghost" icon={LuDownload} onClick={downloadTemplate}>{t('Download template')}</Button>
              </div>
            }
          >
            {t('Write questions one at a time, or fill in the Excel template and import many at once.')}
          </EmptyState>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
            <div className="relative min-w-[200px] flex-1">
              <LuSearch className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search questions')} className="ps-9" />
            </div>
            <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="w-auto">
              <option value="">{t('All types')}</option>
              {Object.entries(QUESTION_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}
            </Select>
            <Select value={complexityFilter} onChange={(e) => setComplexityFilter(e.target.value)} className="w-auto">
              <option value="">{t('All difficulties')}</option>
              <option value="easy">{t('Easy')}</option>
              <option value="medium">{t('Medium')}</option>
              <option value="hard">{t('Hard')}</option>
            </Select>
            {allTags.length > 0 && (
              <Select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} className="w-auto" aria-label={t('Tag')}>
                <option value="">{t('All tags')}</option>
                {allTags.map(([tag, count]) => <option key={tag} value={tag}>#{tag} ({count})</option>)}
              </Select>
            )}
            {filtersActive && (
              <Button variant="ghost" onClick={() => { setSearch(''); setTypeFilter(''); setComplexityFilter(''); setTagFilter(''); }}>{t('Clear')}</Button>
            )}
          </div>

          {selected.size > 0 && (
            <div className="flex items-center justify-between gap-3 border-b border-line bg-brand-soft/40 px-4 py-2 text-sm">
              <span className="font-medium">{t('{{n}} selected', { n: selected.size })}</span>
              <Button variant="danger-ghost" size="sm" icon={LuTrash2} onClick={() => deleteQuestions([...selected])}>{t('Delete')}</Button>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th className="w-10"><Checkbox checked={allSelected} onChange={toggleAll} /></th>
                  <th>{t('Question')}</th>
                  <th>{t('Type')}</th>
                  <th>{t('Difficulty')}</th>
                  <th className="text-end">{t('Points')}</th>
                  <th className="w-24" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((q) => (
                  <tr key={q.id} className={cx(selected.has(q.id) && 'bg-brand-soft/30')}>
                    <td><Checkbox checked={selected.has(q.id)} onChange={() => toggle(q.id)} /></td>
                    <td className="max-w-md">
                      <button type="button" onClick={() => setViewing(q)} className="text-start font-medium hover:text-brand"><MathText text={q.title} /></button>
                      {q.tags?.length > 0 && <p className="mt-0.5 text-xs text-muted">{q.tags.map((tag) => `#${tag}`).join(' ')}</p>}
                    </td>
                    <td className="whitespace-nowrap text-muted">{t(QUESTION_TYPE_LABELS[q.type] || q.type)}</td>
                    <td><Badge tone={COMPLEXITY_TONES[q.complexity]}>{t(q.complexity)}</Badge></td>
                    <td className="tabular text-end">{q.max_score}</td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" icon={LuEye} onClick={() => setViewing(q)} aria-label={t('View')} />
                        <Button variant="ghost" size="sm" icon={LuPencil} onClick={() => navigate(`/admin-questions/${q.id}/edit`)} aria-label={t('Edit')} />
                        <Button variant="danger-ghost" size="sm" icon={LuTrash2} onClick={() => deleteQuestions([q.id])} aria-label={t('Delete')} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <NoResults
                query={search}
                suggestion={search ? suggestCorrection(search, (questions || []).flatMap((q) => [q.title, ...(q.tags || [])])) : null}
                onSuggest={setSearch}
                onClear={() => { setSearch(''); setTypeFilter(''); setComplexityFilter(''); setTagFilter(''); }}
              />
            )}
          </div>
          <div className="border-t border-line px-4 py-2.5 text-xs text-muted">
            {tn(questions.length, '{{n}} of {{count}} question', '{{n}} of {{count}} questions', { n: filtered.length })}
          </div>
        </Card>
      )}

      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={(count) => {
          setMessage({ tone: 'success', text: tn(count, 'Imported {{count}} question', 'Imported {{count}} questions') });
          fetchQuestions();
        }}
      />
      <QuestionDialog question={viewing} onClose={() => setViewing(null)} />
      {confirmDialog}
    </AppShell>
  );
}

export default AdminQuestionsPage;
