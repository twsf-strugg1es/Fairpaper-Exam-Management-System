// Offline-tolerant answer saving for the exam page.
//
// Every answer goes into a queue that lives in IndexedDB (memory if the browser blocks it), keyed
// by attempt and question, so only the newest value per question waits. The queue sends answers
// one at a time and retries with backoff while the network is down; a reload picks up whatever
// hadn't been delivered. Each save carries an increasing `client_seq`, and the server ignores one
// that is older than what it already stored, so a delayed retry can't overwrite a newer answer.

const DB_NAME = 'fairpaper-exam';
const STORE = 'answers';
const RETRY_STEPS = [1000, 2000, 4000, 8000, 15000, 30000];

const key = (attemptId, questionId) => `${attemptId}:${questionId}`;

export function memoryStorage() {
  const rows = new Map();
  return {
    put: async (row) => { rows.set(key(row.attemptId, row.questionId), { ...row }); },
    get: async (attemptId, questionId) => rows.get(key(attemptId, questionId)) || null,
    remove: async (attemptId, questionId) => { rows.delete(key(attemptId, questionId)); },
    list: async (attemptId) => [...rows.values()].filter((r) => r.attemptId === attemptId),
  };
}

function request(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

const OPEN_TIMEOUT_MS = 3000;

// IndexedDB storage, or memory when it isn't available (some private windows, old browsers)
export async function openStorage() {
  try {
    if (typeof indexedDB === 'undefined') return memoryStorage();
    const open = indexedDB.open(DB_NAME, 1);
    open.onupgradeneeded = () => open.result.createObjectStore(STORE, { keyPath: 'key' });
    // An open that never finishes (blocked by another tab, a stuck profile) must not hold up starting the exam
    const db = await Promise.race([
      request(open),
      new Promise((_, reject) => { setTimeout(() => reject(new Error('IndexedDB did not open')), OPEN_TIMEOUT_MS); }),
    ]);
    const store = (mode) => db.transaction(STORE, mode).objectStore(STORE);
    return {
      put: (row) => request(store('readwrite').put({ ...row, key: key(row.attemptId, row.questionId) })),
      get: async (attemptId, questionId) => (await request(store('readonly').get(key(attemptId, questionId)))) || null,
      remove: (attemptId, questionId) => request(store('readwrite').delete(key(attemptId, questionId))),
      list: async (attemptId) => (await request(store('readonly').getAll())).filter((r) => r.attemptId === attemptId),
    };
  } catch {
    return memoryStorage();
  }
}

// Network trouble (no response, or the server is briefly unwell) is worth retrying;
// a clear "no" from the server is not.
const isRetryable = (err) => !err?.response || err.response.status >= 500 || err.response.status === 429;

/**
 * send(row) posts one answer and resolves when the server has it (saved or stale).
 * onChange({ status, waiting }) reports 'saved' | 'saving' | 'offline' | 'error'.
 * onClosed(detail) runs when the server says the attempt is over.
 */
export function createAnswerQueue({ attemptId, send, storage, onChange = () => {}, onClosed = () => {}, now = () => Date.now(), schedule = setTimeout, cancel = clearTimeout }) {
  let lastSeq = 0;
  let running = null;
  let timer = null;
  let attempt = 0;
  let stopped = false;
  const report = async (status) => {
    onChange({ status, waiting: (await storage.list(attemptId)).length });
  };

  // Strictly increasing, and larger than anything sent before a reload
  const nextSeq = () => {
    lastSeq = Math.max(lastSeq + 1, now());
    return lastSeq;
  };

  const retryLater = (delay) => {
    timer = schedule(() => { timer = null; flush(); }, delay); // eslint-disable-line no-use-before-define
  };

  const drain = async () => {
    let dropped = false;
    while (!stopped) {
      const rows = (await storage.list(attemptId)).sort((a, b) => a.seq - b.seq);
      if (!rows.length) { attempt = 0; await report(dropped ? 'error' : 'saved'); return !dropped; }
      const row = rows[0];
      try {
        await send(row);
        // Only clear it if no newer answer for the same question arrived while it was in flight
        const current = await storage.get(attemptId, row.questionId);
        if (current && current.seq === row.seq) await storage.remove(attemptId, row.questionId);
        attempt = 0;
      } catch (err) {
        if (isRetryable(err)) {
          const delay = RETRY_STEPS[Math.min(attempt, RETRY_STEPS.length - 1)];
          attempt += 1;
          await report(err?.response ? 'error' : 'offline');
          retryLater(delay);
          return false;
        }
        const detail = err.response?.data?.detail || '';
        if (/submitted|time is over/i.test(detail)) {
          stopped = true;
          onClosed(detail);
          return false;
        }
        // Rejected for good (e.g. the question isn't in this exam): drop it, say so, move on
        await storage.remove(attemptId, row.questionId);
        dropped = true;
      }
    }
    return false;
  };

  // Send everything now. Resolves true when nothing is left waiting.
  const flush = () => {
    if (stopped) return Promise.resolve(false);
    if (timer) { cancel(timer); timer = null; }
    // Already sending: let that pass finish, then go round once more for anything it missed
    if (running) return running.then(() => flush());
    running = drain().finally(() => { running = null; });
    return running;
  };

  return {
    // Restore what a previous visit didn't deliver; returns { questionId: value } to show
    async restore() {
      const rows = await storage.list(attemptId);
      lastSeq = Math.max(lastSeq, ...rows.map((r) => r.seq), 0);
      if (rows.length) { await report('saving'); flush(); }
      return Object.fromEntries(rows.map((r) => [r.questionId, r.value]));
    },
    async enqueue(questionId, value) {
      if (stopped) return;
      await storage.put({ attemptId, questionId, value, seq: nextSeq() });
      await report('saving');
      flush();
    },
    flush,
    waiting: async () => (await storage.list(attemptId)).length,
    // Forget everything for this attempt (after it's submitted)
    async clear() {
      stopped = true;
      if (timer) cancel(timer);
      await Promise.all((await storage.list(attemptId)).map((r) => storage.remove(attemptId, r.questionId)));
    },
    stop() { stopped = true; if (timer) cancel(timer); },
  };
}
