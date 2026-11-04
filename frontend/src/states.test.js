import React from 'react';
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { ErrorState, NoResults } from './components/ui';
import useDraft from './hooks/useDraft';
import { errorKind, suggestCorrection, suggestEmail } from './utils';

// Task 3.15: the states a screen falls into when things don't go to plan

test('a typo in a search gets a "did you mean"', () => {
  expect(suggestCorrection('phisics', ['Physics model test', 'Chemistry'])).toBe('physics');
  expect(suggestCorrection('physics', ['Physics model test'])).toBeNull(); // already right
  expect(suggestCorrection('zz', ['Physics'])).toBeNull(); // too short to guess
  expect(suggestCorrection('quantum', ['Physics', 'Chemistry'])).toBeNull(); // nothing close
});

test('a mistyped email domain is caught, a correct one is left alone', () => {
  expect(suggestEmail('mim@gmial.com')).toBe('mim@gmail.com');
  expect(suggestEmail('mim@outlok.com')).toBe('mim@outlook.com');
  expect(suggestEmail('mim@gmail.com')).toBeNull();
  expect(suggestEmail('teacher@dhakaschool.edu.bd')).toBeNull();
  expect(suggestEmail('not an email')).toBeNull();
});

test('errors are sorted by whose side they are on', () => {
  expect(errorKind({ message: 'Network Error' })).toBe('unreachable');
  expect(errorKind({ response: { status: 500 } })).toBe('server');
  expect(errorKind({ response: { status: 403 } })).toBe('forbidden');
  expect(errorKind({ response: { status: 404 } })).toBe('notFound');
  expect(errorKind({ response: { status: 401 } })).toBe('expired');
  expect(errorKind({ response: { status: 422 } })).toBe('invalid');
});

test('a server error says it is not your fault and offers Try again', () => {
  const retry = jest.fn();
  render(<ErrorState error={{ response: { status: 503 } }} onRetry={retry} />);
  expect(screen.getByText('Something went wrong on our side')).toBeInTheDocument();
  expect(screen.getByText(/not something you did/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(retry).toHaveBeenCalled();
});

test('a missing page does not offer Try again, which would not help', () => {
  render(<ErrorState error={{ response: { status: 404, data: { detail: 'Exam not found' } } }} onRetry={() => {}} />);
  expect(screen.getByText("We couldn't find this")).toBeInTheDocument();
  expect(screen.getByText('Exam not found')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
});

test('no results is never a dead end', () => {
  const use = jest.fn();
  const clear = jest.fn();
  render(<NoResults query="phisics" suggestion="physics" onSuggest={use} onClear={clear} />);
  expect(screen.getByText('Nothing matches “phisics”')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'physics' }));
  expect(use).toHaveBeenCalledWith('physics');
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  expect(clear).toHaveBeenCalled();
});

describe('drafts', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    localStorage.clear();
  });
  afterEach(() => jest.useRealTimers());

  test('opening a form writes nothing; a change is kept, offered back next time, and cleared on save', () => {
    const { rerender, unmount } = renderHook(({ value }) => useDraft('exam:new', value), { initialProps: { value: { title: '' } } });
    act(() => { jest.advanceTimersByTime(1000); });
    expect(Object.keys(localStorage).filter((k) => k.startsWith('fp-draft:'))).toHaveLength(0);

    rerender({ value: { title: 'Physics test' } });
    act(() => { jest.advanceTimersByTime(1000); });
    unmount();

    const next = renderHook(() => useDraft('exam:new', { title: '' }));
    expect(next.result.current.draft).toEqual({ title: 'Physics test' });
    act(() => { next.result.current.clear(); });
    expect(next.result.current.draft).toBeNull();
    expect(Object.keys(localStorage).filter((k) => k.startsWith('fp-draft:'))).toHaveLength(0);
  });
});
