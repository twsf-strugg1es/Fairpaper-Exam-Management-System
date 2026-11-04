import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import api from '../api';
import GetStarted from './GetStarted';

jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));
let mockAuth = { currentMembership: { organization_id: 'org-1' }, isManager: true };
jest.mock('../context/AuthContext', () => ({ useAuth: () => mockAuth }));

const progress = (steps) => ({ data: { steps, done: Object.values(steps).every(Boolean) } });
const renderIt = () => render(<MemoryRouter><GetStarted /></MemoryRouter>);

beforeEach(() => { localStorage.clear(); mockAuth = { currentMembership: { organization_id: 'org-1' }, isManager: true }; });

test('shows the steps left and points at the next one', async () => {
  api.get.mockResolvedValue(progress({ students: true, groups: false, questions: false, exams: false }));
  renderIt();
  expect(await screen.findByRole('region', { name: 'Get started' })).toBeInTheDocument();
  expect(screen.getByText('1 of 4 done')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create a group' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Invite students' })).not.toBeInTheDocument(); // done
});

test('disappears when every step is done', async () => {
  api.get.mockResolvedValue(progress({ students: true, groups: true, questions: true, exams: true }));
  renderIt();
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/org/setup'));
  expect(screen.queryByRole('region', { name: 'Get started' })).not.toBeInTheDocument();
});

test('can be hidden, and stays hidden for this organization', async () => {
  api.get.mockResolvedValue(progress({ students: false, groups: false, questions: false, exams: false }));
  const { unmount } = renderIt();
  await userEvent.click(await screen.findByRole('button', { name: 'Hide this checklist' }));
  expect(screen.queryByRole('region', { name: 'Get started' })).not.toBeInTheDocument();
  unmount();
  renderIt();
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole('region', { name: 'Get started' })).not.toBeInTheDocument();
});

test('examiners see which steps an admin has to do', async () => {
  mockAuth = { currentMembership: { organization_id: 'org-1' }, isManager: false };
  api.get.mockResolvedValue(progress({ students: false, groups: false, questions: false, exams: false }));
  renderIt();
  expect(await screen.findAllByText('An admin does this')).toHaveLength(2);
  expect(screen.getByRole('button', { name: 'Open the question bank' })).toBeInTheDocument();
});
