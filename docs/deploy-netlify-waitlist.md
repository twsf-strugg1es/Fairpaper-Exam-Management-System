# Deploying the Waitlist Landing Page on Netlify

This guide explains how to deploy the pre-launch waitlist landing page on Netlify using an open-source PostgreSQL database and Netlify Functions. No server or VPS is required for this stage.

---

## Architecture

* **Frontend**: Static landing page built from `scrollcraft/builds/fairpaper-landing/` with interactive proctoring demo.
* **Serverless API**: Netlify Functions (`/api/waitlist` and `/api/waitlist/export`).
* **Database**: Open-source PostgreSQL (compatible with Fairpaper's `waitlist_signups` schema).

---

## 1. Create a Free Open-Source PostgreSQL Database

You can use any PostgreSQL host (e.g. self-hosted via Docker, Aiven, Neon, Supabase). If you don't have one set up yet, [Neon](https://neon.tech) offers an instant, free serverless PostgreSQL database:

1. Sign up at [neon.tech](https://neon.tech) (free tier, no credit card required).
2. Create a project named `fairpaper-waitlist`.
3. Copy the **Connection Details** string (`postgres://...`). Ensure it includes `sslmode=require`.

---

## 2. Deploy to Netlify

1. Go to [Netlify](https://app.netlify.com/) and click **Add new site** → **Import an existing project**.
2. Select **GitHub** and authorize access to your repository: `twsf-strugg1es/Online-Exam-Management-System`.
3. Configure the build settings:
   * **Base directory**: `scrollcraft/builds/fairpaper-landing`
   * **Build command**: `node build.mjs`
   * **Publish directory**: `dist`
   * **Functions directory**: `netlify/functions` (configured automatically via `netlify.toml`)
4. In **Site configuration** → **Environment variables**, add:
   * `DATABASE_URL`: Your PostgreSQL connection string (from Step 1).
   * `WAITLIST_SECRET_KEY`: A private password/token of your choice (used to export emails securely).
   * *(Optional)* `SITE_URL`: Your Netlify URL (e.g. `https://your-site.netlify.app`), or left unset to default to Netlify's automatic URL.
5. Click **Deploy Site**.

Netlify will automatically build the site and deploy the serverless functions. When a visitor submits their email on the landing page, the function creates the `waitlist_signups` table automatically if it does not already exist.

---

## 3. How to View and Download Your Waitlist Emails

### Method A: One-Click Browser Download (CSV)
Visit this URL in your web browser:
```
https://<your-netlify-site>.netlify.app/api/waitlist/export?key=YOUR_WAITLIST_SECRET_KEY
```
This triggers an immediate download of `waitlist-YYYY-MM-DD.csv` containing:
* `email`: Subscriber email address
* `source`: Call-to-action source (`landing-hero`, `landing-close`, `waitlist-page`, etc.)
* `locale`: Browser language/locale
* `created_at`: Signup timestamp in UTC
* `notified_at`: Null (unnotified)
* `unsubscribed_at`: Null

### Method B: View as JSON
Append `&format=json` to the URL:
```
https://<your-netlify-site>.netlify.app/api/waitlist/export?key=YOUR_WAITLIST_SECRET_KEY&format=json
```
Returns:
```json
{
  "total": 42,
  "pending": 42,
  "signups": [...]
}
```

### Method C: Direct SQL Query
You can also connect to your PostgreSQL database using any open-source tool (e.g. `psql`, DBeaver, TablePlus):
```sql
SELECT email, source, locale, created_at FROM waitlist_signups ORDER BY created_at DESC;
```

---

## 4. Connecting a Custom Domain (Later)

When you purchase your domain:
1. Go to Netlify → **Site configuration** → **Domain management** → **Add a custom domain**.
2. Update your domain registrar's DNS records according to Netlify's instructions.
3. Update the `SITE_URL` environment variable in Netlify to `https://yourdomain.com`.
