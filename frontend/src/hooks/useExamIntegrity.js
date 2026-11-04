import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api';

/*
 * Watches an exam attempt and reports what it notices to the server, which counts violations and
 * submits the attempt when the exam's limit is reached. A browser can't stop a student from
 * switching apps; it can notice, hide the questions, and keep a record.
 *
 * Violations: leaving the exam (another tab, window or app) and exiting fullscreen.
 * Flags: copy/paste attempts (keys, menu, drag-and-drop, middle-click), right-clicks, blocked shortcuts,
 * a second screen. With copy/paste blocked, the clipboard is also emptied at the start and on every return,
 * and question text can't be selected (so it can't be copied, dragged out or sent to a "search" or "ask AI" menu).
 *
 * Leaving hides the questions, and they stay hidden after the student comes back until they click into the
 * exam (`returnToExam`): a deliberate return, and the moment a browser lets us empty the clipboard and
 * re-enter fullscreen.
 */

const FLAG_FLUSH_DELAY = 1000; // flags are batched; violations are sent at once
const FULLSCREEN_GRACE = 1500; // leaving the window often exits fullscreen too: count that as one violation

// Keys blocked during an exam whatever the settings (printing, saving, view-source, developer tools)
const isAlwaysBlocked = (e) => {
  const mod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();
  return e.key === 'F12'
    || (mod && ['p', 's', 'u'].includes(key))
    || (mod && e.shiftKey && ['i', 'j', 'c'].includes(key));
};
const isCopyShortcut = (e) => ((e.ctrlKey || e.metaKey) && ['c', 'v', 'x'].includes(e.key.toLowerCase()))
  || (e.key === 'Insert' && (e.shiftKey || e.ctrlKey)); // Shift+Insert pastes, Ctrl+Insert copies
