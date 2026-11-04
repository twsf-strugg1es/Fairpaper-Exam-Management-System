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
      ssl: connectionString.includes('localhost') ? false : { rejectUnauthorized: true },
    });
  }
  return pool;
}

let tableEnsured = false;
async function ensureTable(client) {
  if (tableEnsured) return;
  await client.query(`
    CREATE TABLE IF NOT EXISTS waitlist_signups (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      email VARCHAR(255) NOT NULL UNIQUE,
      source VARCHAR(40),
      locale VARCHAR(20),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      notified_at TIMESTAMPTZ,
      unsubscribed_at TIMESTAMPTZ
    );
  `);
  tableEnsured = true;
}

const JOINED = "You're on the list. We'll email you once, when Fairpaper opens.";
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const BAD_EMAIL = "That email doesn't look right. Check it and try again.";

async function processWaitlistRequest(body) {
  const email = (body.email || '').trim().toLowerCase();
  const website = body.website || '';
  const source = (body.source || 'waitlist-page').slice(0, 40);
  const locale = (body.locale || '').slice(0, 20);

  // Honeypot check: bots fill hidden fields, humans do not
  if (website) {
    return { status: 200, data: { message: JOINED } };
  }

  if (!EMAIL_SHAPE.test(email)) {
    return { status: 422, data: { error: BAD_EMAIL } };
  }

  const p = getPool();
  const client = await p.connect();
  try {
    await ensureTable(client);
    await client.query(
      `
      INSERT INTO waitlist_signups (email, source, locale)
      VALUES ($1, $2, $3)
      ON CONFLICT (email)
      DO UPDATE SET unsubscribed_at = NULL
      WHERE waitlist_signups.unsubscribed_at IS NOT NULL;
      `,
      [email, source, locale]
    );
    return { status: 200, data: { message: JOINED } };
  } finally {
    client.release();
  }
}

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

// Netlify v2 standard export
export default async function (req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json', ...corsHeaders },
    });
  }

  try {
    const body = await req.json().catch(() => ({}));
    const { status, data } = await processWaitlistRequest(body);
    return new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json', ...corsHeaders },
    });
  } catch (err) {
    console.error('Waitlist error:', err);
    return new Response(
      JSON.stringify({
        error: process.env.DATABASE_URL
          ? 'Unable to save to waitlist. Please check your connection and try again.'
          : 'DATABASE_URL is not configured in Netlify environment variables.',
      }),
      { status: 500, headers: { 'Content-Type': 'application/json', ...corsHeaders } }
    );
  }
}

// Netlify v1 fallback handler
export async function handler(event) {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: corsHeaders, body: '' };
  }
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      headers: { 'Content-Type': 'application/json', ...corsHeaders },
      body: JSON.stringify({ error: 'Method not allowed' }),
    };
  }

  try {
    const body = event.body ? JSON.parse(event.body) : {};
    const { status, data } = await processWaitlistRequest(body);
    return {
      statusCode: status,
      headers: { 'Content-Type': 'application/json', ...corsHeaders },
      body: JSON.stringify(data),
    };
  } catch (err) {
    console.error('Waitlist error:', err);
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json', ...corsHeaders },
      body: JSON.stringify({
        error: process.env.DATABASE_URL
          ? 'Unable to save to waitlist. Please check your connection and try again.'
          : 'DATABASE_URL is not configured in Netlify environment variables.',
      }),
    };
  }
}
