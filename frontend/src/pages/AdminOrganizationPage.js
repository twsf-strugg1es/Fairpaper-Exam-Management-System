import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { LuCopy, LuRefreshCw, LuTrash2, LuPlus, LuX, LuCheck, LuLink, LuUpload, LuMail, LuClock } from 'react-icons/lu';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import AppShell from '../components/AppShell';
import ImportStudentsDialog from '../components/ImportStudentsDialog';
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Field, Input, PageHeader, PageLoader, Select, Tabs, useConfirm } from '../components/ui';
import { ROLE_LABELS, errorMessage } from '../utils';
import { LANGUAGES, useI18n } from '../i18n';

const signupLink = (code) => `${window.location.origin}/signup?code=${code}`;

function CopyButton({ text, label }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      window.prompt(t('Copy this link:'), text);
    }
  };
  return (
    <Button variant="secondary" size="sm" icon={copied ? LuCheck : LuCopy} onClick={copy}>
      {copied ? t('Copied') : label || t('Copy link')}
    </Button>
  );
}

// Every IANA timezone the browser knows (plus UTC and the current one, which older browsers may lack)
const timeZoneOptions = (current) => {
  const known = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : [];
  return [...new Set(['UTC', ...known, current].filter(Boolean))];
};
const currencyOptions = (current) => {
  const known = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('currency') : [];
  return [...new Set([...known, current].filter(Boolean))];
};
const displayNames = (locale, type) => {
  try {
    return new Intl.DisplayNames([locale], { type });
  } catch {
    return null; // older browsers: show the codes alone
  }
};

function RegionSettings({ org, onSave }) {
  const { t, locale } = useI18n();
  const initial = { timezone: org.timezone, default_language: org.default_language, country: org.country || '', currency: org.currency || '' };
  const [form, setForm] = useState(initial);
  const zones = useMemo(() => timeZoneOptions(org.timezone), [org.timezone]);
  const currencies = useMemo(() => currencyOptions(org.currency), [org.currency]);
  const regionNames = useMemo(() => displayNames(locale, 'region'), [locale]);
  const currencyNames = useMemo(() => displayNames(locale, 'currency'), [locale]);
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  let countryName = null;
  if (/^[A-Z]{2}$/.test(form.country)) {
    try {
      countryName = regionNames?.of(form.country);
    } catch {
      countryName = null;
    }
  }
  const unchanged = Object.keys(initial).every((key) => initial[key] === form[key]);

  return (
    <Card>
      <CardHeader title={t('Region and language')} description={t('Exam opening and closing times are shown in this timezone to everyone in the organization.')} />
      <form className="grid gap-5 p-5 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); onSave(form); }}>
        <Field label={t('Timezone')} htmlFor="timezone">
          <Select id="timezone" value={form.timezone} onChange={set('timezone')}>
            {zones.map((zone) => <option key={zone} value={zone}>{zone.replace(/_/g, ' ')}</option>)}
          </Select>
        </Field>
        <Field label={t('Default language')} htmlFor="defaultLanguage" hint={t("Members who haven't picked a language see this one.")}>
          <Select id="defaultLanguage" value={form.default_language} onChange={set('default_language')}>
            {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </Select>
        </Field>
        <Field label={t('Country')} htmlFor="country" optional hint={countryName || t('Two-letter code, such as BD or GB.')}>
          <Input
            id="country"
            value={form.country}
            onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase().replace(/[^A-Z]/g, '') })}
            maxLength={2}
            autoComplete="off"
          />
        </Field>
        <Field label={t('Currency')} htmlFor="currency" optional>
          <Select id="currency" value={form.currency} onChange={set('currency')}>
            <option value="">{t('Not set')}</option>
            {currencies.map((code) => {
              const name = currencyNames?.of(code);
              return <option key={code} value={code}>{name && name !== code ? `${code} · ${name}` : code}</option>;
            })}
          </Select>
        </Field>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" disabled={unchanged}>{t('Save')}</Button>
        </div>
      </form>
    </Card>
  );
}

