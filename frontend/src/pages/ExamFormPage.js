import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { LuArrowDown, LuArrowLeft, LuArrowUp, LuSearch, LuFileQuestion, LuPlus, LuShuffle, LuX } from 'react-icons/lu';
import api from '../api';
import AppShell from '../components/AppShell';
import { Alert, Badge, Button, Card, CardHeader, Checkbox, DraftNotice, EmptyState, Field, Input, PageHeader, PageLoader, Select, Switch, Textarea, cx, NoResults } from '../components/ui';
import { QUESTION_TYPE_LABELS, errorMessage, formatExamTime, fromZonedInput, timeZoneLabel, toZonedInput, suggestCorrection } from '../utils';
import { useToast } from '../components/Toaster';
import useDraft from '../hooks/useDraft';
import { useI18n } from '../i18n';

const defaultTimes = () => {
  const start = new Date();
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);
  const end = new Date(start.getTime() + 2 * 3600 * 1000);
  return { start: toZonedInput(start), end: toZonedInput(end) };
};

// Written the way the server stores question tags: lower case, no '#', single spaces, no quotes or backslashes
const normalizeTag = (tag) => (tag || '').replace(/["\\]/g, '').trim().replace(/^#+/, '').split(/\s+/).filter(Boolean).join(' ').toLowerCase();
const newKey = () => `${Date.now()}-${Math.random()}`;
const newRule = (section = null) => ({ key: newKey(), count: '5', complexity: '', tag: '', marks: '1', section });
const MAX_SECTIONS = 20;
const wholeIn = (value, min, max) => {
  const n = Number(value);
  return Number.isInteger(n) && n >= min && n <= max ? n : null;
};

// New exam (/admin-exams/new) or, with an exam ID, edit one that hasn't opened yet
function ExamFormPage() {
  const navigate = useNavigate();
  const { examId } = useParams();
  const editing = Boolean(examId);
  const { t, tn } = useI18n();
  const times = useMemo(defaultTimes, []);
  const [form, setForm] = useState({ title: '', start: times.start, end: times.end, duration: '60' });
  const [settings, setSettings] = useState({
    shuffle_questions: true,
    shuffle_options: true,
    require_fullscreen: true,
    block_copy_paste: true,
    max_violations: '3',
    results_release: 'immediate',
    show_rank: false,
    timing_mode: 'exam',
  });
  const [limits, setLimits] = useState({}); // questionId -> seconds in this exam, when it differs from the bank
  const [sameTime, setSameTime] = useState('30');
  const [questions, setQuestions] = useState([]);
  const [groups, setGroups] = useState([]);
  const [selectedQuestions, setSelectedQuestions] = useState(new Set());
  const [marks, setMarks] = useState({}); // questionId -> marks in this exam, when it differs from the bank
  const [rules, setRules] = useState([]); // random questions drawn for each student (pool rules)
  const [sections, setSections] = useState([]); // [{ key, title, minutes, instructions }]; none: the exam is one part
  const [questionSection, setQuestionSection] = useState({}); // questionId -> section key
  const [pickInto, setPickInto] = useState(null); // the section newly picked questions and rules go into
  const [selectedGroups, setSelectedGroups] = useState(new Set());
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({}); // shown on the field itself
  const [saving, setSaving] = useState(null); // 'draft' | 'publish' | 'save'
  const [existing, setExisting] = useState(editing ? null : {}); // the exam being edited
  const toast = useToast();
  // Unsaved changes survive being signed out or closing the tab (offered back on the next visit)
  const saved = useDraft(`exam:${examId || 'new'}`, {
    form, settings, selected: [...selectedQuestions], marks, rules, groups: [...selectedGroups], sections, questionSection, limits,
  }, { ready: !editing || Boolean(existing?.id) });
  const restoreDraft = () => {
    const d = saved.draft;
    setForm(d.form);
    setSettings(d.settings);
    setSelectedQuestions(new Set(d.selected || []));
    setMarks(d.marks || {});
    setRules(d.rules || []);
    setSelectedGroups(new Set(d.groups || []));
    setSections(d.sections || []);
    setQuestionSection(d.questionSection || {});
    setLimits(d.limits || {});
    setPickInto(d.sections?.[0]?.key || null);
    saved.keep();
  };

  useEffect(() => {
    api.get('/admin/questions/').then((res) => setQuestions(res.data || [])).catch(() => setQuestions([]));
    api.get('/org/groups').then((res) => setGroups(res.data || [])).catch(() => setGroups([]));
  }, []);

  useEffect(() => {
    if (!editing) return;
    api.get(`/admin/exams/${examId}`)
      .then(({ data }) => {
        setExisting(data);
        setForm({ title: data.title, start: toZonedInput(data.start_time), end: toZonedInput(data.end_time), duration: String(data.duration_minutes) });
        setSettings({
          shuffle_questions: data.shuffle_questions,
          shuffle_options: data.shuffle_options,
          require_fullscreen: data.require_fullscreen,
          block_copy_paste: data.block_copy_paste,
          max_violations: data.max_violations ? String(data.max_violations) : '',
          results_release: data.results_release || 'immediate',
          show_rank: Boolean(data.show_rank),
          timing_mode: data.timing_mode || 'exam',
        });
        setLimits(Object.fromEntries(data.questions
          .filter((q) => q.time_limit_seconds != null && q.time_limit_seconds !== q.bank_time_limit_seconds)
          .map((q) => [q.id, String(q.time_limit_seconds)])));
        setSelectedQuestions(new Set(data.questions.map((q) => q.id)));
        setMarks(Object.fromEntries(data.questions.filter((q) => q.max_score !== q.bank_max_score).map((q) => [q.id, String(q.max_score)])));
        setSelectedGroups(new Set(data.groups.map((g) => g.id)));
        const keys = (data.sections || []).map((section) => section.id);
        setSections((data.sections || []).map((section) => ({
          key: section.id, title: section.title, minutes: section.time_limit_minutes ? String(section.time_limit_minutes) : '', instructions: section.instructions || '',
        })));
        setQuestionSection(Object.fromEntries(data.questions.filter((q) => q.section != null).map((q) => [q.id, keys[q.section]])));
        setPickInto(keys[0] || null);
        setRules((data.pool_rules || []).map((r) => ({
          key: r.id, count: String(r.count), complexity: r.complexity || '', tag: r.tag || '', marks: String(r.marks),
          section: r.section != null ? keys[r.section] : null,
        })));
      })
      .catch((err) => { setExisting({ edit_blocked: errorMessage(err, 'Exam not found') }); });
  }, [editing, examId]);

  const update = (field) => (e) => {
    setForm({ ...form, [field]: e.target.value });
    if (fieldErrors[field]) setFieldErrors({ ...fieldErrors, [field]: undefined });
  };
  const toggleIn = (set, setter, id) => {
    const next = new Set(set);
    next.has(id) ? next.delete(id) : next.add(id);
    setter(next);
  };

  const visibleQuestions = questions.filter((q) => !search || q.title.toLowerCase().includes(search.toLowerCase()));
  const marksFor = (q) => {
    const n = Number(marks[q.id]);
    return Number.isInteger(n) && n >= 1 && n <= 100 ? n : q.max_score;
  };
  const perQuestion = settings.timing_mode === 'per_question';
  const secondsFor = (q) => (limits[q.id] !== undefined && limits[q.id] !== '' ? wholeIn(limits[q.id], 10, 3600) : q.default_time_limit_seconds ?? null);
  const fixedPoints = questions.filter((q) => selectedQuestions.has(q.id)).reduce((sum, q) => sum + marksFor(q), 0);
  // How many bank questions each rule could draw from (questions picked above are never drawn)
  const matching = (rule) => questions.filter((q) => !selectedQuestions.has(q.id)
    && (!rule.complexity || q.complexity === rule.complexity)
    && (!normalizeTag(rule.tag) || (q.tags || []).map(normalizeTag).includes(normalizeTag(rule.tag)))).length;
  const drawnCount = rules.reduce((sum, r) => sum + (wholeIn(r.count, 1, 200) || 0), 0);
  const totalPoints = fixedPoints + rules.reduce((sum, r) => sum + (wholeIn(r.count, 1, 200) || 0) * (wholeIn(r.marks, 1, 100) || 0), 0);
  const questionCount = selectedQuestions.size + drawnCount;
  const bankTags = [...new Set(questions.flatMap((q) => (q.tags || []).map(normalizeTag)).filter(Boolean))].sort();
  const setRule = (key, field) => (e) => setRules(rules.map((r) => (r.key === key ? { ...r, [field]: e.target.value } : r)));

  // Sections: each chosen question and rule sits in one; a key that no longer exists falls back to the first
  const sectionKeys = sections.map((section) => section.key);
  const into = sectionKeys.includes(pickInto) ? pickInto : sectionKeys[0] || null;
  const sectionFor = (key) => (sectionKeys.includes(key) ? key : sectionKeys[0]);
  const inSection = (key) => [...selectedQuestions].filter((id) => sectionFor(questionSection[id]) === key).length
    + rules.filter((r) => sectionFor(r.section) === key).reduce((sum, r) => sum + (wholeIn(r.count, 1, 200) || 0), 0);
  const timedMinutes = sections.reduce((sum, section) => sum + (wholeIn(section.minutes, 1, 600) || 0), 0);
  const timed = sections.some((section) => wholeIn(section.minutes, 1, 600));
  const setSection = (key, field) => (e) => setSections(sections.map((section) => (section.key === key ? { ...section, [field]: e.target.value } : section)));
  const pick = (id) => {
    if (!selectedQuestions.has(id) && into) setQuestionSection({ ...questionSection, [id]: into });
    toggleIn(selectedQuestions, setSelectedQuestions, id);
  };
  const pickAll = (ids) => {
    if (into) setQuestionSection({ ...questionSection, ...Object.fromEntries(ids.filter((id) => !selectedQuestions.has(id)).map((id) => [id, into])) });
    setSelectedQuestions(new Set([...selectedQuestions, ...ids]));
  };
  const splitIntoSections = () => {
    const first = { key: newKey(), title: t('Section {{n}}', { n: 1 }), minutes: '', instructions: '' };
    setSections([first, { key: newKey(), title: t('Section {{n}}', { n: 2 }), minutes: '', instructions: '' }]);
    setQuestionSection({}); // everything chosen so far starts in the first section
    setPickInto(first.key);
  };
  const moveSection = (i, j) => {
    const next = [...sections];
    [next[i], next[j]] = [next[j], next[i]];
    setSections(next);
  };
  // A removed section's questions and rules move to the one before it (or after, for the first)
  const removeSection = (i) => {
    if (sections.length === 1) {
      setSections([]);
      return;
    }
    const gone = sections[i].key;
    const heir = sections[i === 0 ? 1 : i - 1].key;
    setSections(sections.filter((_, j) => j !== i));
    setQuestionSection(Object.fromEntries(Object.entries(questionSection).map(([id, key]) => [id, key === gone ? heir : key])));
    setRules(rules.map((r) => (r.section === gone ? { ...r, section: heir } : r)));
    if (pickInto === gone) setPickInto(heir);
  };
  const sectionSelect = (value, onChange, label) => (
    <Select value={sectionFor(value)} onChange={(e) => onChange(e.target.value)} aria-label={label} className="h-8 w-auto max-w-[10rem] py-0 text-xs">
      {sections.map((section, i) => <option key={section.key} value={section.key}>{section.title.trim() || t('Section {{n}}', { n: i + 1 })}</option>)}
    </Select>
  );

  const windowMinutes = (fromZonedInput(form.end) - fromZonedInput(form.start)) / 60000;
  const scheduleProblem =
    !form.start || !form.end ? null
      : windowMinutes <= 0 ? t('The exam must close after it opens.')
        : Number(form.duration) > windowMinutes ? t('The window is only {{w}} minutes, so students who start late get less time than {{d}} minutes.', { w: Math.round(windowMinutes), d: form.duration })
          : null;

  const submit = async (publish) => {
    if (editing && existing?.edit_blocked) return;
    setError('');
    const problems = {};
    if (!form.title.trim()) problems.title = t('Give the exam a title, for example “Physics, chapter 3 test”.');
    if (!(Number(form.duration) > 0)) problems.duration = t('Set a duration in whole minutes, for example 60.');
    setFieldErrors(problems);
    if (Object.keys(problems).length) {
      document.getElementById(problems.title ? 'title' : 'duration')?.focus();
      return setError(t('Fix the fields marked in red above.'));
    }
    if (windowMinutes <= 0) return setError(t('The exam must close after it opens.'));
    if (selectedQuestions.size === 0 && rules.length === 0) return setError(t('Pick at least one question, or add a rule that draws random questions.'));
    for (const [i, rule] of rules.entries()) {
      if (!wholeIn(rule.count, 1, 200)) return setError(t('Random questions, rule {{n}}: draw a whole number of questions from 1 to 200.', { n: i + 1 }));
      if (!wholeIn(rule.marks, 1, 100)) return setError(t('Random questions, rule {{n}}: marks must be a whole number from 1 to 100.', { n: i + 1 }));
      if (wholeIn(rule.count, 1, 200) > matching(rule)) return setError(t('Random questions, rule {{n}}: only {{m}} questions in the bank match it.', { n: i + 1, m: matching(rule) }));
    }
    const badMarks = questions.find((q) => selectedQuestions.has(q.id) && marks[q.id] !== undefined && marks[q.id] !== '' && marksFor(q) !== Number(marks[q.id]));
    if (badMarks) return setError(t('Marks for “{{title}}” must be a whole number from 1 to 100.', { title: badMarks.title }));
    if (perQuestion && sections.some((section) => wholeIn(section.minutes, 1, 600))) {
      return setError(t('Timing each question can’t be combined with sections that have their own time. Clear the sections’ minutes, or time the exam as a whole.'));
    }
    const badLimit = perQuestion && questions.find((q) => selectedQuestions.has(q.id) && limits[q.id] !== undefined && limits[q.id] !== '' && !wholeIn(limits[q.id], 10, 3600));
    if (badLimit) return setError(t('The time for “{{title}}” must be a whole number of seconds from 10 to 3600, or empty for its default.', { title: badLimit.title }));
    for (const section of sections) {
      if (!section.title.trim()) return setError(t('Give every section a title.'));
      if (section.minutes !== '' && !wholeIn(section.minutes, 1, 600)) return setError(t('Section “{{title}}”: the time must be a whole number of minutes from 1 to 600, or empty for no limit.', { title: section.title }));
      if (inSection(section.key) === 0) return setError(t('The section “{{title}}” has no questions. Add some or remove it.', { title: section.title }));
    }

    setSaving(editing ? 'save' : publish ? 'publish' : 'draft');
    const payload = {
        title: form.title.trim(),
        // Send real instants (UTC), so the exam opens at the same moment wherever the server runs
        start_time: fromZonedInput(form.start).toISOString(),
        end_time: fromZonedInput(form.end).toISOString(),
        duration_minutes: parseInt(form.duration, 10),
        question_ids: [...selectedQuestions],
        pool_rules: rules.map((r) => ({
          count: wholeIn(r.count, 1, 200), complexity: r.complexity || null, tag: normalizeTag(r.tag) || null, marks: wholeIn(r.marks, 1, 100),
          section: sections.length ? sectionKeys.indexOf(sectionFor(r.section)) : null,
        })),
        sections: sections.map((section) => ({
          title: section.title.trim(), instructions: section.instructions.trim() || null, time_limit_minutes: wholeIn(section.minutes, 1, 600),
        })),
        question_sections: sections.length
          ? Object.fromEntries([...selectedQuestions].map((id) => [id, sectionKeys.indexOf(sectionFor(questionSection[id]))]))
          : {},
        // Only the questions whose marks differ from the question bank
        question_marks: Object.fromEntries(questions.filter((q) => selectedQuestions.has(q.id) && marksFor(q) !== q.max_score).map((q) => [q.id, marksFor(q)])),
        group_ids: [...selectedGroups],
        shuffle_questions: settings.shuffle_questions,
        shuffle_options: settings.shuffle_options,
        require_fullscreen: settings.require_fullscreen,
        block_copy_paste: settings.block_copy_paste,
        max_violations: settings.max_violations ? parseInt(settings.max_violations, 10) : null,
        results_release: settings.results_release,
        show_rank: settings.show_rank,
        timing_mode: settings.timing_mode,
        // Only the times that differ from each question's own
        question_time_limits: perQuestion
          ? Object.fromEntries(questions.filter((q) => selectedQuestions.has(q.id) && limits[q.id] && wholeIn(limits[q.id], 10, 3600) !== (q.default_time_limit_seconds ?? null))
            .map((q) => [q.id, wholeIn(limits[q.id], 10, 3600)]))
          : {},
    };
    try {
      let id = examId;
      if (editing) {
        await api.put(`/admin/exams/${examId}`, payload); // a published exam stays published
      } else {
        const res = await api.post('/admin/exams/', payload);
        id = res.data.id;
        if (publish) await api.post(`/admin/exams/${id}/publish`);
      }
      saved.clear();
      const who = selectedGroups.size
        ? groups.filter((g) => selectedGroups.has(g.id)).map((g) => g.name).join(', ')
        : t('everyone in your organization');
      const when = formatExamTime(payload.start_time);
      toast(editing
        ? { title: t('Changes saved'), body: t('{{title}} opens {{when}}.', { title: payload.title, when }), action: { label: t('View exam'), to: `/admin-exams/${id}` } }
        : publish
          ? { title: t('Exam published'), body: t('{{title}} opens {{when}} for {{who}}. Students see it on their dashboard.', { title: payload.title, when, who }), action: { label: t('View exam'), to: `/admin-exams/${id}` } }
          : { title: t('Saved as a draft'), body: t("Students can't see {{title}} until you publish it.", { title: payload.title }), action: { label: t('Keep editing'), to: `/admin-exams/${id}/edit` } });
      navigate('/admin-exams');
    } catch (err) {
      setError(errorMessage(err, editing ? 'Could not save the exam' : 'Could not create the exam'));
      setSaving(null);
    }
  };

  if (!existing) return <AppShell><PageLoader /></AppShell>;
  const locked = editing && existing.edit_blocked;

  return (
    <AppShell>
      <Link to="/admin-exams" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <LuArrowLeft className="h-4 w-4 rtl:-scale-x-100" /> {t('Exams')}
      </Link>
      <PageHeader title={editing ? t('Edit exam') : t('New exam')} />
      {saved.draft && !(editing && existing?.edit_blocked) && (
        <DraftNotice className="mb-6" savedAt={saved.savedAt} onRestore={restoreDraft} onDiscard={saved.clear} />
      )}
      {locked && <Alert tone="warn" className="mb-6" title={t('Editing is closed')}>{t(existing.edit_blocked)}</Alert>}

      {/* A disabled fieldset disables every input and switch inside it */}
      <fieldset disabled={!!locked} className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <Card>
            <CardHeader title={t('Details and schedule')} description={t('Students can start any time in the window. Each attempt lasts the duration, but never past the closing time.')} />
            <div className="grid gap-5 p-5 sm:grid-cols-2">
              <Field label={t('Title')} htmlFor="title" className="sm:col-span-2" error={fieldErrors.title}>
                <Input id="title" value={form.title} onChange={update('title')} placeholder={t('e.g. Physics, chapter 3 test')} autoFocus aria-invalid={Boolean(fieldErrors.title)} />
              </Field>
              <Field label={t('Opens')} htmlFor="start">
                <Input id="start" type="datetime-local" value={form.start} onChange={update('start')} />
              </Field>
              <Field label={t('Closes')} htmlFor="end">
                <Input id="end" type="datetime-local" value={form.end} onChange={update('end')} />
              </Field>
              <Field label={t('Duration (minutes)')} htmlFor="duration" error={fieldErrors.duration}>
                <Input id="duration" type="number" min="1" value={form.duration} onChange={update('duration')} aria-invalid={Boolean(fieldErrors.duration)} />
              </Field>
              <Field label={t('Timing')} htmlFor="timing">
                <Select id="timing" value={settings.timing_mode} onChange={(e) => setSettings({ ...settings, timing_mode: e.target.value })}>
                  <option value="exam">{t('One timer for the whole exam')}</option>
                  <option value="per_question">{t('A time for each question')}</option>
                </Select>
              </Field>
              {perQuestion && (
                <p className="text-sm leading-relaxed text-muted sm:col-span-2">
                  {t('Students see one question at a time and can’t go back. A question moves on when its time runs out or when they press Next. The duration still ends the exam.')}
                </p>
              )}
              {timeZoneLabel() && (
                <p className="text-sm text-muted sm:col-span-2">
                  {t("Times are in your organization's timezone ({{zone}}), not your device's.", { zone: timeZoneLabel() })}
                </p>
              )}
              {scheduleProblem && <Alert tone="warn" className="sm:col-span-2">{scheduleProblem}</Alert>}
            </div>
          </Card>

          <Card>
            <CardHeader
              title={t('Sections')}
              description={!sections.length
                ? t('Split the exam into parts, each with its own instructions and, if you like, its own time.')
                : timed
                  ? t('Students take the sections in order, one at a time. A section closes when its time runs out or when they finish it, and they can’t go back.')
                  : t('Sections group the questions under their own headings. Give a section a time and students take the sections in order.')}
              action={!sections.length && <Button variant="secondary" size="sm" icon={LuPlus} onClick={splitIntoSections}>{t('Split into sections')}</Button>}
            />
            {sections.length > 0 && (
              <>
                <ol className="divide-y divide-line">
                  {sections.map((section, i) => (
                    <li key={section.key} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_9rem_auto]">
                      <Field label={t('Section {{n}}', { n: i + 1 })} htmlFor={`section-${section.key}`}>
                        <Input id={`section-${section.key}`} value={section.title} onChange={setSection(section.key, 'title')} maxLength={120} placeholder={t('e.g. Part A: multiple choice')} />
                      </Field>
                      <Field label={t('Minutes')} optional htmlFor={`section-time-${section.key}`}>
                        <Input id={`section-time-${section.key}`} type="number" min={1} max={600} inputMode="numeric" value={section.minutes} onChange={setSection(section.key, 'minutes')} placeholder={t('No limit')} className="tabular-nums" />
                      </Field>
                      <div className="flex items-end gap-1 pb-0.5">
                        <Button variant="ghost" size="sm" icon={LuArrowUp} disabled={i === 0} onClick={() => moveSection(i, i - 1)} aria-label={t('Move section {{n}} up', { n: i + 1 })} />
                        <Button variant="ghost" size="sm" icon={LuArrowDown} disabled={i === sections.length - 1} onClick={() => moveSection(i, i + 1)} aria-label={t('Move section {{n}} down', { n: i + 1 })} />
                        <Button variant="ghost" size="sm" icon={LuX} onClick={() => removeSection(i)} aria-label={t('Remove section {{n}}', { n: i + 1 })} />
                      </div>
                      <Field label={t('Instructions')} optional htmlFor={`section-notes-${section.key}`} className="sm:col-span-3">
                        <Textarea id={`section-notes-${section.key}`} rows={2} maxLength={1000} value={section.instructions} onChange={setSection(section.key, 'instructions')} placeholder={t('e.g. Answer any three questions.')} />
                      </Field>
                      <p className="tabular text-xs text-muted sm:col-span-3">
                        {tn(inSection(section.key), '{{count}} question', '{{count}} questions')}
                        {wholeIn(section.minutes, 1, 600) ? ` · ${t('{{n}} min', { n: wholeIn(section.minutes, 1, 600) })}` : ` · ${t('no time of its own')}`}
                      </p>
                    </li>
                  ))}
                </ol>
                <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-3">
                  <Button variant="ghost" size="sm" icon={LuPlus} disabled={sections.length >= MAX_SECTIONS}
                    onClick={() => setSections([...sections, { key: newKey(), title: t('Section {{n}}', { n: sections.length + 1 }), minutes: '', instructions: '' }])}>
                    {t('Add a section')}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setSections([])}>{t('Back to one part')}</Button>
                </div>
                {timed && timedMinutes > Number(form.duration) && (
                  <Alert tone="warn" className="mx-5 mb-4">{t('The timed sections add up to {{n}} minutes but the exam lasts {{d}}, so it ends after {{d}} minutes.', { n: timedMinutes, d: form.duration })}</Alert>
                )}
              </>
            )}
          </Card>

          <Card>
            <CardHeader
              title={t('Questions')}
              description={t('Pick from your question bank.')}
              action={<Badge tone={questionCount ? 'brand' : 'neutral'}>{tn(questionCount, '{{count}} question', '{{count}} questions')} · {t('{{n}} pts', { n: totalPoints })}</Badge>}
            />
            {questions.length === 0 ? (
              <EmptyState icon={LuFileQuestion} title={t('Your question bank is empty')}>
                <Link to="/admin-questions" className="link">{t('Import questions')}</Link> {t('first, then come back to build the exam.')}
              </EmptyState>
            ) : (
              <>
                <div className="border-b border-line p-3">
                  <div className="relative">
                    <LuSearch className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                    <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search questions')} className="ps-9" />
                  </div>
                  {perQuestion && (
                    <p className="mt-2.5 flex flex-wrap items-center gap-2 text-sm text-muted">
                      {t('Same time for every chosen question:')}
                      <Input type="number" min={10} max={3600} inputMode="numeric" value={sameTime} onChange={(e) => setSameTime(e.target.value)}
                        aria-label={t('Seconds for every chosen question')} className="h-8 w-20 text-end tabular-nums" />
                      {t('s')}
                      <Button variant="secondary" size="sm" disabled={!wholeIn(sameTime, 10, 3600) || selectedQuestions.size === 0}
                        onClick={() => setLimits({ ...limits, ...Object.fromEntries([...selectedQuestions].map((id) => [id, String(wholeIn(sameTime, 10, 3600))])) })}>
                        {t('Apply')}
                      </Button>
                    </p>
                  )}
                  {sections.length > 0 && (
                    <p className="mt-2.5 flex flex-wrap items-center gap-2 text-sm text-muted">
                      {t('New picks go into')}
                      {sectionSelect(into, setPickInto, t('Section that new picks go into'))}
                    </p>
                  )}
                </div>
                <div className="max-h-[420px] divide-y divide-line overflow-y-auto">
                  {visibleQuestions.map((q) => (
                    <label
                      key={q.id}
                      className={cx('flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors hover:bg-sunken/50', selectedQuestions.has(q.id) && 'bg-brand-soft/30')}
                    >
                      <input
                        type="checkbox"
                        checked={selectedQuestions.has(q.id)}
                        onChange={() => pick(q.id)}
                        className="mt-0.5 h-4 w-4 accent-[rgb(var(--brand))]"
                      />
                      <span className="min-w-0 flex-1 text-sm">
                        <span className="block font-medium">{q.title}</span>
                        <span className="mt-0.5 block text-xs text-muted">
                          {t(QUESTION_TYPE_LABELS[q.type] || '')} · {t(q.complexity)} · {tn(q.max_score, '{{count}} pt', '{{count}} pts')}
                        </span>
                      </span>
                      {selectedQuestions.has(q.id) && (
                        <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted">
                          {sections.length > 0 && sectionSelect(questionSection[q.id], (key) => setQuestionSection({ ...questionSection, [q.id]: key }), t('Section for “{{title}}”', { title: q.title }))}
                          {perQuestion && (
                            <>
                              <Input
                                type="number"
                                min={10}
                                max={3600}
                                inputMode="numeric"
                                value={limits[q.id] ?? ''}
                                placeholder={q.default_time_limit_seconds ? String(q.default_time_limit_seconds) : t('No limit')}
                                onChange={(e) => setLimits({ ...limits, [q.id]: e.target.value })}
                                aria-label={t('Seconds for “{{title}}”', { title: q.title })}
                                className={cx('h-8 w-20 text-end tabular-nums', secondsFor(q) == null && 'placeholder:text-faint')}
                              />
                              {t('s')}
                            </>
                          )}
                          <Input
                            type="number"
                            min={1}
                            max={100}
                            step={1}
                            inputMode="numeric"
                            value={marks[q.id] ?? String(q.max_score)}
                            onChange={(e) => setMarks({ ...marks, [q.id]: e.target.value })}
                            onBlur={() => { if (marks[q.id] === String(q.max_score)) setMarks((m) => { const next = { ...m }; delete next[q.id]; return next; }); }}
                            aria-label={t('Marks for “{{title}}” in this exam', { title: q.title })}
                            className={cx('h-8 w-16 text-end tabular-nums', marksFor(q) !== q.max_score && 'border-brand')}
                          />
                          {t('pts')}
                        </span>
                      )}
                    </label>
                  ))}
                </div>
                {visibleQuestions.length === 0 && (
                  <NoResults
                    query={search}
                    suggestion={suggestCorrection(search, questions.flatMap((q) => [q.title, ...(q.tags || [])]))}
                    onSuggest={setSearch}
                    onClear={() => setSearch('')}
                  />
                )}
                <div className="flex gap-2 border-t border-line px-4 py-2.5">
                  <Button variant="ghost" size="sm" onClick={() => pickAll(visibleQuestions.map((q) => q.id))}>
                    {search ? t('Select shown') : t('Select all')}
                  </Button>
                  {selectedQuestions.size > 0 && (
                    <Button variant="ghost" size="sm" onClick={() => setSelectedQuestions(new Set())}>{t('Clear')}</Button>
                  )}
                </div>

                {/* Random questions: each student gets their own draw when they start */}
                <div className="border-t border-line p-4">
                  <div className="flex items-start gap-3">
                    <LuShuffle className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{t('Random questions')}</p>
                      <p className="mt-0.5 text-sm text-muted">
                        {t('Each student gets their own random set, drawn when they start and kept if they reload. Questions picked above are never drawn.')}
                      </p>
                    </div>
                  </div>
                  {rules.length > 0 && (
                    <ul className="mt-4 space-y-2.5">
                      {rules.map((rule, i) => {
                        const found = matching(rule);
                        const short = (wholeIn(rule.count, 1, 200) || 0) > found;
                        return (
                          <li key={rule.key} className="flex flex-wrap items-center gap-x-2 gap-y-2 rounded-lg border border-line bg-sunken/40 px-3 py-2.5 text-sm">
                            <span className="text-muted">{t('Draw')}</span>
                            <Input type="number" min={1} max={200} inputMode="numeric" value={rule.count} onChange={setRule(rule.key, 'count')}
                              aria-label={t('How many questions rule {{n}} draws', { n: i + 1 })} className="h-8 w-16 text-end tabular-nums" />
                            <Select value={rule.complexity} onChange={setRule(rule.key, 'complexity')} aria-label={t('Difficulty for rule {{n}}', { n: i + 1 })} className="h-8 w-auto py-0">
                              <option value="">{t('any difficulty')}</option>
                              <option value="easy">{t('easy')}</option>
                              <option value="medium">{t('medium')}</option>
                              <option value="hard">{t('hard')}</option>
                            </Select>
                            <span className="text-muted">{t('questions tagged')}</span>
                            <Input value={rule.tag} onChange={setRule(rule.key, 'tag')} list="pool-tags" placeholder={t('any tag')}
                              aria-label={t('Tag for rule {{n}}', { n: i + 1 })} className="h-8 w-36" />
                            <span className="text-muted">{t('worth')}</span>
                            <Input type="number" min={1} max={100} inputMode="numeric" value={rule.marks} onChange={setRule(rule.key, 'marks')}
                              aria-label={t('Marks for each question rule {{n}} draws', { n: i + 1 })} className="h-8 w-16 text-end tabular-nums" />
                            <span className="text-muted">{t('pts each')}</span>
                            {sections.length > 0 && sectionSelect(rule.section, (key) => setRules(rules.map((r) => (r.key === rule.key ? { ...r, section: key } : r))), t('Section for rule {{n}}', { n: i + 1 }))}
                            <span className={cx('ms-auto text-xs tabular-nums', short ? 'font-medium text-danger' : 'text-muted')}>
                              {short ? t('Only {{n}} match', { n: found }) : tn(found, '{{count}} matches', '{{count}} match')}
                            </span>
                            <Button variant="ghost" size="sm" className="btn-icon" onClick={() => setRules(rules.filter((r) => r.key !== rule.key))}
                              aria-label={t('Remove rule {{n}}', { n: i + 1 })}>
                              <LuX className="h-4 w-4" />
                            </Button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  <datalist id="pool-tags">{bankTags.map((tag) => <option key={tag} value={tag} />)}</datalist>
                  {perQuestion && rules.length > 0 && <p className="mt-3 text-xs text-muted">{t('Random questions use the time set on each question in the bank.')}</p>}
                  <Button variant="secondary" size="sm" icon={LuPlus} className="mt-3" onClick={() => setRules([...rules, newRule(into)])}>
                    {rules.length ? t('Add another rule') : t('Add a rule')}
                  </Button>
                </div>
              </>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title={t('Who can take it')} />
            <div className="space-y-3 p-5">
              {groups.length === 0 ? (
                <p className="text-sm text-muted">
                  {t('Every student in your organization. To limit it,')} <Link to="/admin-organization" className="link">{t('create groups')}</Link>.
                </p>
              ) : (
                <>
                  {groups.map((g) => (
                    <Checkbox key={g.id} checked={selectedGroups.has(g.id)} onChange={() => toggleIn(selectedGroups, setSelectedGroups, g.id)}>
                      <span className="flex-1">{g.name}</span>
                      <span className="text-xs text-muted">{g.member_count}</span>
                    </Checkbox>
                  ))}
                  <p className="hint">{selectedGroups.size ? t('Only students in the ticked groups.') : t('None ticked: every student in your organization.')}</p>
                </>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title={t('Integrity')} description={t('What the exam page enforces and records.')} />
            <div className="space-y-5 p-5">
              <Switch
                label={t('Require fullscreen')}
                description={t('Questions are hidden whenever the student leaves fullscreen.')}
                checked={settings.require_fullscreen}
                onChange={(v) => setSettings({ ...settings, require_fullscreen: v })}
              />
              <Switch
                label={t('Shuffle question order')}
                description={t('Each student gets their own order.')}
                checked={settings.shuffle_questions}
                onChange={(v) => setSettings({ ...settings, shuffle_questions: v })}
              />
              <Switch
                label={t('Shuffle answer options')}
                checked={settings.shuffle_options}
                onChange={(v) => setSettings({ ...settings, shuffle_options: v })}
              />
              <Switch
                label={t('Block copy and paste')}
                description={t('Attempts are blocked, recorded, and the clipboard is emptied during the exam.')}
                checked={settings.block_copy_paste}
                onChange={(v) => setSettings({ ...settings, block_copy_paste: v })}
              />
              <Field
                label={t('Submit automatically after')}
                htmlFor="maxViolations"
                hint={t('A violation is leaving the exam (another tab, window or app) or exiting fullscreen. Every violation is recorded either way.')}
              >
                <Select id="maxViolations" value={settings.max_violations} onChange={(e) => setSettings({ ...settings, max_violations: e.target.value })}>
                  <option value="">{t('Never (only record violations)')}</option>
                  {[1, 2, 3, 5, 10].map((n) => <option key={n} value={n}>{tn(n, '{{count}} violation', '{{count}} violations')}</option>)}
                </Select>
              </Field>
              <Field
                label={t('Students see their results')}
                htmlFor="resultsRelease"
                hint={t('Until then, students see that their exam was submitted, but not their score or the correct answers.')}
              >
                <Select id="resultsRelease" value={settings.results_release} onChange={(e) => setSettings({ ...settings, results_release: e.target.value })}>
                  <option value="immediate">{t('Right after they submit')}</option>
                  <option value="on_close">{t('When the exam closes')}</option>
                  <option value="manual">{t('When I release them')}</option>
                </Select>
              </Field>
              <Switch
                label={t('Show students their rank')}
                description={t('With their results, students see their place on the merit list, e.g. 3rd of 40.')}
                checked={settings.show_rank}
                onChange={(v) => setSettings({ ...settings, show_rank: v })}
              />
            </div>
          </Card>
        </div>
      </fieldset>

      <div className="sticky bottom-0 z-10 -mx-4 mt-8 border-t border-line bg-paper px-4 py-4 sm:-mx-8 sm:px-8">
        {error && <Alert tone="danger" className="mb-3">{error}</Alert>}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button variant="ghost" onClick={() => navigate('/admin-exams')}>{t('Cancel')}</Button>
          {editing ? (
            <Button loading={saving === 'save'} disabled={!!saving || !!locked} onClick={() => submit(false)}>{t('Save changes')}</Button>
          ) : (
            <>
              <Button variant="secondary" loading={saving === 'draft'} disabled={!!saving} onClick={() => submit(false)}>{t('Save as draft')}</Button>
              <Button loading={saving === 'publish'} disabled={!!saving} onClick={() => submit(true)}>{t('Create and publish')}</Button>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}

export default ExamFormPage;
