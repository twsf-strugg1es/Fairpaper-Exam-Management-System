import pg from 'pg';

const { Pool } = pg;

let pool;
function getPool() {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error('DATABASE_URL environment variable is not configured');
    }
    pool = new Pool({
      connectionString,
      ssl: connectionString.includes('localhost') ? false : { rejectUnauthorized: false },
    });
  }
  return pool;
}

function checkAuth(authKey) {
  const secretKey = process.env.WAITLIST_SECRET_KEY || process.env.ADMIN_KEY;
  if (!secretKey) {
    return { ok: false, error: 'WAITLIST_SECRET_KEY is not set in Netlify environment variables.' };
  }
  if (!authKey || authKey !== secretKey) {
    return { ok: false, error: 'Unauthorized. Provide a valid ?key= parameter matching WAITLIST_SECRET_KEY.' };
  }
  return { ok: true };
}

function toCsv(rows) {
  const fields = ['email', 'source', 'locale', 'created_at', 'notified_at', 'unsubscribed_at'];
  const escapeCell = (v) => {
    if (v === null || v === undefined) return '';
    const str = v instanceof Date ? v.toISOString() : String(v);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replaceAll('"', '""')}"`;
    }
    return str;
  };

  const lines = [fields.join(',')];
  for (const row of rows) {
    lines.push(fields.map((f) => escapeCell(row[f])).join(','));
  }
  return lines.join('\r\n');
}

async function handleExport(authKey, format) {
  const auth = checkAuth(authKey);
  if (!auth.ok) {
    return {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: auth.error }),
    };
  }

  const p = getPool();
  const client = await p.connect();
  try {
    const res = await client.query(`
      SELECT email, source, locale, created_at, notified_at, unsubscribed_at
      FROM waitlist_signups
      ORDER BY created_at ASC
    `).catch((err) => {
      // Table doesn't exist yet -> return empty rows
      if (err.code === '42P01') return { rows: [] };
      throw err;
    });

    const rows = res.rows || [];
    if (format === 'json') {
      const pending = rows.filter((r) => !r.notified_at && !r.unsubscribed_at).length;
      return {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ total: rows.length, pending, signups: rows }),
      };
    }

    const csvData = toCsv(rows);
    const dateStr = new Date().toISOString().slice(0, 10);
    return {
      status: 200,
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': `attachment; filename="waitlist-${dateStr}.csv"`,
      },
      body: csvData,
    };
  } finally {
    client.release();
  }
}

// Netlify v2 standard export
export default async function (req) {
  const url = new URL(req.url);
  const key = url.searchParams.get('key') || req.headers.get('x-admin-key');
  const format = url.searchParams.get('format') || 'csv';

  try {
    const result = await handleExport(key, format);
    return new Response(result.body, {
      status: result.status,
      headers: result.headers,
    });
  } catch (err) {
    console.error('Export error:', err);
    return new Response(
      JSON.stringify({ error: 'Failed to export waitlist: ' + err.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

// Netlify v1 fallback handler
export async function handler(event) {
  const params = event.queryStringParameters || {};
  const key = params.key || (event.headers && (event.headers['x-admin-key'] || event.headers['X-Admin-Key']));
  const format = params.format || 'csv';

  try {
    const result = await handleExport(key, format);
    return {
      statusCode: result.status,
      headers: result.headers,
      body: result.body,
    };
  } catch (err) {
    console.error('Export error:', err);
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Failed to export waitlist: ' + err.message }),
    };
  }
}
