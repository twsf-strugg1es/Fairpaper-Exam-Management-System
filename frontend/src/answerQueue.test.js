import { createAnswerQueue, memoryStorage } from './answerQueue';

const offline = () => Object.assign(new Error('Network Error'), { response: undefined });
const closed = () => Object.assign(new Error('403'), { response: { status: 403, data: { detail: 'Exam already submitted' } } });

// A fake server that can be switched off, and a fake clock for the retry timer
function setup({ start = 1000 } = {}) {
  const server = { online: true, stored: {}, sent: [] };
  const timers = [];
  let clock = start;
  const changes = [];
  const storage = memoryStorage();
  const send = async (row) => {
    server.sent.push(row);
    if (server.online === 'closed') throw closed();
    if (!server.online) throw offline();
    const prev = server.stored[row.questionId];
    if (!prev || prev.seq < row.seq) server.stored[row.questionId] = { value: row.value, seq: row.seq };
  };
  const make = (extra = {}) => createAnswerQueue({
    attemptId: 'a1', send, storage, now: () => clock,
    onChange: (c) => changes.push(c),
    schedule: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    cancel: () => {},
    ...extra,
  });
  return { server, timers, storage, changes, make, tick: (ms = 1) => { clock += ms; } };
}

test('answers saved while offline are delivered when the connection returns', async () => {
  const { server, timers, make, changes } = setup();
  const queue = make();
  server.online = false;

  await queue.enqueue('q1', 'A');
  await queue.flush();
  await queue.enqueue('q2', 'B');
  await queue.flush();

  expect(changes.at(-1)).toEqual({ status: 'offline', waiting: 2 });
  expect(timers.map((t) => t.ms).slice(0, 2)).toEqual([1000, 2000]); // backs off

  server.online = true;
  timers.at(-1).fn();
  await queue.flush();

  expect(server.stored).toEqual({ q1: { value: 'A', seq: 1000 }, q2: { value: 'B', seq: 1001 } });
  expect(changes.at(-1)).toEqual({ status: 'saved', waiting: 0 });
});

test('only the newest answer per question waits, and it wins', async () => {
  const { server, make } = setup();
  const queue = make();
  server.online = false;
  await queue.enqueue('q1', 'A');
  await queue.enqueue('q1', 'B');
  await queue.enqueue('q1', 'C');
  expect(await queue.waiting()).toBe(1);

  server.online = true;
  await queue.flush();
  expect(server.stored.q1.value).toBe('C');
});

test('a reload resends what was not delivered, with larger numbers than before', async () => {
  const { server, storage, make, tick } = setup({ start: 5000 });
  server.online = false;
  const first = make();
  await first.enqueue('q1', 'A');
  await first.flush();
  first.stop();

  // The page reloads (same storage); the clock went backwards a little
  tick(-2000);
  server.online = true;
  const second = make();
  const restored = await second.restore();
  expect(restored).toEqual({ q1: 'A' });
  await second.flush();
  expect(server.stored.q1).toEqual({ value: 'A', seq: 5000 });

  await second.enqueue('q1', 'B');
  await second.flush();
  expect(server.stored.q1.value).toBe('B'); // seq 5001, newer despite the clock
  expect(await storage.list('a1')).toEqual([]);
});

test('an answer changed while its save is in flight is not lost', async () => {
  const { server, make } = setup();
  let release;
  const slow = new Promise((r) => { release = r; });
  const sendSlowly = async (row) => { if (row.value === 'A') await slow; server.stored[row.questionId] = row; };
  const queue = make({ send: sendSlowly });

  await queue.enqueue('q1', 'A');
  const inFlight = queue.flush();
  await queue.enqueue('q1', 'B'); // typed while A was on its way
  release();
  await inFlight;
  await queue.flush();
  expect(server.stored.q1.value).toBe('B');
  expect(await queue.waiting()).toBe(0);
});

test('when the server says the attempt is over, the queue stops', async () => {
  const { server, make } = setup();
  const onClosed = jest.fn();
  const queue = make({ onClosed });
  server.online = 'closed';
  await queue.enqueue('q1', 'A');
  await queue.flush();
  expect(onClosed).toHaveBeenCalledWith('Exam already submitted');
  await queue.enqueue('q2', 'B');
  expect(server.sent).toHaveLength(1);
});
