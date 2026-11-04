import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import AuthLayout from '../components/AuthLayout';
import { Alert, Button, Field, Input, EmailSuggestion } from '../components/ui';
import { errorMessage } from '../utils';
import { useI18n } from '../i18n';

// Ask for a reset link. The answer is the same whether or not the account exists.
function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState('');
  const [sentTo, setSentTo] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.post('/password-reset/request', { email: email.trim() });
      setSentTo(email.trim());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title={t('Reset password')}
      subtitle={sentTo ? null : t("Enter the email you sign in with. We'll send a link to set a new password.")}
      footer={<p><Link to="/login" className="link">{t('Back to log in')}</Link></p>}
    >
      {sentTo ? (
        <div className="space-y-4 text-sm leading-relaxed">
          <Alert tone="success">{t("If an account exists for that email, we've sent a link to reset the password.")}</Alert>
          <p className="text-muted">
            {t('Check {{email}}, including the spam folder. The link works once, for 30 minutes.', { email: sentTo })}
          </p>
          <Button variant="secondary" onClick={() => setSentTo(null)}>{t('Use a different email')}</Button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-5">
          <Field label={t('Email')} htmlFor="email">
            <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
            <EmailSuggestion value={email} onUse={setEmail} />
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button type="submit" size="lg" loading={loading} className="w-full">{t('Send reset link')}</Button>
        </form>
      )}
    </AuthLayout>
  );
}

export default ForgotPasswordPage;
