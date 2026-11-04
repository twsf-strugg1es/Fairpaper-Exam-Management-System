import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import AuthLayout from '../components/AuthLayout';
import { Alert, Button, Field, Input, EmailSuggestion } from '../components/ui';
import { errorMessage, viewerTimeZone } from '../utils';
import { useI18n } from '../i18n';

// Register a new organization (school, coaching center, company) together with its owner's account
function OrgSignupPage() {
  const { login } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [form, setForm] = useState({ organizationName: '', fullName: '', email: '', password: '', confirmPassword: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.password.length < 8) {
      setError(t('Password must be at least 8 characters long'));
      return;
    }
    if (form.password !== form.confirmPassword) {
      setError(t('Passwords do not match'));
      return;
    }

    setLoading(true);
    try {
      await api.post('/signup/organization', {
        organization_name: form.organizationName.trim(),
        full_name: form.fullName.trim(),
        email: form.email,
        password: form.password,
        timezone: viewerTimeZone(),
      });

      // Sign the new owner straight in
      const credentials = new URLSearchParams({ username: form.email, password: form.password });
      const tokenRes = await api.post('/token', credentials, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      localStorage.setItem('token', tokenRes.data.access_token);
      const me = await api.get('/me');
      login(tokenRes.data.access_token, me.data);
      navigate('/admin-organization');
    } catch (err) {
      setError(errorMessage(err, 'Registration failed. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title={t('Register your organization')}
      label="New organization"
      subtitle={t('A private space for your school, coaching center or company: your own question bank, exams, students and results.')}
      footer={<p>{t('Already have an account?')} <Link to="/login" className="link">{t('Log in')}</Link> {t('and create an organization from there.')}</p>}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <Field label={t('Organization name')} htmlFor="organizationName" hint={t('You can change this later.')}>
          <Input id="organizationName" value={form.organizationName} onChange={update('organizationName')} minLength={2} required autoFocus placeholder={t('e.g. Mirpur Science Coaching')} />
        </Field>
        <div className="border-t border-line pt-5">
          <p className="eyebrow mb-4">{t('Your account (owner)')}</p>
          <div className="space-y-5">
            <Field label={t('Full name')} htmlFor="fullName">
              <Input id="fullName" autoComplete="name" value={form.fullName} onChange={update('fullName')} required />
            </Field>
            <Field label={t('Email')} htmlFor="email">
              <Input id="email" type="email" autoComplete="email" value={form.email} onChange={update('email')} required />
              <EmailSuggestion value={form.email} onUse={(email) => setForm({ ...form, email })} />
            </Field>
            <Field label={t('Password')} htmlFor="password" hint={t('At least 8 characters.')}>
              <Input id="password" type="password" autoComplete="new-password" value={form.password} onChange={update('password')} required />
            </Field>
            <Field label={t('Confirm password')} htmlFor="confirmPassword">
              <Input id="confirmPassword" type="password" autoComplete="new-password" value={form.confirmPassword} onChange={update('confirmPassword')} required />
            </Field>
          </div>
        </div>

        {error && <Alert tone="danger">{error}</Alert>}

        <Button type="submit" size="lg" loading={loading} className="w-full">
          {t('Create organization')}
        </Button>
      </form>
    </AuthLayout>
  );
}

export default OrgSignupPage;
