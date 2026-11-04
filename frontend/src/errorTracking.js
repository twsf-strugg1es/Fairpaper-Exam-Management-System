// Error reports to Sentry (task 5.5). Off unless the build sets REACT_APP_SENTRY_DSN. Loaded once the page has
// loaded, as its own chunk, so it never slows the first screen. Reports carry the user's and organization's ids,
// never names, emails or answers.
export function startErrorTracking() {
  const dsn = process.env.REACT_APP_SENTRY_DSN;
  if (!dsn) return;
  import('@sentry/react')
    .then((Sentry) => Sentry.init({
      dsn,
      environment: process.env.REACT_APP_SENTRY_ENVIRONMENT || 'production',
      sendDefaultPii: false,
      beforeSend(event) {
        try {
          const user = JSON.parse(localStorage.getItem('user') || 'null');
          if (user?.id) event.user = { id: user.id };
          const organizationId = localStorage.getItem('organizationId');
          if (organizationId) event.tags = { ...event.tags, organization_id: organizationId };
        } catch {
          // the report goes without them
        }
        return event;
      },
    }))
    .catch(() => {}); // no reports is better than a broken page
}
