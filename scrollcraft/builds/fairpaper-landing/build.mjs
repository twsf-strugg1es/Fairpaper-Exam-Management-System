// Netlify build: copy only the public files into dist/, point the waitlist at the hosted API (or
// use the built-in Netlify Function if FAIRPAPER_API is omitted) and the links at the site's address.
// Drafts (explorations, older versions, the brief) and the unfinished legal pages stay out.
//   FAIRPAPER_API=https://fairpaper-api.duckdns.org node build.mjs     (Netlify sets URL itself)
import fs from 'fs';
import path from 'path';

const api = (process.env.FAIRPAPER_API || '').replace(/\/$/, '');
if (api && !/^https?:\/\//.test(api) && api !== '/api') {
  console.error('Set FAIRPAPER_API to an https:// address, /api, or leave it empty to use Netlify Functions.');
  process.exit(1);
}
const site = (process.env.SITE_URL || process.env.URL || 'https://fairpaper.app').replace(/\/$/, '');
const FILES = ['index.html', 'waitlist.html', 'waitlist.js', 'favicon.svg', 'og-image.png', 'paper.webp', 'robots.txt', 'sitemap.xml', 'llms.txt', 'fonts', 'paige'];

fs.rmSync('dist', { recursive: true, force: true });
for (const name of FILES) fs.cpSync(name, path.join('dist', name), { recursive: true });
for (const name of ['index.html', 'waitlist.html', 'robots.txt', 'sitemap.xml', 'llms.txt']) {
  const file = path.join('dist', name);
  let text = fs.readFileSync(file, 'utf8').replaceAll('https://fairpaper.app', site);
  text = text.replace(/<meta name="fairpaper-api" content="[^"]*">/, `<meta name="fairpaper-api" content="${api}">`);
  fs.writeFileSync(file, text);
}
const target = api || '/api/waitlist (Netlify Functions)';
console.log(`dist/ ready: waitlist -> ${target}, site ${site}`);
