import React, { forwardRef, useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../i18n';
import {
  LuX, LuLoaderCircle, LuCircleAlert, LuCircleCheck, LuTriangleAlert, LuInfo, LuWifiOff, LuServerCrash, LuLock,
  LuSearchX, LuRefreshCw, LuClock, LuCloudOff,
} from 'react-icons/lu';
import { errorKind, errorMessage, formatDateTime, suggestEmail } from '../utils';

const cx = (...classes) => classes.filter(Boolean).join(' ');
export { cx };

// --- Brand ---

// The mark is a filled answer bubble with a check, as on an exam answer sheet.
// Same geometry as public/favicon.svg and the PNG icons (32-unit grid).
export function LogoMark({ size = 32, className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className={cx('shrink-0', className)}>
      <rect width="32" height="32" rx="8" className="fill-brand" />
      {/* A row of answer bubbles, the third one filled in */}
      {[6.5, 12.83, 19.17, 25.5].map((x, i) => (i === 2
        ? <circle key={x} cx={x} cy="16" r="3.1" className="fill-on-brand" />
        : <circle key={x} cx={x} cy="16" r="2.45" fill="none" strokeWidth="1.7" className="stroke-on-brand" />))}
    </svg>
  );
}

export function Logo({ compact = false, size = 28, className }) {
  return (
    <span className={cx('inline-flex items-center gap-2.5', className)}>
      <LogoMark size={size} />
      {!compact && <span className="text-[17px] font-semibold tracking-[-0.015em] text-ink">Fairpaper</span>}
    </span>
  );
}

// --- Buttons ---

// Full class names, not built from parts: Tailwind only keeps classes it finds written out in the source
const BUTTON_VARIANTS = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  ghost: 'btn-ghost',
  danger: 'btn-danger',
  'danger-ghost': 'btn-danger-ghost',
};
const BUTTON_SIZES = { sm: 'btn-sm', lg: 'btn-lg' };

export const Button = forwardRef(function Button(
  { variant = 'primary', size, icon: Icon, iconRight: IconRight, loading = false, className, children, type = 'button', disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cx('btn', BUTTON_VARIANTS[variant], BUTTON_SIZES[size], !children && 'btn-icon', className)}
      {...props}
    >
      {loading ? <LuLoaderCircle className="h-4 w-4 animate-spin" /> : Icon && <Icon className="h-4 w-4 shrink-0" />}
      {children}
      {IconRight && !loading && <IconRight className="h-4 w-4 shrink-0" />}
    </button>
  );
});

// --- Form controls ---

export function Field({ label, hint, error, htmlFor, children, className, optional }) {
  const { t } = useI18n();
  return (
    <div className={className}>
      {label && (
        <label htmlFor={htmlFor} className="label">
          {label}
          {optional && <span className="ms-1.5 font-normal text-muted">{t('optional')}</span>}
        </label>
      )}
      {children}
      {error ? <p className="hint !text-danger">{error}</p> : hint && <p className="hint">{hint}</p>}
    </div>
  );
}

export const Input = forwardRef(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cx('input', className)} {...props} />;
});

export const Select = forwardRef(function Select({ className, children, ...props }, ref) {
  return (
    <select ref={ref} className={cx('input', className)} {...props}>
      {children}
    </select>
  );
});

export const Textarea = forwardRef(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cx('input', className)} {...props} />;
});

// An on/off setting with a label and an explanation
export function Switch({ checked, onChange, label, description, disabled }) {
  return (
    <label className={cx('flex cursor-pointer items-start justify-between gap-4', disabled && 'cursor-not-allowed opacity-60')}>
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-xs leading-relaxed text-muted">{description}</span>}
      </span>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="h-5 w-9 rounded-full bg-line transition-colors peer-checked:bg-brand peer-focus-visible:ring-2 peer-focus-visible:ring-brand/40 peer-disabled:opacity-50" />
        <span className="absolute start-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4 rtl:peer-checked:-translate-x-4" />
      </span>
    </label>
  );
}

