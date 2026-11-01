import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { LuArrowLeft, LuCopy, LuX } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import AnswerKeyEditor, { EMPTY_KEY, keyFromQuestion, keyPayload, keyProblem } from '../components/AnswerKeyEditor';
import { Alert, Button, Card, CardHeader, DraftNotice, ErrorState, Field, Input, PageHeader, PageLoader, Select, Textarea } from '../components/ui';
import { useToast } from '../components/Toaster';
import useDraft from '../hooks/useDraft';
import { QUESTION_TYPE_LABELS, errorMessage } from '../utils';
import { useI18n } from '../i18n';

const EMPTY = { title: '', description: '', type: 'single_choice', complexity: 'medium', max_score: '1', tags: [], ...EMPTY_KEY };

// Tags as chips: Enter or comma adds one, suggestions come from tags already in the bank
function TagInput({ value, onChange, suggestions }) {
  const { t } = useI18n();
  const [draft, setDraft] = useState('');
  const add = (raw) => {
    const tag = raw.trim().replace(/^#/, '').toLowerCase();
    if (tag && !value.includes(tag)) onChange([...value, tag]);
    setDraft('');
  };
  return (
    <div>
      {value.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-1.5">
          {value.map((tag) => (
            <li key={tag} className="tag gap-1 normal-case">
              #{tag}
              <button type="button" onClick={() => onChange(value.filter((x) => x !== tag))} className="-me-1 rounded p-0.5 hover:text-danger" aria-label={t('Remove {{tag}}', { tag })}>
                <LuX className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Input
        id="tags"
        list="tag-suggestions"
        value={draft}
        placeholder={t('e.g. physics, class 9')}
        onChange={(e) => (e.target.value.endsWith(',') ? add(e.target.value.slice(0, -1)) : setDraft(e.target.value))}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(draft); } }}
        onBlur={() => draft && add(draft)}
      />
      <datalist id="tag-suggestions">
        {suggestions.filter((s) => !value.includes(s)).map((s) => <option key={s} value={s} />)}
      </datalist>
    </div>
  );
}

// Write a question (/admin-questions/new) or edit one (/admin-questions/:id/edit)
function QuestionEditorPage() {
  const { questionId } = useParams();
  const editing = Boolean(questionId);
  const navigate = useNavigate();
  const { t } = useI18n();
  const [form, setForm] = useState(editing ? null : EMPTY);
  const [locked, setLocked] = useState(null);
  const [allTags, setAllTags] = useState([]);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState(null);
  const [reload, setReload] = useState(0);
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  const titleBox = useRef(null);
  const saved = useDraft(`question:${questionId || 'new'}`, form, { ready: Boolean(form) && !locked });

  useEffect(() => {
    api.get('/admin/questions/')
      .then((res) => setAllTags([...new Set(res.data.flatMap((q) => q.tags || []))].sort()))
      .catch(() => setAllTags([]));
  }, []);

  useEffect(() => {
    if (!editing) return;
    // Opening another question (e.g. a fresh duplicate) reuses this page: drop the old one first
    setForm(null);
    setLocked(null);
    setError('');
    setLoadError(null);
    api.get(`/admin/questions/${questionId}`)
      .then(({ data }) => {
        setForm({
          ...EMPTY,
          title: data.title,
          description: data.description || '',
          type: data.type,
          complexity: data.complexity,
          max_score: String(data.max_score),
          tags: data.tags || [],
          ...keyFromQuestion(data),
        });
        setLocked(data.edit_blocked);
      })
      .catch((err) => setLoadError(err));
  }, [editing, questionId, reload]);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  // A blank goes where the cursor is, and the cursor lands after it
  const insertBlank = () => {
    const box = titleBox.current;
    const at = box ? box.selectionStart : form.title.length;
    const end = box ? box.selectionEnd : at;
    const before = form.title.slice(0, at);
    const blank = `${before && !before.endsWith(' ') ? ' ' : ''}___`;
    setForm({ ...form, title: before + blank + form.title.slice(end) });
    requestAnimationFrame(() => {
      box?.focus();
      box?.setSelectionRange(at + blank.length, at + blank.length);
    });
  };

  // The same checks the server makes, so the teacher sees them before saving
  const problem = useMemo(() => {
    if (!form) return null;
    if (!form.title.trim()) return t('Write the question.');
    if (!(Number(form.max_score) >= 1)) return t('Points must be at least 1.');
    return keyProblem(form, t);
  }, [form, t]);

  const save = async () => {
    setError('');
    if (problem) return setError(problem);
    setSaving(true);
    const payload = {
      title: form.title,
      description: form.description || null,
      type: form.type,
      complexity: form.complexity,
      max_score: parseInt(form.max_score, 10),
      ...keyPayload(form),
      tags: form.tags,
    };
    try {
      if (editing) await api.put(`/admin/questions/${questionId}`, payload);
      else await api.post('/admin/questions/', payload);
      saved.clear();
      toast(editing
        ? { title: t('Changes saved'), body: form.title }
        : { title: t('Question added to your bank'), body: form.title, action: { label: t('Write another question'), to: '/admin-questions/new' } });
      navigate('/admin-questions');
    } catch (err) {
      setError(errorMessage(err, 'Could not save the question'));
      setSaving(false);
    }
  };

  const duplicate = async () => {
    try {
      const { data } = await api.post(`/admin/questions/${questionId}/duplicate`);
      navigate(`/admin-questions/${data.id}/edit`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  if (!form) {
    return (
      <AppShell width="narrow">
        {loadError ? (
          <ErrorState
            error={loadError}
            onRetry={() => setReload((n) => n + 1)}
            action={<Link to="/admin-questions" className="btn btn-secondary">{t('Back to the question bank')}</Link>}
          />
        ) : <PageLoader variant="sheet" />}
      </AppShell>
    );
  }

  return (
    <AppShell width="narrow">
      <Link to="/admin-questions" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {t('Question bank')}
      </Link>
      <PageHeader title={editing ? t('Edit question') : t('New question')} />
      {saved.draft && !locked && (
        <DraftNotice className="mb-6" savedAt={saved.savedAt} onRestore={() => { setForm({ ...EMPTY, ...saved.draft }); saved.keep(); }} onDiscard={saved.clear} />
      )}

      {locked && (
        <Alert tone="warn" className="mb-6" title={t('Editing is closed')}>
          <p>{t(locked)}</p>
          <Button size="sm" variant="secondary" icon={LuCopy} className="mt-2" onClick={duplicate}>{t('Duplicate and edit the copy')}</Button>
        </Alert>
      )}

      <fieldset disabled={!!locked} className="min-w-0 space-y-6">
        <Card>
          <CardHeader title={t('Details')} />
          <div className="grid gap-5 p-5 sm:grid-cols-3">
            <Field
              label={form.type === 'true_false' ? t('Statement') : t('Question')}
              htmlFor="title"
              className="sm:col-span-3"
            >
              <Textarea ref={titleBox} id="title" rows={3} value={form.title} onChange={set('title')} autoFocus={!editing} />
              {form.type === 'fill_blank' && (
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <Button variant="secondary" size="sm" onClick={insertBlank}>{t('Insert a blank')}</Button>
                  <p className="text-xs text-muted">{t('Write ___ (three underscores) where each blank goes.')}</p>
                </div>
              )}
            </Field>
            <Field label={t('Notes')} htmlFor="description" optional hint={t('Only staff see this, for example the source or how to grade it.')} className="sm:col-span-3">
              <Textarea id="description" rows={2} value={form.description} onChange={set('description')} />
            </Field>
            <Field label={t('Type')} htmlFor="type">
              <Select id="type" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value, correct: e.target.value === 'single_choice' ? form.correct.slice(0, 1) : form.correct })}>
                {Object.entries(QUESTION_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}
              </Select>
            </Field>
            <Field label={t('Difficulty')} htmlFor="complexity">
              <Select id="complexity" value={form.complexity} onChange={set('complexity')}>
                <option value="easy">{t('Easy')}</option>
                <option value="medium">{t('Medium')}</option>
                <option value="hard">{t('Hard')}</option>
              </Select>
            </Field>
            <Field label={t('Points')} htmlFor="points">
              <Input id="points" type="number" min="1" max="100" value={form.max_score} onChange={set('max_score')} />
            </Field>
          </div>
        </Card>

        <AnswerKeyEditor form={form} setForm={setForm} />

        <Card>
          <CardHeader title={t('Tags')} description={t('Find questions by topic, chapter or class. Press Enter or type a comma after each tag.')} />
          <div className="p-5">
            <TagInput value={form.tags} onChange={(tags) => setForm({ ...form, tags })} suggestions={allTags} />
          </div>
        </Card>
      </fieldset>

      <div className="sticky bottom-0 z-10 -mx-4 mt-8 border-t border-line bg-paper px-4 py-4 sm:-mx-8 sm:px-8">
        {error && <Alert tone="danger" className="mb-3">{error}</Alert>}
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={() => navigate('/admin-questions')}>{t('Cancel')}</Button>
          <Button loading={saving} disabled={saving || !!locked} onClick={save}>{editing ? t('Save changes') : t('Add question')}</Button>
        </div>
      </div>
    </AppShell>
  );
}

export default QuestionEditorPage;
