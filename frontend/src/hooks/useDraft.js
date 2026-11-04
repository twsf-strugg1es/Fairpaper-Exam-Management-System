import { useEffect, useRef, useState } from 'react';

/*
 * Keeps a long form's unsaved changes on this computer (localStorage), so being signed out, a closed tab or
 * a crash doesn't lose them. Nothing is written until the form differs from what the page loaded, so opening
 * a page never overwrites an older draft. The page offers `draft` back (restore or discard) and calls
 * clear() once the form is saved.
 *
 *   const saved = useDraft(`exam:${examId || 'new'}`, formState, { ready: loaded });
 */

const PREFIX = 'fp-draft:';
const read = (key) => {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null');
  } catch {
    return null;
  }
};

export default function useDraft(name, value, { ready = true } = {}) {
  // Scoped to the account and organization, so a shared computer never shows one person's draft to another
  const owner = `${(() => { try { return JSON.parse(localStorage.getItem('user') || '{}').id || ''; } catch { return ''; } })()}:${localStorage.getItem('organizationId') || ''}`;
  const key = `${PREFIX}${owner}:${name}`;
  const [draft, setDraft] = useState(() => read(key));
  const baseline = useRef(null);
  const json = JSON.stringify(value);

  useEffect(() => {
    if (!ready) return undefined;
    if (baseline.current === null) {
      baseline.current = json; // what the page loaded: not a change
      return undefined;
    }
    if (json === baseline.current) return undefined;
    const id = setTimeout(() => {
      try {
        localStorage.setItem(key, JSON.stringify({ at: new Date().toISOString(), value }));
      } catch {
        // storage full or blocked: the form still works, it just can't be recovered
      }
    }, 400);
    return () => clearTimeout(id);
  }, [key, ready, json]); // eslint-disable-line react-hooks/exhaustive-deps -- json stands for value

  const clear = () => {
    try { localStorage.removeItem(key); } catch { /* nothing to remove */ }
    setDraft(null);
  };
  return {
    draft: draft?.value ?? null,
    savedAt: draft?.at ?? null,
    keep: () => setDraft(null), // restored: hide the offer, keep saving
    clear,
  };
}
