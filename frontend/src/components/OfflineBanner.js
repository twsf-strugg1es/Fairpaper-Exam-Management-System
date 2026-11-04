import React, { useEffect, useRef, useState } from 'react';
import { LuWifi, LuWifiOff } from 'react-icons/lu';
import { useI18n } from '../i18n';

// Whether the browser thinks it's online; updates as the connection comes and goes
export function useOnline() {
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine !== false);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  return online;
}

// Across the app (the exam page has its own): what's on screen stays, and says what still works.
// When the connection returns, a short "back online" note, then nothing.
export default function OfflineBanner() {
  const { t } = useI18n();
  const online = useOnline();
  const [back, setBack] = useState(false);
  const wasOffline = useRef(false);

  useEffect(() => {
    if (!online) {
      wasOffline.current = true;
      setBack(false);
      return undefined;
    }
    if (!wasOffline.current) return undefined;
    wasOffline.current = false;
    setBack(true);
    const id = setTimeout(() => setBack(false), 4000);
    return () => clearTimeout(id);
  }, [online]);

  if (online && !back) return null;
  return (
    <div
      role="status"
      className={online
        ? 'sticky top-0 z-50 flex items-center justify-center gap-2 border-b border-brand/25 bg-brand-soft px-4 py-2 text-center text-sm text-brand-ink print:hidden'
        : 'sticky top-0 z-50 flex items-center justify-center gap-2 border-b border-warn/25 bg-warn-soft px-4 py-2 text-center text-sm text-warn-ink print:hidden'}
    >
      {online ? <LuWifi className="h-4 w-4 shrink-0" aria-hidden="true" /> : <LuWifiOff className="h-4 w-4 shrink-0" aria-hidden="true" />}
      {online
        ? t("You're back online.")
        : t("You're offline. What's on screen stays here and you can keep reading; saving and loading new pages wait until you reconnect.")}
    </div>
  );
}
