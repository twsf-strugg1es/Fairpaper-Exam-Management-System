import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { LuCircleCheck, LuX } from 'react-icons/lu';
import { useI18n } from '../i18n';

/*
 * Success confirmations: what just happened, the details worth repeating, and where to go next.
 *   const toast = useToast();
 *   toast({ title: t('Exam published'), body: t('Opens …'), action: { label: t('View exam'), to: '/admin-exams/…' } });
 * Shown bottom-end, read out politely by screen readers, gone after a few seconds (or on close).
 */

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const { t } = useI18n();
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const dismiss = useCallback((id) => {
    clearTimeout(timers.current[id]);
    delete timers.current[id];
    setToasts((list) => list.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback((toast) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((list) => [...list.slice(-2), { id, ...toast }]);
    timers.current[id] = setTimeout(() => dismiss(id), toast.duration || 7000);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-5 end-5 z-[60] flex w-[min(380px,calc(100vw-2.5rem))] flex-col gap-2 print:hidden">
        {toasts.map((toast) => (
          <div key={toast.id} role="status" className="pointer-events-auto motion-safe:animate-rise-in flex gap-3 rounded-xl border border-line bg-surface p-4 shadow-lg">
            <LuCircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-medium text-ink">{toast.title}</p>
              {toast.body && <p className="mt-0.5 leading-relaxed text-muted">{toast.body}</p>}
              {toast.action && (
                <Link to={toast.action.to} onClick={() => dismiss(toast.id)} className="link mt-2 inline-block font-medium">{toast.action.label}</Link>
              )}
            </div>
            <button type="button" onClick={() => dismiss(toast.id)} className="-m-1 h-7 w-7 shrink-0 rounded p-1 text-muted hover:text-ink" aria-label={t('Dismiss')}>
              <LuX className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
