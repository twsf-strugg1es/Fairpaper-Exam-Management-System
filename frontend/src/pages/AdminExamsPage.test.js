import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ExamMenu } from './AdminExamsPage';

jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));

const exam = { id: 'exam-1', is_published: true, edit_blocked: false };
const renderMenu = () => render(<MemoryRouter><ExamMenu exam={exam} onPublishToggle={jest.fn()} onDelete={jest.fn()} /></MemoryRouter>);
const placeButton = (top) => jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ top, bottom: top + 32, left: 900, right: 932, width: 32, height: 32 });

afterEach(() => jest.restoreAllMocks());

test('the row menu opens from its button and Escape closes it, back on the button', async () => {
  placeButton(100);
  renderMenu();
  const button = screen.getByRole('button', { name: 'More actions' });
  await userEvent.click(button);
  expect(button).toHaveAttribute('aria-expanded', 'true');
  const unpublish = screen.getByRole('button', { name: 'Unpublish' });
  expect(unpublish.parentElement.style.top).toBe('136px'); // under the button, outside the table's scroll box
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('button', { name: 'Unpublish' })).not.toBeInTheDocument();
  expect(button).toHaveFocus();
});

test('near the bottom of the window the menu opens upward instead of being cut off', async () => {
  placeButton(window.innerHeight - 60);
  renderMenu();
  await userEvent.click(screen.getByRole('button', { name: 'More actions' }));
  const menu = screen.getByRole('button', { name: 'Unpublish' }).parentElement;
  expect(menu.style.top).toBe('');
  expect(menu.style.bottom).toBe('64px');
});
