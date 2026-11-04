import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LuArrowRight, LuBuilding2, LuCheck, LuLogOut, LuPlus } from 'react-icons/lu';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import { Alert, Button, Card, Input, Logo } from '../components/ui';
import { ROLE_LABELS, errorMessage } from '../utils';
import { useI18n } from '../i18n';

// Pick which organization to work in, join one with a code, or create a new one
function OrganizationsPage() {
  const { user, logout, refreshUser, selectOrganization, currentMembership } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [joinCode, setJoinCode] = useState('');
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null); // 'join' | 'create'
  const [showCreate, setShowCreate] = useState(false);

  const memberships = user?.memberships || [];

  const open = (organizationId) => {
    selectOrganization(organizationId);
    navigate('/');
  };

  const submit = async (e, kind, request, fallbackError) => {
    e.preventDefault();
    setError('');
    setBusy(kind);
    try {
      const response = await request();
      await refreshUser();
      open(response.data.organization_id);
    } catch (err) {
      setError(errorMessage(err, fallbackError));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-paper">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-5 py-5">
        <Logo />
        <div className="flex items-center gap-3 text-sm text-muted">
          <span className="hidden sm:inline">{user?.email}</span>
          <Button variant="ghost" size="sm" icon={LuLogOut} onClick={() => { logout(); navigate('/login'); }}>
            {t('Log out')}
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-lg px-5 pb-16 pt-8 sm:pt-14">
        <h1 className="text-2xl font-semibold tracking-tight">
          {memberships.length ? t('Choose an organization') : t('Join your organization')}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          {memberships.length
            ? t('You can switch between them any time from the sidebar.')
            : t("You're signed in but not part of an organization yet. Enter the join code your school, coaching center or employer gave you.")}
        </p>

        {error && <Alert tone="danger" className="mt-6" onClose={() => setError('')}>{error}</Alert>}

        {memberships.length > 0 && (
          <Card className="mt-6 divide-y divide-line overflow-hidden">
            {memberships.map((m) => {
              const active = m.organization_id === currentMembership?.organization_id;
              return (
                <button
                  key={m.organization_id}
                  type="button"
                  onClick={() => open(m.organization_id)}
                  className="group flex w-full items-center gap-4 px-4 py-3.5 text-start transition-colors hover:bg-sunken/60"
                >
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-sunken text-sm font-semibold">
                    {m.organization_name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{m.organization_name}</span>
                    <span className="block text-xs text-muted">{t(ROLE_LABELS[m.role] || m.role)}</span>
                  </span>
                  {active ? (
                    <LuCheck className="h-4 w-4 text-brand" />
                  ) : (
                    <LuArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" />
                  )}
                </button>
              );
            })}
          </Card>
        )}

        <Card className="mt-6 p-5">
          <form onSubmit={(e) => submit(e, 'join', () => api.post('/organizations/join', { join_code: joinCode.trim() }), 'Could not join')}>
            <label htmlFor="joinCode" className="label">{t('Join with a code')}</label>
            <div className="flex gap-2">
              <Input
                id="joinCode"
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                placeholder="K7M2QX9P"
                className="font-mono tracking-widest"
                autoComplete="off"
                required
              />
              <Button type="submit" loading={busy === 'join'}>{t('Join')}</Button>
            </div>
            <p className="hint">{t('Joining as a student. Staff are added by an organization admin.')}</p>
          </form>
        </Card>

        <div className="mt-6">
          {!showCreate ? (
            <button type="button" onClick={() => setShowCreate(true)} className="btn btn-ghost w-full border border-dashed border-line">
              <LuPlus className="h-4 w-4" />
              {t('Create a new organization')}
            </button>
          ) : (
            <Card className="p-5">
              <form onSubmit={(e) => submit(e, 'create', () => api.post('/organizations', { name: orgName.trim() }), 'Could not create the organization')}>
                <div className="mb-3 flex items-center gap-2">
                  <LuBuilding2 className="h-4 w-4 text-muted" />
                  <label htmlFor="orgName" className="text-sm font-medium">{t('New organization')}</label>
                </div>
                <div className="flex gap-2">
                  <Input id="orgName" value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder={t('Organization name')} minLength={2} required autoFocus />
                  <Button type="submit" loading={busy === 'create'}>{t('Create')}</Button>
                </div>
                <p className="hint">{t("For any team that runs its own exams. You'll be its owner.")}</p>
              </form>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
}

export default OrganizationsPage;