// Organization settings for owners and admins: join codes, groups and members
function AdminOrganizationPage() {
  const { user, currentMembership, refreshUser } = useAuth();
  const { t } = useI18n();
  const [org, setOrg] = useState(null);
  const [groups, setGroups] = useState([]);
  const [members, setMembers] = useState([]);
  const [message, setMessage] = useState(null);
  const [tab, setTab] = useState('invite');
  const [orgName, setOrgName] = useState('');
  const [newGroup, setNewGroup] = useState('');
  const emptyMember = { email: '', full_name: '', role: 'examiner' };
  const [newMember, setNewMember] = useState(emptyMember);
  const [confirmDialog, confirm] = useConfirm();
  const [importOpen, setImportOpen] = useState(false);

  const isOwner = currentMembership?.role === 'owner';
  const assignableRoles = isOwner ? ['owner', 'admin', 'examiner', 'candidate'] : ['admin', 'examiner', 'candidate'];

  const load = useCallback(async () => {
    try {
      const [orgRes, groupsRes, membersRes] = await Promise.all([
        api.get('/org'), api.get('/org/groups'), api.get('/org/members'),
      ]);
      setOrg(orgRes.data);
      setOrgName(orgRes.data.name);
      setGroups(groupsRes.data);
      setMembers(membersRes.data);
    } catch (err) {
      setMessage({ tone: 'danger', text: errorMessage(err, 'Failed to load the organization') });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Run a change, show its outcome and reload; resolves to whether it worked
  const act = async (request, successText) => {
    setMessage(null);
    try {
      const res = await request();
      // successText may depend on the response, e.g. invited vs. added
      const text = typeof successText === 'function' ? successText(res?.data) : successText;
      if (text) setMessage({ tone: 'success', text });
      await load();
      return true;
    } catch (err) {
      setMessage({ tone: 'danger', text: errorMessage(err) });
      return false;
    }
  };

  const confirmThen = async (options, request, successText) => {
    if (await confirm(options)) act(request, successText);
  };

  if (!org) {
    return <AppShell>{message ? <Alert tone={message.tone}>{message.text}</Alert> : <PageLoader />}</AppShell>;
  }

  const candidates = members.filter((m) => m.role === 'candidate');
  const staff = members.filter((m) => m.role !== 'candidate');

  return (
    <AppShell>
      <PageHeader title={t('Organization')} description={t('Invite students, organize them into groups, and manage who can run exams.')} />

      {message && <Alert tone={message.tone} className="mb-6" onClose={() => setMessage(null)}>{message.text}</Alert>}

      <Tabs
        value={tab}
        onChange={setTab}
        className="mb-6"
        tabs={[
          { value: 'invite', label: t('Invite & groups'), count: groups.length },
          { value: 'students', label: t('Students'), count: candidates.length },
          { value: 'staff', label: t('Staff'), count: staff.length },
          { value: 'settings', label: t('Settings') },
        ]}
      />

      {tab === 'invite' && (
        <div className="space-y-6">
          <Card>
            <CardHeader title={t('Organization join code')} description={t('Anyone with this code can join as a student. Share the code, or the signup link that already contains it.')} />
            <div className="flex flex-wrap items-center gap-3 p-5">
              <span className="rounded-lg border border-dashed border-brand/50 bg-brand-soft/40 px-4 py-2 font-mono text-xl tracking-[0.25em] text-ink">
                {org.join_code}
              </span>
              <CopyButton text={signupLink(org.join_code)} />
              <Button
                variant="ghost"
                size="sm"
                icon={LuRefreshCw}
                onClick={() => confirmThen(
                  { title: t('Create a new join code?'), description: t('The current code and links stop working. Students who already joined are not affected.'), confirmLabel: t('New code') },
                  () => api.post('/org/join-code/regenerate'),
                  t('New join code created'),
                )}
              >
                {t('New code')}
              </Button>
            </div>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader
              title={t('Groups')}
              description={t('Batches, classes or hiring rounds. Each group has its own code that also puts students into the group. Exams can be limited to groups.')}
            />
            {groups.length === 0 ? (
              <EmptyState title={t('No groups yet')}>{t('Students who join with the organization code are in no group, and see exams open to everyone.')}</EmptyState>
            ) : (
              <div className="relative overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr><th>{t('Group')}</th><th>{t('Join code')}</th><th className="text-end">{t('Students')}</th><th /></tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => (
                      <tr key={g.id}>
                        <td className="font-medium">{g.name}</td>
                        <td><span className="code-chip">{g.join_code}</span></td>
                        <td className="tabular text-end">{g.member_count}</td>
                        <td>
                          <div className="flex justify-end gap-1">
                            <CopyButton text={signupLink(g.join_code)} label={t('Link')} />
                            <Button
                              variant="ghost"
                              size="sm"
                              icon={LuRefreshCw}
                              aria-label={t('New code')}
                              title={t('New code')}
                              onClick={() => confirmThen(
                                { title: t('New join code for {{name}}?', { name: g.name }), description: t('The current code and links for this group stop working.'), confirmLabel: t('New code') },
                                () => api.post(`/org/groups/${g.id}/join-code/regenerate`),
                                t('New group code created'),
                              )}
                            />
                            <Button
                              variant="danger-ghost"
                              size="sm"
                              icon={LuTrash2}
                              aria-label={t('Delete group')}
                              onClick={() => confirmThen(
                                { title: t('Delete {{name}}?', { name: g.name }), description: t('Its students stay in the organization. Exams limited to only this group become open to everyone.'), confirmLabel: t('Delete group'), danger: true },
                                () => api.delete(`/org/groups/${g.id}`),
                                t('Group deleted'),
                              )}
                            />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <form
              className="flex gap-2 border-t border-line p-4"
              onSubmit={(e) => {
                e.preventDefault();
                act(() => api.post('/org/groups', { name: newGroup.trim() }), t('Group created')).then((ok) => ok && setNewGroup(''));
              }}
            >
              <Input value={newGroup} onChange={(e) => setNewGroup(e.target.value)} placeholder={t('New group, e.g. HSC 2027 Batch A')} required />
              <Button type="submit" icon={LuPlus}>{t('Add')}</Button>
            </form>
          </Card>
        </div>
      )}

      {tab === 'students' && (
        <Card className="overflow-hidden">
          <CardHeader
            title={t('Students and their groups')}
            description={t('Put students into groups so they see the right exams.')}
            action={<Button size="sm" variant="secondary" icon={LuUpload} onClick={() => setImportOpen(true)}>{t('Import students')}</Button>}
          />
          {candidates.length === 0 ? (
            <EmptyState icon={LuLink} paige="hello" title={t('No students yet')}>{t('Import a list of students, or share the join code from the Invite tab.')}</EmptyState>
          ) : (
            <div className="relative overflow-x-auto">
              <table className="table">
                <thead><tr><th>{t('Student')}</th><th>{t('Groups')}</th><th className="w-48">{t('Add to group')}</th></tr></thead>
                <tbody>
                  {candidates.map((m) => {
                    const available = groups.filter((g) => !m.groups.some((mg) => mg.id === g.id));
                    return (
                      <tr key={m.user_id}>
                        <td>
                          <p className="font-medium">{m.full_name || m.email}</p>
                          {m.full_name && <p className="text-xs text-muted">{m.email}</p>}
                        </td>
                        <td>
                          <div className="flex flex-wrap gap-1">
                            {m.groups.length === 0 && <span className="text-muted">—</span>}
                            {m.groups.map((g) => (
                              <Badge key={g.id} tone="brand" className="pe-1">
                                {g.name}
                                <button
                                  type="button"
                                  title={t('Remove from {{name}}', { name: g.name })}
                                  className="rounded-full p-0.5 hover:bg-brand/20"
                                  onClick={() => act(() => api.delete(`/org/groups/${g.id}/members/${m.user_id}`))}
                                >
                                  <LuX className="h-3 w-3" />
                                </button>
                              </Badge>
                            ))}
                          </div>
                        </td>
                        <td>
                          {available.length > 0 && (
                            <Select
                              value=""
                              className="h-8 text-xs"
                              onChange={(e) => act(() => api.post(`/org/groups/${e.target.value}/members`, { user_ids: [m.user_id] }))}
                            >
                              <option value="">{t('Choose a group…')}</option>
                              {available.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                            </Select>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === 'staff' && (
        <Card className="overflow-hidden">
          <CardHeader
            title={t('Staff')}
            description={t('Examiners manage questions, exams and grading. Admins can also manage students, groups and staff. Only owners can manage other owners.')}
          />
          <div className="relative overflow-x-auto">
            <table className="table">
              <thead><tr><th>{t('Member')}</th><th className="w-44">{t('Role')}</th><th><span className="sr-only">{t('Actions')}</span></th></tr></thead>
              <tbody>
                {staff.map((m) => {
                  const locked = m.role === 'owner' && !isOwner;
                  const isMe = m.user_id === user?.id;
                  return (
                    <tr key={m.user_id}>
                      <td>
                        <p className="font-medium">
                          {m.full_name || m.email}
                          {isMe && <span className="ms-2 text-xs font-normal text-muted">{t('you')}</span>}
                          {m.invite_pending && <Badge tone="warn" icon={LuClock} className="ms-2 align-middle">{t('Invite pending')}</Badge>}
                        </p>
                        {m.full_name && <p className="text-xs text-muted">{m.email}</p>}
                      </td>
                      <td>
                        <Select
                          value={m.role}
                          disabled={locked}
                          className="h-8 text-xs"
                          onChange={(e) => act(() => api.patch(`/org/members/${m.user_id}`, { role: e.target.value }), t('Role updated'))}
                        >
                          {(locked ? ['owner'] : assignableRoles).map((r) => <option key={r} value={r}>{t(ROLE_LABELS[r])}</option>)}
                        </Select>
                      </td>
                      <td className="whitespace-nowrap text-end">
                        {!locked && m.invite_pending && (
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={LuMail}
                            onClick={() => act(() => api.post(`/org/members/${m.user_id}/invite`), t('New invite sent to {{email}}. Older links no longer work.', { email: m.email }))}
                          >
                            {t('Resend invite')}
                          </Button>
                        )}
                        {!locked && !isMe && (
                          <Button
                            variant="danger-ghost"
                            size="sm"
                            icon={LuTrash2}
                            aria-label={t('Remove')}
                            onClick={() => confirmThen(
                              { title: t('Remove {{name}}?', { name: m.email }), description: t('They lose access to this organization. Their account is kept.'), confirmLabel: t('Remove'), danger: true },
                              () => api.delete(`/org/members/${m.user_id}`),
                              t('Member removed'),
                            )}
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <form
            className="flex flex-wrap gap-2 border-t border-line p-4"
            onSubmit={(e) => {
              e.preventDefault();
              act(
                () => api.post('/org/members', newMember),
                (added) => (added.invited
                  ? t('Invite sent to {{email}}. They can sign in once they set a password.', { email: added.email })
                  : t('{{email}} added. We emailed them to let them know.', { email: added.email })),
              ).then((ok) => ok && setNewMember(emptyMember));
            }}
          >
            <Input
              type="email"
              value={newMember.email}
              onChange={(e) => setNewMember({ ...newMember, email: e.target.value })}
              placeholder={t('Email address')}
              aria-label={t('Email address')}
              className="min-w-[220px] flex-1"
              required
            />
            <Input
              value={newMember.full_name}
              onChange={(e) => setNewMember({ ...newMember, full_name: e.target.value })}
              placeholder={t('Name (optional)')}
              aria-label={t('Name (optional)')}
              maxLength={200}
              className="min-w-[180px] flex-1"
            />
            <Select value={newMember.role} onChange={(e) => setNewMember({ ...newMember, role: e.target.value })} className="w-36" aria-label={t('Role')}>
              {assignableRoles.map((r) => <option key={r} value={r}>{t(ROLE_LABELS[r])}</option>)}
            </Select>
            <Button type="submit" icon={LuPlus}>{t('Add')}</Button>
            <p className="w-full text-xs text-muted">{t('No account yet? We’ll email them an invite to set a password. The link lasts 7 days.')}</p>
          </form>
        </Card>
      )}

      {tab === 'settings' && (
        <div className="space-y-6">
          <Card>
            <CardHeader title={t('Organization name')} description={t('Shown to your staff and students.')} />
            <form
              className="flex gap-2 p-5"
              onSubmit={(e) => {
                e.preventDefault();
                act(async () => {
                  await api.patch('/org', { name: orgName.trim() });
                  await refreshUser(); // the name shows in the sidebar and organization picker
                }, t('Organization renamed'));
              }}
            >
              <Input value={orgName} onChange={(e) => setOrgName(e.target.value)} minLength={2} required />
              <Button type="submit" disabled={orgName.trim() === org.name}>{t('Save')}</Button>
            </form>
          </Card>
          <RegionSettings
            key={[org.timezone, org.default_language, org.country, org.currency].join('|')}
            org={org}
            onSave={(form) => act(async () => {
              await api.patch('/org', form);
              await refreshUser(); // the timezone and language come with the membership
            }, t('Settings saved'))}
          />
        </div>
      )}
      {confirmDialog}
      <ImportStudentsDialog open={importOpen} onClose={() => setImportOpen(false)} onImported={load} groups={groups} />
    </AppShell>
  );
}

export default AdminOrganizationPage;
