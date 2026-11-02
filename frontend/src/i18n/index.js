import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { setI18n } from '../utils';

/*
 * Translations without a library. English text is the key: t('Sign in') shows "Sign in" until a
 * locale file has an entry for it, so nothing is ever blank. Locale files map English to the
 * translation; plural entries hold one form per Intl.PluralRules category.
 *
 *   t('Hello, {{name}}', { name })
 *   tn(count, '{{count}} question', '{{count}} questions')
 *
 * "en-XA" is a pseudo-language for finding strings that skipped t(): everything translated
 * renders as [Ŝîĝñ îñ], so plain English on screen is a miss. "en-XB" is the same text laid out
 * right to left, for checking layouts before a real RTL language (Arabic, Urdu) ships.
 */

const CATALOGS = {
  en: { label: 'English', dir: 'ltr', messages: {} },
  // Loaded only for people who use it (about 32 kB compressed); English shows until it arrives.
  // Latin digits, so dates match the numbers in the text and in questions (৪ reads like 8).
  bn: { label: 'বাংলা', dir: 'ltr', locale: 'bn-u-nu-latn', messages: {}, load: () => import('./bn.json') },
  'en-XA': { label: 'Pseudo (test)', dir: 'ltr', messages: null, hidden: true },
  'en-XB': { label: 'Pseudo RTL (test)', dir: 'rtl', messages: null, hidden: true },
};

const STORAGE_KEY = 'language';
const CHOSEN_KEY = 'languageChosen'; // '1' once someone picks a language by hand on this device (the sign-in page)
const ACCENTS = { a: 'á', b: 'ƀ', c: 'ç', d: 'ð', e: 'é', f: 'ƒ', g: 'ĝ', h: 'ĥ', i: 'î', j: 'ĵ', k: 'ķ', l: 'ļ', m: 'ɱ', n: 'ñ', o: 'ö', p: 'þ', r: 'ŕ', s: 'š', t: 'ţ', u: 'û', w: 'ŵ', y: 'ý', z: 'ž', A: 'Å', C: 'Ç', E: 'É', I: 'Î', O: 'Ö', S: 'Ŝ', U: 'Û' };

const pseudo = (text) => `[${text.replace(/\{\{\w+\}\}|[A-Za-z]/g, (m) => (m.length > 1 ? m : ACCENTS[m] || m))}]`;
const interpolate = (text, vars) => (vars ? text.replace(/\{\{(\w+)\}\}/g, (m, k) => (vars[k] ?? m)) : text);

// Pseudo-languages format dates, numbers and plurals as English; a catalog can pick its own digits
const baseLocale = (language) => (language.startsWith('en-X') ? 'en' : CATALOGS[language]?.locale || language);

export function initialLanguage() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('lang');
    if (fromUrl && CATALOGS[fromUrl]) {
      localStorage.setItem(STORAGE_KEY, fromUrl); // ?lang=bn sticks for the rest of the visit
      return fromUrl;
    }
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && CATALOGS[saved]) return saved;
  } catch {
    // storage blocked: fall through to the browser language
  }
  const browser = (navigator.language || 'en').split('-')[0];
  return CATALOGS[browser] && !CATALOGS[browser].hidden ? browser : 'en';
}

// The language a signed-in person gets: their account's; else one picked by hand on this device, which
// shouldn't flip to the organization's the moment they sign in; else the organization's. null keeps the current one.
export function languageFor(user, membership) {
  let chosenHere = false;
  try { chosenHere = localStorage.getItem(CHOSEN_KEY) === '1'; } catch { /* storage blocked: no pick to keep */ }
  return user?.language || (chosenHere ? null : membership?.default_language) || null;
}

// A language saved on the account decides again, instead of this device's pick
export function forgetDeviceLanguage() {
  try { localStorage.removeItem(CHOSEN_KEY); } catch { /* nothing was stored */ }
}

// Fetch a language's messages once; resolves true when the catalog changed
export async function loadCatalog(language) {
  const catalog = CATALOGS[language];
  if (!catalog?.load || catalog.loaded) return false;
  const module = await catalog.load();
  catalog.messages = module.default || module;
  catalog.loaded = true;
  return true;
}

export function makeTranslator(language) {
  const catalog = CATALOGS[language] || CATALOGS.en;
  const plural = new Intl.PluralRules(baseLocale(language));
  const lookup = (key) => (catalog.messages ? catalog.messages[key] : undefined);

  const t = (key, vars) => {
    const entry = lookup(key);
    const text = typeof entry === 'string' ? entry : key;
    return interpolate(catalog.messages === null ? pseudo(text) : text, vars);
  };
  // Plurals: the English one/other forms are in the code; a translation lists its own categories
  const tn = (count, one, other, vars) => {
    const entry = lookup(other);
    const category = plural.select(count);
    let text = count === 1 || category === 'one' ? one : other;
    if (entry && typeof entry === 'object') text = entry[category] ?? entry.other ?? text;
    return interpolate(catalog.messages === null ? pseudo(text) : text, { count, ...vars });
  };
  return { t, tn };
}

// Marks English text kept in a table (labels, steps, messages) for scripts/extract-strings.js; the code that
// shows it still passes it through t(). It returns the text unchanged.
export const msg = (text) => text;

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [language, setLanguageState] = useState(initialLanguage);
  const [loaded, setLoaded] = useState(0); // bumps when a catalog arrives, so every t() picks it up

  useEffect(() => {
    let live = true;
    loadCatalog(language).then((changed) => live && changed && setLoaded((n) => n + 1)).catch(() => {
      // offline or blocked: English stays, and the next visit tries again
    });
    return () => { live = false; };
  }, [language]);

  useEffect(() => {
    const catalog = CATALOGS[language] || CATALOGS.en;
    document.documentElement.lang = language.startsWith('en-X') ? 'en' : language; // the language, not its digit choice
    document.documentElement.dir = catalog.dir;
  }, [language]);

  const setLanguage = useCallback((next, { chosen = false } = {}) => {
    if (!CATALOGS[next]) return;
    setLanguageState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
      if (chosen) localStorage.setItem(CHOSEN_KEY, '1');
    } catch {
      // the choice just won't survive a reload
    }
  }, []);

  const value = useMemo(() => {
    const { t, tn } = makeTranslator(language);
    const locale = baseLocale(language);
    setI18n({ t, locale }); // plain helpers (errorMessage, date formatting) follow the language too
    return { language, locale, setLanguage, t, tn };
  }, [language, setLanguage, loaded]); // eslint-disable-line react-hooks/exhaustive-deps -- `loaded` changes what the catalog holds

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

// Outside a provider (some tests, early errors) fall back to English
const FALLBACK = { language: 'en', locale: 'en', setLanguage: () => {}, ...makeTranslator('en') };

export function useI18n() {
  return useContext(I18nContext) || FALLBACK;
}

export const LANGUAGES = Object.entries(CATALOGS)
  .filter(([, c]) => !c.hidden)
  .map(([code, c]) => ({ code, label: c.label }));
