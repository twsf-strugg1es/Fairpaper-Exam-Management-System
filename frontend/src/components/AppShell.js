import React, { useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { LuChevronsUpDown, LuMoon, LuSun, LuLogOut, LuMenu, LuX } from 'react-icons/lu';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { msg, useI18n } from '../i18n';
import { Logo, cx } from './ui';
import { ROLE_LABELS } from '../utils';
import VerifyEmailBanner from './VerifyEmailBanner';

const STAFF_NAV = [
  { to: '/admin-exams', label: msg('Exams') },
  { to: '/admin-questions', label: msg('Question bank') },
  { to: '/admin-students', label: msg('Students') },
];
const MANAGER_NAV = [{ to: '/admin-organization', label: msg('Organization') }];
const ACCOUNT_NAV = [{ to: '/profile', label: msg('Account') }];
const STUDENT_NAV = [
  { to: '/student-account', label: msg('Exams') },
  { to: '/student-exams', label: msg('Results') },
];

// Menu items carry an answer-bubble dot: filled for the current page
function NavItem({ to, label }) {
  const { t } = useI18n();
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cx(
          'group flex items-center gap-3 rounded px-2.5 py-2 text-sm transition-colors',
          isActive ? 'font-medium text-ink' : 'text-muted hover:bg-surface hover:text-ink',
        )
      }
    >
      {({ isActive }) => (
        <>
          <span className={cx('status-dot', isActive ? 'bg-brand text-brand' : 'text-faint group-hover:text-muted')} />
          {t(label)}
        </>
      )}
    </NavLink>
  );
}

function Sidebar({ onNavigate }) {
  const { user, currentMembership, isStaff, isManager, logout } = useAuth();
  const { themeName, toggleTheme } = useTheme();
  const { t } = useI18n();
  const navigate = useNavigate();
  const items = [...(isStaff ? [...STAFF_NAV, ...(isManager ? MANAGER_NAV : [])] : STUDENT_NAV), ...ACCOUNT_NAV];
  const displayName = user?.full_name || user?.email;

  return (
    <div className="flex h-full flex-col gap-6 px-3 py-6">
      <div className="px-2.5">
        <Logo />
      </div>

      {/* Current organization; opens the organization picker */}
      <button
        type="button"
        onClick={() => { onNavigate?.(); navigate('/organizations'); }}
        className="group flex items-center gap-3 rounded border border-line bg-surface px-3 py-2.5 text-start transition-colors hover:border-line-strong"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-ink">{currentMembership?.organization_name}</span>
          <span className="eyebrow mt-1 block">{t(ROLE_LABELS[currentMembership?.role] || '')} · {t('switch')}</span>
        </span>
        <LuChevronsUpDown className="h-4 w-4 shrink-0 text-muted group-hover:text-ink" />
      </button>

      <nav className="flex flex-1 flex-col gap-1" onClick={onNavigate}>
        {items.map((item) => <NavItem key={item.to} {...item} />)}
      </nav>

      <div className="border-t border-line pt-4">
        <div className="flex items-center gap-3 px-2">
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-ink">{displayName}</span>
            {user?.full_name && <span className="block truncate font-mono text-xs text-faint">{user.email}</span>}
          </span>
        </div>
        <div className="mt-3 flex gap-1">
          <button
            type="button"
            onClick={toggleTheme}
            className="btn btn-ghost btn-sm flex-1"
            aria-label={themeName === 'dark' ? t('Switch to light theme') : t('Switch to dark theme')}
          >
            {themeName === 'dark' ? <LuSun className="h-4 w-4" /> : <LuMoon className="h-4 w-4" />}
            {themeName === 'dark' ? t('Light') : t('Dark')}
          </button>
          <button
            type="button"
            onClick={() => { logout(); navigate('/login'); }}
            className="btn btn-ghost btn-sm flex-1"
          >
            <LuLogOut className="h-4 w-4" />
            {t('Log out')}
          </button>
        </div>
      </div>
    </div>
  );
}

// Signed-in layout: sidebar on wide screens, a top bar with a slide-in menu on phones
export default function AppShell({ children, width = 'default' }) {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className="min-h-screen bg-paper">
      <aside className="fixed inset-y-0 start-0 hidden w-64 border-e border-line bg-paper lg:block">
        <Sidebar />
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-paper px-4 py-3 lg:hidden">
        <Logo />
        <button type="button" className="btn btn-ghost btn-icon" onClick={() => setMenuOpen(true)} aria-label={t('Open menu')}>
          <LuMenu className="h-5 w-5" />
        </button>
      </header>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 animate-fade-in bg-black/40" onClick={() => setMenuOpen(false)} />
          <div className="absolute inset-y-0 start-0 w-72 max-w-[85vw] animate-rise-in border-e border-line bg-paper">
            <button
              type="button"
              className="btn btn-ghost btn-icon absolute end-3 top-4"
              onClick={() => setMenuOpen(false)}
              aria-label={t('Close menu')}
            >
              <LuX className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={() => setMenuOpen(false)} />
          </div>
        </div>
      )}

      <main className="lg:ps-64">
        <div className={cx('mx-auto px-4 py-8 sm:px-8 lg:px-12 lg:py-10', width === 'narrow' ? 'max-w-3xl' : 'max-w-6xl')}>
          <VerifyEmailBanner />
          {children}
        </div>
      </main>
    </div>
  );
}