const isSelectAll = (e) => (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a';

// A student may select (and type) inside their own answer box; everything else on the exam page is off limits
const inAnswerBox = (target) => {
  const el = target?.nodeType === 1 ? target : target?.parentElement;
  return Boolean(el?.closest?.('input, textarea, [contenteditable="true"]'));
};

// Every way text can arrive in an answer box without being typed
const PASTE_INPUT_TYPES = new Set(['insertFromPaste', 'insertFromPasteAsQuotation', 'insertFromDrop', 'insertFromYank']);

// Empty the clipboard so text copied before the exam (or outside it) can't be pasted in.
// Best effort: browsers only allow this on a focused page, some only right after a click.
export function clearClipboard() {
  try {
    return navigator.clipboard?.writeText('').catch(() => {}) ?? Promise.resolve();
  } catch {
    return Promise.resolve();
  }
}

const describeKey = (e) => [e.ctrlKey && 'Ctrl', e.metaKey && 'Cmd', e.shiftKey && 'Shift', e.key.length === 1 ? e.key.toUpperCase() : e.key]
  .filter(Boolean)
  .join('+');

export const fullscreenSupported = () => Boolean(document.fullscreenEnabled && document.documentElement.requestFullscreen);
const inFullscreen = () => Boolean(document.fullscreenElement);

export function enterFullscreen() {
  if (!fullscreenSupported() || inFullscreen()) return Promise.resolve();
  return document.documentElement.requestFullscreen({ navigationUI: 'hide' }).catch(() => {});
}

export function exitFullscreen() {
  if (inFullscreen()) document.exitFullscreen().catch(() => {});
}

export default function useExamIntegrity({ attemptId, settings, active, initialViolations = 0, onSubmitted }) {
  const [violations, setViolations] = useState(initialViolations);
  const [isAway, setIsAway] = useState(false);
  const [needsReturn, setNeedsReturn] = useState(false); // back from leaving, but hasn't clicked into the exam yet
  const [fullscreenLost, setFullscreenLost] = useState(false);
  const [lastViolation, setLastViolation] = useState(null); // { type, at } for the warning banner

  const queue = useRef([]);
  const flushTimer = useRef(null);
  const awaySince = useRef(null);
  const ignoreBlurUntilFocus = useRef(false);
  const onSubmittedRef = useRef(onSubmitted);
  onSubmittedRef.current = onSubmitted;

  const requireFullscreen = Boolean(settings?.require_fullscreen) && fullscreenSupported();

  const flush = useCallback(() => {
    clearTimeout(flushTimer.current);
    if (!attemptId || queue.current.length === 0) return;
    const events = queue.current.splice(0, 50);
    const headers = { 'Content-Type': 'application/json' };
    const token = localStorage.getItem('token');
    const org = localStorage.getItem('organizationId');
    if (token) headers.Authorization = `Bearer ${token}`;
    if (org) headers['X-Organization-Id'] = org;

    // keepalive lets the last events through even if the tab is being closed
    fetch(`${api.defaults.baseURL}/student/attempts/${attemptId}/events`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ events }),
      keepalive: true,
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data) return;
        setViolations(data.violations);
        if (data.submitted) onSubmittedRef.current?.(data.submit_reason);
      })
      .catch(() => {
        queue.current.unshift(...events); // offline: try again with the next event
      });
    if (queue.current.length) flushTimer.current = setTimeout(flush, FLAG_FLUSH_DELAY);
  }, [attemptId]);

  const record = useCallback((type, details, { violation = false } = {}) => {
    queue.current.push({ type, occurred_at: new Date().toISOString(), details: details || undefined });
    if (violation) {
      setViolations((v) => v + 1); // optimistic; the server's count replaces it
      setLastViolation({ type, at: Date.now() });
      flush();
    } else {
      clearTimeout(flushTimer.current);
      flushTimer.current = setTimeout(flush, FLAG_FLUSH_DELAY);
    }
  }, [flush]);

  // Opening the file picker for an image answer takes focus away; that isn't leaving the exam.
  // Switching tabs still counts, because that also hides the page.
  const allowFilePicker = useCallback(() => {
    ignoreBlurUntilFocus.current = true;
  }, []);

  // The click (or key press on the Return button) that brings the student back to the questions
  const returnToExam = useCallback(() => {
    if (document.hidden) return;
    setNeedsReturn(false);
    if (settings?.block_copy_paste) clearClipboard(); // a click is when browsers reliably allow this
    if (requireFullscreen) enterFullscreen();
  }, [settings?.block_copy_paste, requireFullscreen]);

  useEffect(() => {
    if (!active || !attemptId) return undefined;

    const leave = (tabHidden) => {
      if (awaySince.current) return; // already away: one violation per episode
      awaySince.current = Date.now();
      setIsAway(true);
      setNeedsReturn(true);
      record('focus_lost', { tab_hidden: tabHidden }, { violation: true });
    };

    const comeBack = () => {
      if (!awaySince.current || document.hidden || !document.hasFocus()) return;
      record('focus_returned', { away_ms: Date.now() - awaySince.current });
      awaySince.current = null;
      setIsAway(false);
      // Whatever they copied while away doesn't come back with them
      if (settings?.block_copy_paste) clearClipboard();
    };

    const onVisibility = () => {
      if (document.hidden) {
        ignoreBlurUntilFocus.current = false;
        leave(true);
      } else {
        comeBack();
      }
    };

    const onBlur = () => {
      // Let the focus settle: focus can move to the browser's own UI for a moment
      setTimeout(() => {
        if (document.hasFocus()) return;
        if (ignoreBlurUntilFocus.current) return;
        leave(document.hidden);
      }, 50);
    };

    const onFocus = () => {
      ignoreBlurUntilFocus.current = false;
      comeBack();
    };

    const onFullscreenChange = () => {
      if (!requireFullscreen) return;
      if (inFullscreen()) {
        setFullscreenLost(false);
        return;
      }
      setFullscreenLost(true);
      const leftWindowJustNow = awaySince.current && Date.now() - awaySince.current < FULLSCREEN_GRACE;
      if (!leftWindowJustNow) record('fullscreen_exit', null, { violation: true });
    };

    const onClipboard = (e) => {
      if (!settings?.block_copy_paste) return;
      e.preventDefault();
      record('copy_paste', { action: e.type });
    };

    // Paste from the browser menu, drag-and-drop and middle-click all end up here, whatever started them
    const onBeforeInput = (e) => {
      if (!settings?.block_copy_paste || !PASTE_INPUT_TYPES.has(e.inputType)) return;
      e.preventDefault();
      record('copy_paste', { action: e.inputType });
    };

    const onDrop = (e) => {
      if (!settings?.block_copy_paste) return;
      e.preventDefault();
      record('copy_paste', { action: 'drop' });
    };

    const onDragStart = (e) => {
      if (settings?.block_copy_paste) e.preventDefault(); // dragging question text out is copying
    };

    const onSelectStart = (e) => {
      if (settings?.block_copy_paste && !inAnswerBox(e.target)) e.preventDefault();
    };

    const onMiddleClick = (e) => {
      if (e.button !== 1 || !settings?.block_copy_paste) return;
      e.preventDefault(); // middle-click pastes the selection on Linux
      record('copy_paste', { action: 'middle_click' });
    };

    const onContextMenu = (e) => {
      e.preventDefault();
      record('context_menu');
    };

    const onKeyDown = (e) => {
      if (isAlwaysBlocked(e) || (settings?.block_copy_paste && isCopyShortcut(e))) {
        e.preventDefault();
        record('blocked_shortcut', { key: describeKey(e) });
        return;
      }
      if (settings?.block_copy_paste && isSelectAll(e) && !inAnswerBox(e.target)) e.preventDefault();
    };

    const onKeyUp = (e) => {
      if (e.key === 'PrintScreen') record('blocked_shortcut', { key: 'PrintScreen' });
    };

    const onBeforeUnload = (e) => {
      flush();
      e.preventDefault();
      e.returnValue = '';
    };

    // Screens beyond the first, where supported (Chromium)
    if (window.screen?.isExtended) record('multiple_screens');
    if (settings?.block_copy_paste) {
      clearClipboard();
      window.getSelection?.()?.removeAllRanges();
    }
    if (requireFullscreen && !inFullscreen()) setFullscreenLost(true);

    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('copy', onClipboard);
    document.addEventListener('cut', onClipboard);
    document.addEventListener('paste', onClipboard);
    document.addEventListener('beforeinput', onBeforeInput, true);
    document.addEventListener('drop', onDrop, true);
    document.addEventListener('dragstart', onDragStart, true);
    document.addEventListener('selectstart', onSelectStart, true);
    document.addEventListener('auxclick', onMiddleClick, true);
    document.addEventListener('mousedown', onMiddleClick, true);
    document.addEventListener('contextmenu', onContextMenu);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('keyup', onKeyUp);
    window.addEventListener('beforeunload', onBeforeUnload);

    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('copy', onClipboard);
      document.removeEventListener('cut', onClipboard);
      document.removeEventListener('paste', onClipboard);
      document.removeEventListener('beforeinput', onBeforeInput, true);
      document.removeEventListener('drop', onDrop, true);
      document.removeEventListener('dragstart', onDragStart, true);
      document.removeEventListener('selectstart', onSelectStart, true);
      document.removeEventListener('auxclick', onMiddleClick, true);
      document.removeEventListener('mousedown', onMiddleClick, true);
      document.removeEventListener('contextmenu', onContextMenu);
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('beforeunload', onBeforeUnload);
      flush();
    };
  }, [active, attemptId, requireFullscreen, settings?.block_copy_paste, record, flush]);

  return {
    violations,
    maxViolations: settings?.max_violations || null,
    isAway,
    needsReturn,
    // Questions stay hidden while away, after coming back until the student clicks in, and out of fullscreen (when required)
    blocked: active && (isAway || needsReturn || (requireFullscreen && fullscreenLost)),
    fullscreenLost: requireFullscreen && fullscreenLost,
    requireFullscreen,
    lastViolation,
    allowFilePicker,
    returnToExam,
  };
}
