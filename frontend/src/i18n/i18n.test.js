import { render } from '@testing-library/react';
import { I18nProvider, forgetDeviceLanguage, languageFor, loadCatalog, makeTranslator, useI18n } from './index';
import { formatNumber } from '../utils';
import bn from './bn.json';

test('English text is its own key, with interpolation', () => {
  const { t } = makeTranslator('en');
  expect(t('Sign in')).toBe('Sign in');
  expect(t('Hello, {{name}}', { name: 'Arif' })).toBe('Hello, Arif');
});

test('plurals use the English forms from the code', () => {
  const { tn } = makeTranslator('en');
  expect(tn(1, '{{count}} question', '{{count}} questions')).toBe('1 question');
  expect(tn(4, '{{count}} question', '{{count}} questions')).toBe('4 questions');
});

test('a language without an entry falls back to English instead of showing nothing', () => {
  const { t } = makeTranslator('bn');
  expect(t('Sign in')).toBe('Sign in');
});

test('the pseudo-language marks every translated string and keeps placeholders working', () => {
  const { t, tn } = makeTranslator('en-XA');
  expect(t('Sign in')).toBe('[Ŝîĝñ îñ]');
  expect(t('Hello, {{name}}', { name: 'Arif' })).toBe('[Héļļö, Arif]');
  expect(tn(2, '{{count}} question', '{{count}} questions')).toBe('[2 qûéšţîöñš]');
});

test('the right-to-left pseudo-language uses the same marked text', () => {
  const { t } = makeTranslator('en-XB');
  expect(t('Sign in')).toBe('[Ŝîĝñ îñ]');
});

test('Bengali loads on demand and fills in words, plurals and placeholders', async () => {
  await loadCatalog('bn');
  const { t, tn } = makeTranslator('bn');
  expect(t('Log in')).toBe('লগ ইন');
  expect(t('Hello, {{name}}', { name: 'Arif' })).toBe('হ্যালো, Arif');
  expect(tn(3, '{{count}} question', '{{count}} questions')).toBe('3টি প্রশ্ন');
  expect(tn(1, '{{count}} question', '{{count}} questions')).toBe('1টি প্রশ্ন');
  expect(t('A sentence nobody translated yet')).toBe('A sentence nobody translated yet'); // English, never blank
});

test('Bengali dates and numbers use the same Latin digits as the text', async () => {
  await loadCatalog('bn');
  localStorage.setItem('language', 'bn');
  function Probe() {
    const { locale } = useI18n();
    const time = new Date(Date.UTC(2026, 10, 2, 14, 37)).toLocaleTimeString(locale, { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    return <p>{time} {formatNumber(1234)}</p>;
  }
  const { container } = render(<I18nProvider><Probe /></I18nProvider>);
  expect(container.textContent).toBe('14:37 1,234');
  expect(document.documentElement.lang).toBe('bn');
  localStorage.removeItem('language');
});

test('a language picked on the sign-in page outlasts signing in, until the account sets one', () => {
  localStorage.clear();
  const org = { default_language: 'en' };
  expect(languageFor({ language: null }, org)).toBe('en'); // nothing picked: the organization's
  localStorage.setItem('languageChosen', '1'); // what the sign-in buttons record
  expect(languageFor({ language: null }, org)).toBe(null); // keep the pick instead of flipping to English
  expect(languageFor({ language: 'bn' }, { default_language: 'en' })).toBe('bn'); // the account still wins
  forgetDeviceLanguage(); // saved in Account settings
  expect(languageFor({ language: null }, org)).toBe('en');
  expect(languageFor(null, null)).toBe(null);
});

test('every Bengali entry keeps the placeholders of its English text', () => {
  const holes = (text) => (text.match(/\{\{\w+\}\}/g) || []).sort().join(',');
  for (const [english, entry] of Object.entries(bn)) {
    for (const text of typeof entry === 'string' ? [entry] : Object.values(entry)) {
      expect([english, holes(text)]).toEqual([english, holes(english)]);
    }
  }
});
