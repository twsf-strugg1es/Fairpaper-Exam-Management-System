/* Sends a waitlist signup to the Fairpaper API (POST /waitlist) or Netlify Functions (/api/waitlist).
   The API's address comes from <meta name="fairpaper-api">; if empty, it defaults to /api/waitlist. */
(() => {
  const rawApi = (document.querySelector('meta[name="fairpaper-api"]')?.content || '').replace(/\/$/, '');
  const endpoint = rawApi ? (rawApi.endsWith('/waitlist') ? rawApi : `${rawApi}/waitlist`) : '/api/waitlist';
  const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  const BAD_EMAIL = 'That email doesn\'t look right. Check it and try again.';

  // form: the <form>; email/website: its inputs; msg: the live message; source: which call to action
  window.wireWaitlist = ({ form, email, website, msg, source }) => {
    const button = form.querySelector('button[type="submit"]');
    const say = (tone, text) => { msg.className = `msg ${tone}`; msg.textContent = text; };
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const value = email.value.trim();
      if (!EMAIL_SHAPE.test(value)) { say('err', BAD_EMAIL); email.focus(); return; }
      button.disabled = true;
      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: value, website: website.value, source, locale: navigator.language }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) say('ok', data.message);
        else say('err', res.status === 422 ? BAD_EMAIL : typeof data.detail === 'string' ? data.detail : (typeof data.error === 'string' ? data.error : 'Something went wrong. Try again in a minute.'));
      } catch {
        say('err', 'We couldn\'t reach Fairpaper. Check your connection and try again.');
      } finally {
        button.disabled = false;
      }
    });
  };
})();
