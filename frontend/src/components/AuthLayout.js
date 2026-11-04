import React from 'react';
import { Link } from 'react-router-dom';
import { LuMoon, LuSun } from 'react-icons/lu';
import { useTheme } from '../context/ThemeContext';
import { msg, useI18n } from '../i18n';
import { Logo } from './ui';

// Sign-in and sign-up pages: one exam-paper sheet on the paper ground
export default function AuthLayout({ title, subtitle, children, footer, label = msg('Students & staff') }) {
  const { themeName, toggleTheme } = useTheme();
  const { t } = useI18n();

  return (
    <div className="grid min-h-screen grid-rows-[auto_1fr_auto] bg-paper px-5 py-6 sm:px-12 sm:py-8">
      <header className="flex items-center justify-between">
        <Link to="/login" aria-label={t('Fairpaper home')}><Logo /></Link>
        <button
          type="button"
          onClick={toggleTheme}
          className="btn btn-ghost btn-icon"
          aria-label={themeName === 'dark' ? t('Switch to light theme') : t('Switch to dark theme')}
        >
          {themeName === 'dark' ? <LuSun className="h-4 w-4" /> : <LuMoon className="h-4 w-4" />}
        </button>
      </header>

      <main className="sheet sheet-margin my-10 w-full max-w-[34rem] self-center justify-self-center px-6 pb-9 pt-10 sm:ps-14 sm:pe-12">
        <div className="flex items-baseline justify-between gap-4 border-b-2 border-ink pb-3.5">
          <h1 className="text-[1.9rem] font-semibold leading-none tracking-[-0.02em]">{title}</h1>
          {label && <span className="eyebrow text-end">{t(label)}</span>}
        </div>
        {subtitle && <p className="mt-4 text-sm leading-relaxed text-muted">{subtitle}</p>}
        <div className="mt-7">{children}</div>
        {footer && <div className="mt-8 space-y-2 border-t border-line pt-4 text-sm text-muted">{footer}</div>}
      </main>

      <footer className="flex justify-between font-mono text-xs text-faint">
        <span>Fairpaper</span>
        <span>{t('Fair exams in any browser')}</span>
      </footer>
    </div>
  );
}
