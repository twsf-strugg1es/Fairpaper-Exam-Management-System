import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import AppShell from '../components/AppShell';
import { Alert, Button, Card, CardHeader, Field, Input, PageHeader, PageLoader, Select } from '../components/ui';
import { ROLE_LABELS, errorMessage } from '../utils';
import { LANGUAGES, forgetDeviceLanguage, useI18n } from '../i18n';

// Account settings for anyone signed in: name, gender, language and password
function StudentProfilePage() {
  const { user, currentMembership, refreshUser, replaceToken } = useAuth();
  const { t } = useI18n();
  const [profile, setProfile] = useState(null);
  const [details, setDetails] = useState({ full_name: '', gender: '', language: '' });
  const [passwords, setPasswords] = useState({ old_password: '', new_password: '', confirm_password: '' });
  const [detailsMessage, setDetailsMessage] = useState(null);
  const [passwordMessage, setPasswordMessage] = useState(null);
  const [saving, setSaving] = useState(null); // 'details' | 'password'

  useEffect(() => {
    api.get('/profile/student')
      .then((res) => {
        setProfile(res.data);
        setDetails({ full_name: res.data.full_name || '', gender: res.data.gender || '', language: res.data.language || '' });
      })
      .catch((err) => setDetailsMessage({ tone: 'danger', text: errorMessage(err, 'Failed to load your profile') }));
  }, []);

  const saveDetails = async (e) => {
    e.preventDefault();
    setDetailsMessage(null);
    setSaving('details');
    try {
      const res = await api.put('/profile/student', { full_name: details.full_name.trim(), gender: details.gender || null, language: details.language || null });
      if (details.language !== (profile.language || '')) forgetDeviceLanguage(); // the account's choice now decides
      setProfile(res.data);
      await refreshUser(); // the name shows in the sidebar; the language applies straight away
      setDetailsMessage({ tone: 'success', text: t('Saved') });
    } catch (err) {
      setDetailsMessage({ tone: 'danger', text: errorMessage(err, 'Could not save') });
    } finally {
      setSaving(null);
    }
  };

  const changePassword = async (e) => {
    e.preventDefault();
    setPasswordMessage(null);
    if (passwords.new_password.length < 6) {
      setPasswordMessage({ tone: 'danger', text: t('The new password must be at least 6 characters.') });
      return;
    }
    if (passwords.new_password !== passwords.confirm_password) {
      setPasswordMessage({ tone: 'danger', text: t('The new passwords do not match.') });
      return;
    }
    setSaving('password');
    try {
      const res = await api.post('/profile/change-password', { old_password: passwords.old_password, new_password: passwords.new_password });
      // The change signs out every session, so this one carries on with the fresh token
      if (res.data?.access_token) replaceToken(res.data.access_token);
      setPasswords({ old_password: '', new_password: '', confirm_password: '' });
      setPasswordMessage({ tone: 'success', text: t('Password changed. Other devices are signed out.') });
    } catch (err) {
      setPasswordMessage({ tone: 'danger', text: errorMessage(err, 'Could not change the password') });
    } finally {
      setSaving(null);
    }
  };

  if (!profile && !detailsMessage) return <AppShell width="narrow"><PageLoader /></AppShell>;

  const unchanged = profile && details.full_name === (profile.full_name || '') && details.gender === (profile.gender || '')
    && details.language === (profile.language || '');
  const orgLanguage = LANGUAGES.find((l) => l.code === currentMembership?.default_language);

  return (
    <AppShell width="narrow">
      <PageHeader title={t('Account')} description={t('Your name is what examiners see on your results.')} />

      <div className="space-y-6">
        <Card>
          <CardHeader title={t('Personal details')} />
          <form onSubmit={saveDetails} className="space-y-5 p-5">
            <Field label={t('Email')} hint={t("Your email is your login and can't be changed here.")}>
              <Input value={profile?.email || ''} disabled />
            </Field>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label={t('Full name')} htmlFor="fullName">
                <Input id="fullName" value={details.full_name} onChange={(e) => setDetails({ ...details, full_name: e.target.value })} required />
              </Field>
              <Field label={t('Gender')} htmlFor="gender" optional>
                <Select id="gender" value={details.gender} onChange={(e) => setDetails({ ...details, gender: e.target.value })}>
                  <option value="">{t('Prefer not to say')}</option>
                  <option value="female">{t('Female')}</option>
                  <option value="male">{t('Male')}</option>
                  <option value="other">{t('Other')}</option>
                </Select>
              </Field>
              <Field label={t('Language')} htmlFor="language">
                <Select id="language" value={details.language} onChange={(e) => setDetails({ ...details, language: e.target.value })}>
                  <option value="">{orgLanguage ? t('Organization default ({{language}})', { language: orgLanguage.label }) : t('Organization default')}</option>
                  {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
                </Select>
              </Field>
            </div>
            {detailsMessage && <Alert tone={detailsMessage.tone}>{detailsMessage.text}</Alert>}
            <div className="flex justify-end">
              <Button type="submit" loading={saving === 'details'} disabled={unchanged}>{t('Save changes')}</Button>
            </div>
          </form>
        </Card>

        <Card>
          <CardHeader title={t('Password')} />
          <form onSubmit={changePassword} className="space-y-5 p-5">
            <Field label={t('Current password')} htmlFor="oldPassword">
              <Input id="oldPassword" type="password" autoComplete="current-password" value={passwords.old_password} onChange={(e) => setPasswords({ ...passwords, old_password: e.target.value })} required />
            </Field>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label={t('New password')} htmlFor="newPassword" hint={t('At least 6 characters.')}>
                <Input id="newPassword" type="password" autoComplete="new-password" value={passwords.new_password} onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })} required />
              </Field>
              <Field label={t('Confirm new password')} htmlFor="confirmPassword">
                <Input id="confirmPassword" type="password" autoComplete="new-password" value={passwords.confirm_password} onChange={(e) => setPasswords({ ...passwords, confirm_password: e.target.value })} required />
              </Field>
            </div>
            {passwordMessage && <Alert tone={passwordMessage.tone}>{passwordMessage.text}</Alert>}
            <div className="flex justify-end">
              <Button type="submit" variant="secondary" loading={saving === 'password'}>{t('Change password')}</Button>
            </div>
          </form>
        </Card>

        <Card>
          <CardHeader title={t('Organizations')} description={t('Switch between them from the sidebar.')} />
          <ul className="divide-y divide-line">
            {(user?.memberships || []).map((m) => (
              <li key={m.organization_id} className="flex items-center justify-between px-5 py-3 text-sm">
                <span>{m.organization_name}</span>
                <span className="text-muted">{t(ROLE_LABELS[m.role] || '')}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}

export default StudentProfilePage;
