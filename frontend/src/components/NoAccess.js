import React from 'react';
import { Link } from 'react-router-dom';
import { LuLock } from 'react-icons/lu';
import AppShell from './AppShell';
import { useAuth } from '../context/AuthContext';
import { useI18n } from '../i18n';
import { ROLE_LABELS } from '../utils';

// Instead of quietly sending someone elsewhere: why this page isn't theirs, and where they can go.
// need: staff | manager | candidate
export default function NoAccess({ need }) {
  const { t } = useI18n();
  const { user, currentMembership } = useAuth();
  const role = (ROLE_LABELS[currentMembership?.role] ? t(ROLE_LABELS[currentMembership.role]) : t('a member')).toLowerCase();
  const org = currentMembership?.organization_name || '';
  const title = {
    staff: t('This page is for staff'),
    manager: t('This page is for owners and admins'),
    candidate: t('This page is for students'),
  }[need] || t("You don't have access to this page");
  const why = {
    staff: t('It lets examiners manage exams, questions and results.'),
    manager: t("It changes the organization's members and settings."),
    candidate: t('It is where students take their exams.'),
  }[need];
  return (
    <AppShell>
      <div className="flex flex-col items-center px-6 py-20 text-center">
        <span className="mb-4 grid h-11 w-11 place-items-center rounded-full bg-sunken text-muted"><LuLock className="h-5 w-5" /></span>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">
          {why}{' '}
          {org ? t("You're signed in as {{role}} in {{org}}.", { role, org }) : t("You're signed in as {{email}}.", { email: user?.email })}
          {' '}{need === 'manager' && t('An owner or admin can change your role.')}
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Link to="/" className="btn btn-primary">{t('Go to my home page')}</Link>
          {user?.memberships?.length > 1 && <Link to="/organizations" className="btn btn-secondary">{t('Switch organization')}</Link>}
        </div>
      </div>
    </AppShell>
  );
}
