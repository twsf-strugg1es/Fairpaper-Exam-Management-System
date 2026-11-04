// Question types on the client: what each answer looks like and how to show it. The rules that count (checking a
// key, grading) live on the server in backend/app/question_types.py; the helpers here mirror them for display and
// for early feedback only.

// Written and image answers are graded by staff; every other type is graded automatically
export const MANUAL_TYPES = ['text', 'image_upload'];
export const isManual = (type) => MANUAL_TYPES.includes(type);

// Blanks are written in the question as ___ (three or more underscores); without any, one blank follows the question
const BLANK = /_{3,}/;
export const blankCount = (title) => Math.max(1, String(title || '').split(BLANK).length - 1);
export const splitBlanks = (title) => String(title || '').split(BLANK);

const ZEROS = [0x09e6, 0x0660, 0x06f0, 0x0966]; // Bengali, Arabic-Indic, Persian and Devanagari zero
const asciiDigits = (text) => text.replace(/[০-৯٠-٩۰-۹०-९]/g, (c) => {
  const zero = ZEROS.find((z) => c.charCodeAt(0) >= z && c.charCodeAt(0) <= z + 9);
  return String(c.charCodeAt(0) - zero);
});
const GROUPED = /^[-+]?[1-9]\d{0,2}(?:(?:,\d{3})+|(?:,\d{2})+,\d{3})$/;

// A typed number the way the server reads it ("9,81", "1,000", "১২.৫"), or null when it isn't one
export const parseNumber = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  let text = asciiDigits(String(value ?? '').normalize('NFKC'))
    .replace(/٫/g, '.').replace(/٬/g, ',').replace(/−/g, '-').replace(/\s/g, '');
  if (text.includes(',') && text.includes('.')) {
    text = text.lastIndexOf('.') > text.lastIndexOf(',') ? text.replace(/,/g, '') : text.replace(/\./g, '').replace(/,/g, '.');
  } else if (text.includes(',')) {
    text = GROUPED.test(text) ? text.replace(/,/g, '') : text.replace(/,/g, '.');
  }
  if (!/^[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?$/i.test(text)) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
};

// Whether a saved answer says anything: a matching answer with no pairs, or blanks all empty, is not an answer yet
export const isAnswered = (value) => {
  if (value === undefined || value === null || value === '') return false;
  if (Array.isArray(value)) return value.some(isAnswered);
  if (typeof value === 'object') return Object.values(value).some(isAnswered);
  return true;
};

const pairs = (map) => Object.entries(map || {}).map(([item, match]) => `${item}: ${match}`).join('; ');
const numbered = (items) => [].concat(items || []).map((item, i) => `${i + 1}. ${item}`).join(', ');

// A student's answer as one line of text, or null when there's nothing to show
export const answerText = (type, value, t) => {
  if (!isAnswered(value)) return null;
  switch (type) {
    case 'true_false': return value === 'true' ? t('True') : value === 'false' ? t('False') : String(value);
    case 'fill_blank': return [].concat(value).map((v) => (v ? String(v) : '—')).join(' · ');
    case 'matching': return pairs(value);
    case 'ordering': return numbered(value);
    case 'image_upload': return value?.name || t('Image uploaded');
    default: return Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? null : String(value);
  }
};

// An answer key as one line of text
export const keyText = (type, key, t) => {
  if (key === undefined || key === null) return null;
  switch (type) {
    case 'true_false': return key === 'true' ? t('True') : t('False');
    case 'fill_blank': return [].concat(key).map((accepted) => [].concat(accepted).join(' / ')).join(' · ');
    case 'numeric': return key.tolerance ? `${key.value} ± ${key.tolerance}` : String(key.value);
    case 'matching': return pairs(key);
    case 'ordering': return numbered(key);
    default: return Array.isArray(key) ? key.join(', ') : String(key);
  }
};
