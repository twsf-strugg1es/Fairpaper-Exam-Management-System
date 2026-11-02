import React, { useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { SIGNED_OUT_KEY, useAuth } from '../context/AuthContext';
import api from '../api';
import AuthLayout from '../components/AuthLayout';
import { Alert, Button, Checkbox, Field, Input, EmailSuggestion } from '../components/ui';
import { errorMessage } from '../utils';
import { LANGUAGES, useI18n } from '../i18n';

// Where Fairpaper signed this person out, if it did (idle or expired), read once per visit to this page
const readSignedOut = () => {
  try {
    return JSON.parse(sessionStorage.getItem(SIGNED_OUT_KEY) || 'null');
  } catch {
    return null;
  }
};
// Only paths inside the app, never another site (//evil.example)
const safePath = (path) => (typeof path === 'string' && path.startsWith('/') && !path.startsWith('//') && !path.startsWith('/login') ? path : null);

function LoginPage() {
  const [signedOut] = useState(readSignedOut);
  const [email, setEmail] = useState(signedOut?.email || '');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saveLogin, setSaveLogin] = useState(false);
  const { login } = useAuth();
  const { t, language, setLanguage } = useI18n();
  const navigate = useNavigate();
  const { state } = useLocation();
  const notice = state?.notice;
  const returnTo = safePath(state?.from) || safePath(signedOut?.path);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      const response = await api.post('/token', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      const { access_token } = response.data;
      localStorage.setItem('token', access_token);

      try {
        const userRes = await api.get('/me');
        login(access_token, userRes.data, saveLogin);
        sessionStorage.removeItem(SIGNED_OUT_KEY);
        navigate(returnTo || '/', { replace: true });
      } catch (userErr) {
        localStorage.removeItem('token');
        throw userErr;
      }
    } catch (err) {
      setError(errorMessage(err, 'Login failed. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title={t('Log in')}
      subtitle={t('Students, teachers and recruiters all sign in here.')}
      footer={
        <>
          <p>
            {t('New here?')} <Link to="/signup" className="link">{t('Create a student account')}</Link>
          </p>
          <p>
            {t('Running exams for a school or company?')} <Link to="/signup/organization" className="link">{t('Register your organization')}</Link>
          </p>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        {notice && !error && <Alert tone="success">{notice}</Alert>}
        {signedOut && !notice && !error && (
          <Alert tone="info" title={signedOut.reason === 'idle' ? t('You were signed out after a while away') : t('Your session ended')}>
            {t("We do this to keep your account safe. Everything you saved is safe, and forms you were filling in keep your changes on this computer. Sign in to pick up where you left off.")}
          </Alert>
        )}
        <Field label={t('Email')} htmlFor="email">
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          <EmailSuggestion value={email} onUse={setEmail} />
        </Field>
        <Field label={t('Password')} htmlFor="password" hint={<Link to="/forgot-password" className="link">{t('Forgot password?')}</Link>}>
          <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <Checkbox checked={saveLogin} onChange={setSaveLogin}>{t('Keep me signed in on this device')}</Checkbox>

        {error && <Alert tone="danger">{error}</Alert>}

        <Button type="submit" size="lg" loading={loading} className="w-full">
          {t('Log in')}
        </Button>
      </form>
      {/* Before signing in there is no profile to hold a language, so it can be chosen here; each name is in its own language */}
      <div className="mt-6 flex justify-center gap-1" role="group" aria-label={t('Language')}>
        {LANGUAGES.map((l) => (
          <button
            key={l.code}
            type="button"
            lang={l.code}
            onClick={() => setLanguage(l.code, { chosen: true })}
            aria-pressed={language === l.code}
            className={language === l.code ? 'btn btn-sm btn-ghost font-semibold text-ink' : 'btn btn-sm btn-ghost'}
          >
            {l.label}
          </button>
        ))}
      </div>
    </AuthLayout>
  );
}

export default LoginPage;