// Without visible text (a table's row checkbox), pass aria-label so it still has a name
export function Checkbox({ checked, onChange, children, className, ...props }) {
  return (
    <label className={cx('flex cursor-pointer items-center gap-2.5 text-sm text-ink', className)}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 cursor-pointer rounded border-line accent-[rgb(var(--brand))]"
        {...props}
      />
      {children}
    </label>
  );
}

// --- Surfaces ---

export function Card({ className, children, ...props }) {
  return (
    <div className={cx('card', className)} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ title, description, action, className }) {
  return (
    <div className={cx('flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4', className)}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

const BADGE_TONES = {
  neutral: 'badge-neutral',
  brand: 'badge-brand',
  danger: 'badge-danger',
  warn: 'badge-warn',
  info: 'badge-info',
};

export function Badge({ tone = 'neutral', icon: Icon, className, children }) {
  return (
    <span className={cx('badge', BADGE_TONES[tone], className)}>
      {Icon && <Icon className="h-3 w-3" />}
      {children}
    </span>
  );
}

const ALERT_STYLES = {
  info: ['bg-info-soft text-info-ink', LuInfo],
  success: ['bg-brand-soft text-brand-ink', LuCircleCheck],
  warn: ['bg-warn-soft text-warn-ink', LuTriangleAlert],
  danger: ['bg-danger-soft text-danger-ink', LuCircleAlert],
};

export function Alert({ tone = 'info', title, children, onClose, className }) {
  const { t } = useI18n();
  const [style, Icon] = ALERT_STYLES[tone];
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={cx('flex gap-3 rounded-lg px-4 py-3 text-sm', style, className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cx('leading-relaxed', title && 'mt-0.5 opacity-90')}>{children}</div>}
      </div>
      {onClose && (
        <button type="button" onClick={onClose} className="-m-1 rounded p-1 opacity-70 hover:opacity-100" aria-label={t('Dismiss')}>
          <LuX className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

// Paige, the Fairpaper mascot. Decorative: the text beside her always carries the meaning.
// Poses are generated by design/paige/build.mjs into public/paige.
export function Paige({ pose = 'hello', className }) {
  return <img src={`${process.env.PUBLIC_URL}/paige/${pose}.svg`} alt="" aria-hidden="true" draggable="false" className={cx('select-none', className)} />;
}

export function EmptyState({ icon: Icon, paige, title, children, action, className }) {
  return (
    <div className={cx('flex flex-col items-center px-6 py-12 text-center', className)}>
      {paige ? (
        <Paige pose={paige} className="mb-2 h-28 w-28" />
      ) : Icon && (
        <span className="mb-4 grid h-11 w-11 place-items-center rounded-full bg-sunken text-muted">
          <Icon className="h-5 w-5" />
        </span>
      )}
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm leading-relaxed text-muted">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Spinner({ className }) {
  return <LuLoaderCircle className={cx('h-5 w-5 animate-spin text-muted', className)} />;
}

// A gray block where content is about to appear (pulses only when motion is allowed)
export function Skeleton({ className }) {
  return <span aria-hidden="true" className={cx('block rounded bg-sunken motion-safe:animate-pulse', className)} />;
}

function SkeletonRows({ rows = 6 }) {
  return (
    <div className="divide-y divide-line">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3.5">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-4 w-1/6" />
          <Skeleton className="ms-auto h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

// The whole signed-in frame while the app gets ready (the account loading, a screen's code arriving): a sidebar and
// a page of blocks, the same shape public/index.html shows before the script arrives
export function ShellSkeleton() {
  const { t } = useI18n();
  return (
    <div role="status" aria-busy="true" className="flex min-h-screen bg-paper">
      <span className="sr-only">{t('Loading…')}</span>
      <div className="hidden w-64 shrink-0 space-y-5 border-e border-line px-5 py-6 lg:block">
        <Skeleton className="h-7 w-36" />
        <Skeleton className="h-14" />
        {['w-3/4', 'w-3/5', 'w-2/3', 'w-1/2'].map((w) => <Skeleton key={w} className={cx('h-3.5', w)} />)}
      </div>
      <div className="mx-auto w-full max-w-6xl px-6 py-10 lg:px-12">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="mt-3.5 h-3.5 w-full max-w-md" />
        <div className="mt-8 space-y-3 border-t-2 border-line pt-8">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
      </div>
    </div>
  );
}

// Loading shows the shape of what's coming, not a spinner. If it takes long, it says so: usually a slow line.
// variant: list (title + table), detail (title + stats + table), cards (a grid of cards), sheet (one paper sheet),
// exam (question + answers + question map)
export function PageLoader({ label, variant = 'list' }) {
  const { t } = useI18n();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setSlow(true), 5000);
    return () => clearTimeout(id);
  }, []);
  return (
    <div role="status" aria-busy="true" aria-live="polite" className="mx-auto w-full max-w-6xl px-6 py-8">
      <span className="sr-only">{label || t('Loading…')}</span>
      {variant === 'exam' ? (
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="mx-auto w-full max-w-[42rem] space-y-6 pt-6">
            <div className="flex items-end gap-4 border-b border-line pb-3.5"><Skeleton className="h-9 w-14" /><Skeleton className="h-3 w-40" /></div>
            <div className="space-y-3"><Skeleton className="h-5 w-11/12" /><Skeleton className="h-5 w-2/3" /></div>
            <div className="space-y-2.5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12 rounded-lg" />)}</div>
          </div>
          <div className="grid h-fit grid-cols-5 gap-3 pt-6">{Array.from({ length: 15 }, (_, i) => <Skeleton key={i} className="h-7 w-7 rounded-full" />)}</div>
        </div>
      ) : variant === 'sheet' ? (
        <div className="sheet mx-auto max-w-2xl space-y-4 px-10 py-10">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-px w-full" />
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-4 w-full" />)}
          <Skeleton className="mt-6 h-11 w-full rounded-lg" />
        </div>
      ) : (
        <>
          <Skeleton className="h-7 w-56" />
          <Skeleton className="mt-3 h-4 w-80" />
          {variant === 'detail' && (
            <div className="mt-8 grid grid-cols-2 gap-6 rounded-xl border border-line bg-surface p-5 sm:grid-cols-4">
              {[0, 1, 2, 3].map((i) => <div key={i} className="space-y-2"><Skeleton className="h-3 w-20" /><Skeleton className="h-7 w-14" /></div>)}
            </div>
          )}
          {variant === 'cards' ? (
            <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="space-y-3 rounded-xl border border-line bg-surface p-5">
                  <Skeleton className="h-5 w-3/4" /><Skeleton className="h-3 w-1/2" /><Skeleton className="mt-4 h-9 w-28 rounded-lg" />
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-8 overflow-hidden rounded-xl border border-line bg-surface"><SkeletonRows /></div>
          )}
        </>
      )}
      {slow && (
        <p className="mt-6 flex items-center justify-center gap-2 text-sm text-muted">
          <Spinner className="h-4 w-4" />
          {t('Still loading. Your connection seems slow; this appears as soon as it arrives.')}
        </p>
      )}
    </div>
  );
}

// A failed load, said plainly: what happened, whose side it's on, and what to do now
const ERROR_ICONS = { offline: LuWifiOff, unreachable: LuCloudOff, server: LuServerCrash, forbidden: LuLock, notFound: LuSearchX, expired: LuClock, invalid: LuCircleAlert };
export function ErrorState({ error, onRetry, action, className }) {
  const { t } = useI18n();
  const kind = errorKind(error);
  const detail = typeof error?.response?.data?.detail === 'string' ? errorMessage(error) : null;
  const copy = {
    offline: [t("You're offline"), t("Nothing you've saved is lost. Reconnect, then try again.")],
    unreachable: [t("We couldn't reach Fairpaper"), t("Your connection may be slow or blocked, or our servers may be busy. Nothing you've saved is lost.")],
    server: [t('Something went wrong on our side'), t("It's not something you did, and your saved work is safe. Try again in a moment.")],
    forbidden: [t("You don't have access to this"), detail || t("Your role in this organization doesn't include it. An owner or admin can change that.")],
    notFound: [t("We couldn't find this"), detail || t('It may have been deleted, or the link may be out of date.')],
    expired: [t('Your session has ended'), t('Sign in again to carry on. Your saved work is safe.')],
    invalid: [t("That didn't work"), detail || t('Something went wrong. Please try again.')],
  }[kind];
  const Icon = ERROR_ICONS[kind];
  const retryable = ['offline', 'unreachable', 'server', 'invalid'].includes(kind);
  return (
    <div role="alert" className={cx('flex flex-col items-center px-6 py-14 text-center', className)}>
      <span className="mb-4 grid h-11 w-11 place-items-center rounded-full bg-danger-soft text-danger"><Icon className="h-5 w-5" /></span>
      <p className="font-medium text-ink">{copy[0]}</p>
      <p className="mt-1 max-w-md text-sm leading-relaxed text-muted">{copy[1]}</p>
      {(onRetry || action) && (
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {onRetry && retryable && <Button icon={LuRefreshCw} onClick={onRetry}>{t('Try again')}</Button>}
          {action}
        </div>
      )}
    </div>
  );
}

// A search with no results is never a dead end: say what was searched, offer a likely correction, a way back
export function NoResults({ query, suggestion, onSuggest, onClear, children, className }) {
  const { t } = useI18n();
  return (
    <div className={cx('flex flex-col items-center px-6 py-12 text-center', className)}>
      <span className="mb-4 grid h-11 w-11 place-items-center rounded-full bg-sunken text-muted"><LuSearchX className="h-5 w-5" /></span>
      <p className="font-medium text-ink">{query ? t('Nothing matches “{{q}}”', { q: query }) : t('Nothing matches these filters')}</p>
      <p className="mt-1 max-w-sm text-sm leading-relaxed text-muted">
        {suggestion ? (
          <>
            {t('Did you mean')}{' '}
            <button type="button" className="link font-medium" onClick={() => onSuggest?.(suggestion)}>{suggestion}</button>?
          </>
        ) : (children || t('Check the spelling, or try fewer or different words.'))}
      </p>
      {onClear && <Button variant="secondary" size="sm" className="mt-5" onClick={onClear}>{query ? t('Clear search') : t('Clear filters')}</Button>}
    </div>
  );
}

// "Did you mean …@gmail.com?" under an email field: a typo caught here is an account that can still be reached
export function EmailSuggestion({ value, onUse }) {
  const { t } = useI18n();
  const suggestion = suggestEmail(value);
  if (!suggestion) return null;
  return (
    <p className="hint" aria-live="polite">
      {t('Did you mean')}{' '}
      <button type="button" className="link font-medium" onClick={() => onUse(suggestion)}>{suggestion}</button>?
    </p>
  );
}

// An upload in flight: the real percentage, then "checking" while the server reads it
export function UploadProgress({ value, hint, className }) {
  const { t } = useI18n();
  const pct = Math.round((value || 0) * 100);
  return (
    <div className={cx('space-y-1.5', className)}>
      <ProgressBar value={value} label={t('Upload progress')} />
      <p className="text-xs text-muted">
        {pct < 100 ? t('Uploading: {{pct}}%', { pct }) : t('Uploaded. Checking it…')}
        {hint && pct < 100 && <span className="block">{hint}</span>}
      </p>
    </div>
  );
}

// A form's unsaved changes from an earlier visit (useDraft): restore them or start from what's saved
export function DraftNotice({ savedAt, onRestore, onDiscard, className }) {
  const { t } = useI18n();
  return (
    <Alert tone="info" className={className} title={t('You have unsaved changes from earlier')}>
      <p>{t('Kept on this computer when you left this form on {{when}}.', { when: formatDateTime(savedAt) })}</p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        <Button size="sm" onClick={onRestore}>{t('Restore my changes')}</Button>
        <Button size="sm" variant="ghost" onClick={onDiscard}>{t('Discard them')}</Button>
      </div>
    </Alert>
  );
}

// Real progress for uploads (value from 0 to 1), so a slow line doesn't look frozen
export function ProgressBar({ value, label, className }) {
  const pct = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label} className={cx('h-1.5 w-full overflow-hidden rounded-full bg-sunken', className)}>
      <div className="h-full w-full rounded-full bg-brand transition-transform duration-150 ltr:origin-left rtl:origin-right" style={{ transform: `scaleX(${pct / 100})` }} />
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b-2 border-ink pb-5">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
        <h1 className="text-[2rem] font-semibold leading-none tracking-[-0.025em]">{title}</h1>
        {description && <p className="mt-2.5 max-w-2xl text-sm leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone }) {
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <p className={cx('tabular mt-1 text-2xl font-semibold tracking-tight', tone === 'danger' && 'text-danger', tone === 'brand' && 'text-brand')}>
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Tabs({ tabs, value, onChange, className }) {
  return (
    <div role="tablist" className={cx('flex gap-1 border-b border-line', className)}>
      {tabs.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          type="button"
          aria-selected={value === tab.value}
          onClick={() => onChange(tab.value)}
          className={cx(
            '-mb-px inline-flex items-center gap-2 border-b-2 px-3 pb-2.5 pt-1 text-sm font-medium transition-colors',
            value === tab.value ? 'border-brand text-ink' : 'border-transparent text-muted hover:text-ink',
          )}
        >
          {tab.label}
          {tab.count !== undefined && <span className="tabular rounded-full bg-sunken px-1.5 text-xs text-muted">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}

// --- Dialogs ---

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({ open, onClose, title, description, children, footer, size = 'md' }) {
  const { t } = useI18n();
  const panelRef = useRef(null);
  // The latest onClose, read when needed: an effect keyed on it re-ran (and grabbed focus) on every parent render
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    const opener = document.activeElement; // focus goes back here when the dialog closes
    const panel = panelRef.current;
    if (panel && !panel.contains(document.activeElement)) panel.focus(); // an autofocused field keeps focus
    const onKey = (e) => {
      if (e.key === 'Escape') {
        closeRef.current?.();
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      // Tab stays inside the dialog
      const items = [...panel.querySelectorAll(FOCUSABLE)];
      if (!items.length) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (opener?.focus && document.contains(opener)) opener.focus();
    };
  }, [open]);

  if (!open) return null;
  const width = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }[size];

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div className="absolute inset-0 animate-fade-in bg-black/40" onClick={onClose} />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cx('relative flex max-h-[90vh] w-full animate-rise-in flex-col rounded-xl border border-line bg-surface shadow-pop focus:outline-none', width)}
      >
        <div className="flex items-start justify-between gap-4 px-5 pb-2 pt-5">
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            {description && <p className="mt-1 text-sm leading-relaxed text-muted">{description}</p>}
          </div>
          {onClose && (
            <button type="button" onClick={onClose} className="-me-1 rounded-md p-1 text-muted hover:bg-sunken hover:text-ink" aria-label={t('Close')}>
              <LuX className="h-4 w-4" />
            </button>
          )}
        </div>
        {children && <div className="overflow-y-auto px-5 py-3">{children}</div>}
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}

// Promise-based confirmation: `if (await confirm({ title, ... })) doIt();`
export function useConfirm() {
  const { t } = useI18n();
  const [state, setState] = useState(null);

  const confirm = useCallback(
    (options) => new Promise((resolve) => setState({ ...options, resolve })),
    [],
  );

  const close = (result) => {
    state?.resolve(result);
    setState(null);
  };

  const dialog = (
    <Modal
      open={!!state}
      onClose={() => close(false)}
      title={state?.title}
      description={state?.description}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={() => close(false)}>{t('Cancel')}</Button>
          <Button variant={state?.danger ? 'danger' : 'primary'} onClick={() => close(true)}>
            {state?.confirmLabel || t('Confirm')}
          </Button>
        </>
      }
    />
  );

  return [dialog, confirm];
}
