import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../api';
import AuthLayout from '../components/AuthLayout';
import { Alert, Button, Field, Input, Paige, EmailSuggestion } from '../components/ui';
import { errorMessage } from '../utils';
import { useI18n } from '../i18n';

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

// Launch waitlist (PRD F27). The answer is the same whether or not the email was already listed.
function WaitlistPage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [website, setWebsite] = useState(''); // honeypot: people never see it
  const [joined, setJoined] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!EMAIL_SHAPE.test(email.trim())) {
      setError(t("That email doesn't look right. Check it and try again."));
      return;
    }
    setLoading(true);
    try {
      await api.post('/waitlist', { email: email.trim(), source: params.get('from') || 'waitlist-page', locale: navigator.language, website });
      setJoined(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title={joined ? t("You're on the list") : t('Hear when Fairpaper opens')}
      label="Launching soon"
      subtitle={joined ? null : t("Fair, timed exams in any browser. Leave your email and we'll send one message at launch.")}
      footer={<p>{t('One email when we launch, nothing else. Every email has an unsubscribe link.')}</p>}
    >
      <Paige pose={joined ? 'submitted' : 'join'} className="mx-auto -mt-3 mb-5 h-28 w-28" />
      {joined ? (
        <div className="space-y-4 text-sm leading-relaxed">
          <Alert tone="success">{t("We'll email {{email}} once, when Fairpaper opens.", { email: email.trim() })}</Alert>
          <p className="text-muted">{t('Already running exams? You can start now.')} <Link to="/signup/organization" className="link">{t('Create an organization')}</Link></p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-5" noValidate>
          <Field label={t('Your email')} htmlFor="email">
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder={t('Your email here')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'waitlist-error' : undefined}
              required
              autoFocus
            />
            <EmailSuggestion value={email} onUse={setEmail} />
          </Field>
          <div className="sr-only" aria-hidden="true">
            <label htmlFor="website">{t('Website')}</label>
            <input id="website" name="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
          </div>
          {error && <div id="waitlist-error"><Alert tone="danger">{error}</Alert></div>}
          <Button type="submit" size="lg" loading={loading} className="w-full">{t('Join the waitlist')}</Button>
        </form>
      )}
    </AuthLayout>
  );
}

export default WaitlistPage;
