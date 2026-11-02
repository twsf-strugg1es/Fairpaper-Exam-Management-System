import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { LuSearch, LuUsers, LuUserMinus, LuLink } from 'react-icons/lu';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import AppShell from '../components/AppShell';
import { Alert, Badge, Button, Card, Input, Select, EmptyState, ErrorState, PageHeader, PageLoader, useConfirm, NoResults } from '../components/ui';
import { errorMessage, formatDate, suggestCorrection } from '../utils';
import { useI18n } from '../i18n';

function ScoreBar({ value }) {
  const tone = value >= 80 ? 'bg-brand' : value >= 50 ? 'bg-warn' : 'bg-danger';
  return (
    <span className="flex items-center gap-2.5">
      <span className="h-1.5 w-20 overflow-hidden rounded-full bg-sunken">
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span className="tabular w-9 text-end text-sm">{value}%</span>
    </span>
  );
}

function AdminStudentsPage() {
  const { isManager } = useAuth();
  const { t } = useI18n();
  const [students, setStudents] = useState(null);
  const [message, setMessage] = useState(null);
  const [search, setSearch] = useState('');
  const [groupFilter, setGroupFilter] = useState('');
  const [confirmDialog, confirm] = useConfirm();
  const [loadFailure, setLoadFailure] = useState(null);

  const fetchStudents = async () => {
    try {
      const res = await api.get('/admin/students/');
      setStudents(res.data || []);
    } catch (err) {
      setLoadFailure(err); // an error, not "no students yet"
    }
  };

  useEffect(() => {
    fetchStudents();
  }, []);

  const groups = useMemo(() => {
    const byId = new Map();
    (students || []).forEach((s) => s.groups?.forEach((g) => byId.set(g.id, g.name)));
    return [...byId.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [students]);

  const shown = (students || []).filter((s) => {
    const q = search.toLowerCase();
    const matches = !q || s.email?.toLowerCase().includes(q) || s.full_name?.toLowerCase().includes(q);
    const inGroup = !groupFilter || (groupFilter === 'none' ? !s.groups?.length : s.groups?.some((g) => g.id === groupFilter));
    return matches && inGroup;
  });

  const remove = async (student) => {
    const ok = await confirm({
      title: t('Remove {{name}}?', { name: student.full_name || student.email }),
      description: t('They lose access to your exams. Their account and past results are kept, and they can rejoin with a join code.'),
      confirmLabel: t('Remove'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.delete(`/admin/students/${student.id}`);
      setMessage({ tone: 'success', text: t('Student removed from the organization') });
      fetchStudents();
    } catch (err) {
      setMessage({ tone: 'danger', text: errorMessage(err) });
    }
  };

  return (
    <AppShell>
      <PageHeader
        title={t('Students')}
        description={t('Everyone who joined your organization as a student, with their average score across your exams.')}
        actions={isManager && (
          <Link to="/admin-organization" className="btn btn-secondary">
            <LuLink className="h-4 w-4" /> {t('Invite students')}
          </Link>
        )}
      />

      {message && <Alert tone={message.tone} className="mb-6" onClose={() => setMessage(null)}>{message.text}</Alert>}

      {loadFailure ? (
        <Card><ErrorState error={loadFailure} onRetry={() => { setLoadFailure(null); fetchStudents(); }} /></Card>
      ) : students === null ? (
        <PageLoader />
      ) : students.length === 0 ? (
        <Card>
          <EmptyState
            icon={LuUsers}
            paige="hello"
            title={t('No students yet')}
            action={isManager && <Link to="/admin-organization" className="btn btn-primary"><LuLink className="h-4 w-4" />{t('Get a join link')}</Link>}
          >
            {t("Students join by signing up with your organization's join code, or a group's code.")}
          </EmptyState>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap gap-2 border-b border-line p-3">
            <div className="relative min-w-[200px] flex-1">
              <LuSearch className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search by name or email')} className="ps-9" />
            </div>
            {groups.length > 0 && (
              <Select value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)} className="w-auto">
                <option value="">{t('All groups')}</option>
                {groups.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                <option value="none">{t('No group')}</option>
              </Select>
            )}
          </div>
          <div className="relative overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Student')}</th>
                  <th>{t('Groups')}</th>
                  <th>{t('Average')}</th>
                  <th>{t('Joined')}</th>
                  {isManager && <th />}
                </tr>
              </thead>
              <tbody>
                {shown.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <p className="font-medium">{s.full_name || s.email}</p>
                      {s.full_name && <p className="text-xs text-muted">{s.email}</p>}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {s.groups?.length ? s.groups.map((g) => <Badge key={g.id}>{g.name}</Badge>) : <span className="text-muted">—</span>}
                      </div>
                    </td>
                    <td><ScoreBar value={s.overall || 0} /></td>
                    <td className="whitespace-nowrap text-muted">{formatDate(s.joined_at)}</td>
                    {isManager && (
                      <td className="text-end">
                        <Button variant="danger-ghost" size="sm" icon={LuUserMinus} onClick={() => remove(s)} aria-label={t('Remove from organization')} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {shown.length === 0 && (
              <NoResults
                query={search}
                suggestion={search ? suggestCorrection(search, (students || []).flatMap((s) => [s.full_name, s.email])) : null}
                onSuggest={setSearch}
                onClear={() => { setSearch(''); setGroupFilter(''); }}
              />
            )}
          </div>
          <div className="border-t border-line px-4 py-2.5 text-xs text-muted">{t('{{n}} of {{total}} students', { n: shown.length, total: students.length })}</div>
        </Card>
      )}
      {confirmDialog}
    </AppShell>
  );
}

export default AdminStudentsPage;
