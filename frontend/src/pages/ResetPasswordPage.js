import React, { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import api from '../api';
import AuthLayout from '../components/AuthLayout';
import { Alert, Button, Field, Input } from '../components/ui';
import { errorMessage } from '../utils';
import { useI18n } from '../i18n';

// Set a new password from the emailed link (/reset-password/:token), or the first password
// from an invite sent by a bulk import (/invite/:token, invite)
function ResetPasswordPage({ invite = false }) {
  const { token } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) {
      setError(t('Password must be at least 8 characters long'));
      return;
    }
    if (password !== confirmPassword) {
      setError(t('Passwords do not match'));
      return;
    }
    setLoading(true);
    try {
      await api.post('/password-reset/confirm', { token, new_password: password });
      navigate('/login', { replace: true, state: { notice: invite ? t('Your account is ready. Sign in with your email and new password.') : t('Password changed. Sign in with your new password.') } });
    } catch (err) {
      setError(errorMessage(err));
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title={invite ? t('Welcome to Fairpaper') : t('Set a new password')}
      subtitle={invite ? t('Choose a password to finish setting up your account.') : t('Choose a password you haven’t used here before.')}
      footer={<p>{invite && `${t('Link expired?')} `}<Link to="/forgot-password" className="link">{t('Ask for a new link')}</Link></p>}
    >
      <form onSubmit={submit} className="space-y-5">
        <Field label={t('New password')} htmlFor="password" hint={t('At least 8 characters.')}>
          <Input id="password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus />
        </Field>
        <Field label={t('Confirm new password')} htmlFor="confirmPassword">
          <Input id="confirmPassword" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" size="lg" loading={loading} className="w-full">{invite ? t('Set password') : t('Change password')}</Button>
      </form>
    </AuthLayout>
  );
}

export default ResetPasswordPage;
