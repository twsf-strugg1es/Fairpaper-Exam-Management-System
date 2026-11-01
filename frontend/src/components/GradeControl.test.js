import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api from '../api';
import GradeControl from './GradeControl';

jest.mock('../api', () => ({ __esModule: true, default: { post: jest.fn() } }));

beforeEach(() => {
  api.post.mockReset();
  api.post.mockImplementation((url, body) => Promise.resolve({ data: { score_awarded: body.score_awarded } }));
});

test('a quick mark saves at once, with the comment', async () => {
  const onSaved = jest.fn();
  render(<GradeControl answerId="a1" worth={4} score={null} comment="" onSaved={onSaved} />);
  await userEvent.type(screen.getByLabelText('Comment for the student'), 'Name the products.');
  // Saves finish after the click handler returns, so let them settle inside act
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Half marks (2)' })); });
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('a1', { score: 2, comment: 'Name the products.' }));
  expect(api.post).toHaveBeenLastCalledWith('/admin/evaluations/answers/a1/submit', { score_awarded: 2, comment: 'Name the products.' });
  expect(await screen.findByText('Saved')).toBeInTheDocument();
});

test('Enter saves a typed mark once and moves on', async () => {
  const onNext = jest.fn();
  render(<GradeControl answerId="a1" worth={4} score={null} comment="" onNext={onNext} />);
  await userEvent.type(screen.getByLabelText('Mark out of 4'), '2,5');
  await act(async () => { await userEvent.keyboard('{Enter}'); });
  await waitFor(() => expect(onNext).toHaveBeenCalled());
  await userEvent.tab(); // leaving the box afterwards doesn't send the same mark again
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post.mock.calls[0][1]).toEqual({ score_awarded: 2.5, comment: '' });
});

test('a mark above what the question is worth is refused before sending', async () => {
  const onNext = jest.fn();
  render(<GradeControl answerId="a1" worth={4} score={null} comment="" onNext={onNext} />);
  await userEvent.type(screen.getByLabelText('Mark out of 4'), '9{Enter}');
  expect(await screen.findByRole('alert')).toHaveTextContent('Give a mark from 0 to 4.');
  expect(api.post).not.toHaveBeenCalled();
  expect(onNext).not.toHaveBeenCalled();
});

test("a failed save says so, and the same mark can be sent again", async () => {
  api.post.mockRejectedValueOnce({ response: { status: 400, data: { detail: 'This answer can be graded once the student submits.' } } });
  render(<GradeControl answerId="a1" worth={4} score={null} comment="" />);
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Full marks (4)' })); });
  expect(await screen.findByRole('alert')).toHaveTextContent('This answer can be graded once the student submits.');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Full marks (4)' })); });
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
  expect(await screen.findByText('Saved')).toBeInTheDocument();
});
