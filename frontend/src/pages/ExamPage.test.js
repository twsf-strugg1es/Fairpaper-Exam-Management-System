import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import api from '../api';
import ExamPage from './ExamPage';
// Real API responses, written by backend/scripts/exam_page_fixture.py
import fixture from './__fixtures__/examPage.json';

jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), defaults: { baseURL: 'http://api.test' } } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ refreshSession: jest.fn() }) }));

const exam = fixture.exams[0];
const posted = (tail) => api.post.mock.calls.filter(([url]) => url.endsWith(tail));

// Integrity events go out with fetch (keepalive), so they survive the page closing
const sentEvents = () => global.fetch.mock.calls.filter(([url]) => url.endsWith('/events')).flatMap(([, init]) => JSON.parse(init.body).events);

beforeEach(() => {
  sessionStorage.clear();
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
  api.get.mockImplementation((url) => {
    if (url === '/student/exams/') return Promise.resolve({ data: fixture.exams });
    if (url === '/student/unfinished-attempts/') return Promise.resolve({ data: [] });
    if (url.endsWith('/answers')) return Promise.resolve({ data: [] });
    if (url.endsWith('/clock')) return Promise.resolve({ data: fixture.clock });
    if (url.endsWith('/results')) return Promise.resolve({ data: fixture.results });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  api.post.mockImplementation((url) => {
    if (url.endsWith('/start')) return Promise.resolve({ data: fixture.session });
    if (url.endsWith('/save-answer')) return Promise.resolve({ data: fixture.save });
    if (url.endsWith('/events')) return Promise.resolve({ data: {} });
    if (url.endsWith('/submit')) return Promise.resolve({ data: fixture.submit });
    return Promise.reject(new Error(`unexpected POST ${url}`));
  });
});
afterEach(() => jest.clearAllMocks());

const renderExam = () => render(
  <MemoryRouter initialEntries={[`/exam/${exam.id}`]}>
    <Routes><Route path="/exam/:id" element={<ExamPage />} /></Routes>
  </MemoryRouter>,
);

async function start() {
  renderExam();
  await userEvent.click(await screen.findByRole('button', { name: /start exam/i }));
  return screen.findByText('What is 2 + 2?');
}

test('from the rules screen to an answer saved and the exam submitted', async () => {
  renderExam();
  expect(await screen.findByRole('heading', { name: exam.title })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /start exam/i }));
  expect(await screen.findByText('What is 2 + 2?')).toBeInTheDocument();
  expect(posted('/start')).toHaveLength(1);

  await userEvent.keyboard('2'); // the second option, "4"
  await waitFor(() => expect(posted('/save-answer').some(([, body]) => body.answer_data === '4')).toBe(true));
  expect(screen.getByText('1 of 2')).toBeInTheDocument(); // answered

  await userEvent.click(screen.getByRole('button', { name: 'Submit exam' }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.click(within(dialog).getByRole('button', { name: /submit/i }));
  await waitFor(() => expect(posted('/submit')).toHaveLength(1));
  // The results screen replaces the exam
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Submit exam' })).not.toBeInTheDocument());
});

test('leaving the exam hides the questions until the student comes back and returns', async () => {
  await start();
  const hidden = Object.getOwnPropertyDescriptor(Document.prototype, 'hidden');
  try {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    act(() => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(screen.queryByText('What is 2 + 2?')).not.toBeInTheDocument();
    await waitFor(() => expect(sentEvents().some((e) => e.type === 'focus_lost')).toBe(true));

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
    act(() => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(screen.queryByText('What is 2 + 2?')).not.toBeInTheDocument(); // still covered until they say so
    await userEvent.click(screen.getByRole('button', { name: /return to the exam/i }));
    expect(await screen.findByText('What is 2 + 2?')).toBeInTheDocument();
  } finally {
    delete document.hidden;
    if (hidden) Object.defineProperty(Document.prototype, 'hidden', hidden);
  }
});
