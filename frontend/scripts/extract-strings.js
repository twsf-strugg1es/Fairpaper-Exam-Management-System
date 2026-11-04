#!/usr/bin/env node
// Lists every string passed to t() / tn() so translators get one complete file.
// Usage: npm run i18n:extract   (writes src/i18n/strings.json; commit it with UI changes)
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
const OUT = path.join(SRC, 'i18n', 'strings.json');
const STR = String.raw`(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")`;
const T_CALL = new RegExp(String.raw`\bt\(\s*${STR}`, 'g');
const TN_CALL = new RegExp(String.raw`\btn\([^,]+,\s*${STR}\s*,\s*${STR}`, 'g');
// msg('…') marks text kept in a table and passed to t() later (see src/i18n)
const MSG_CALL = new RegExp(String.raw`\bmsg\(\s*${STR}`, 'g');
// English labels kept in lookup tables and rendered through t(label)
const TABLES = [/QUESTION_TYPE_LABELS = \{([\s\S]*?)\};/, /ROLE_LABELS = \{([\s\S]*?)\};/, /SUBMIT_REASONS = \{([\s\S]*?)\};/, /RISK_EXPLANATIONS = \{([\s\S]*?)\};/, /PASTE_ACTIONS = \{([\s\S]*?)\};/];

const unescape = (s) => s.replace(/\\(['"\\])/g, '$1');
const strings = new Map(); // text -> { plural?: true }

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.js$/.test(entry.name) && !/\.test\.js$/.test(entry.name)) scan(fs.readFileSync(full, 'utf8'));
  }
}

function scan(code) {
  for (const m of code.matchAll(TN_CALL)) {
    strings.set(unescape(m[1] ?? m[2]), { plural_of: unescape(m[3] ?? m[4]) });
    strings.set(unescape(m[3] ?? m[4]), { plural: true });
  }
  for (const m of [...code.matchAll(T_CALL), ...code.matchAll(MSG_CALL)]) {
    const text = unescape(m[1] ?? m[2]);
    if (!strings.has(text)) strings.set(text, {});
  }
  for (const table of TABLES) {
    const body = code.match(table)?.[1];
    if (!body) continue;
    for (const m of body.matchAll(new RegExp(String.raw`:\s*${STR}`, 'g'))) {
      const text = unescape(m[1] ?? m[2]);
      if (!strings.has(text)) strings.set(text, {});
    }
  }
}

walk(SRC);

// Server messages reach the screen through errorMessage()/t() too, so translators need them
const BACKEND = path.join(__dirname, '..', '..', 'backend', 'app');
// detail=/message= strings, and validation errors (shown through errorMessage too)
const PY_MESSAGE = /(?:(?:detail|message)\s*[=:]\s*|ValueError\()(?:f?"([^"{}]+)"|f?'([^'{}]+)')|^[A-Z_]+ = (?:"([A-Z][^"{}]*\.)"|'([A-Z][^'{}]*\.)')/gm;
function walkPy(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walkPy(full);
    else if (entry.name.endsWith('.py')) {
      for (const m of fs.readFileSync(full, 'utf8').matchAll(PY_MESSAGE)) {
        const text = m[1] ?? m[2] ?? m[3] ?? m[4];
        if (/^[A-Z]/.test(text) && !strings.has(text)) strings.set(text, { source: 'server' });
      }
    }
  }
}
walkPy(BACKEND);

const sorted = Object.fromEntries([...strings.entries()].sort(([a], [b]) => a.localeCompare(b)));
fs.writeFileSync(OUT, `${JSON.stringify(sorted, null, 2)}\n`);
console.log(`${strings.size} strings -> ${path.relative(process.cwd(), OUT)}`);

// How much of each translation covers the current strings (plural "one" forms live under their "other" form)
for (const file of fs.readdirSync(path.join(SRC, 'i18n')).filter((f) => /^[a-z]{2}(-[A-Z]{2})?\.json$/.test(f))) {
  const messages = JSON.parse(fs.readFileSync(path.join(SRC, 'i18n', file), 'utf8'));
  const needed = [...strings.entries()].filter(([, meta]) => !meta.plural_of).map(([text]) => text);
  const missing = needed.filter((text) => !(text in messages));
  console.log(`${file}: ${needed.length - missing.length} of ${needed.length} translated${missing.length ? `; missing e.g. "${missing[0]}"` : ''}`);
}
