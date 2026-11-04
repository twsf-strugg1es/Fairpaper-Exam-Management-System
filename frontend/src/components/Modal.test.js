import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from './ui';

function Page() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Submit exam</button>
      <Modal open={open} onClose={() => setOpen(false)} title="Submit the exam?"
        footer={<><button type="button" onClick={() => setOpen(false)}>Cancel</button><button type="button">Submit</button></>} />
    </>
  );
}

test('a dialog takes focus, keeps Tab inside, closes on Escape and gives focus back', async () => {
  render(<Page />);
  const opener = screen.getByRole('button', { name: 'Submit exam' });
  await userEvent.click(opener);
  expect(screen.getByRole('dialog', { name: 'Submit the exam?' })).toHaveFocus();

  await userEvent.tab();
  expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
  await userEvent.tab();
  await userEvent.tab();
  expect(screen.getByRole('button', { name: 'Submit' })).toHaveFocus();
  await userEvent.tab(); // past the last control, back to the first
  expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
  await userEvent.tab({ shift: true }); // and the other way round
  expect(screen.getByRole('button', { name: 'Submit' })).toHaveFocus();

  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
});

test("a re-render of the page behind doesn't pull focus back to the dialog", () => {
  // The exam page re-renders every second for its timer, with a new onClose each time
  const dialog = () => <Modal open onClose={() => {}} title="Submit the exam?" footer={<button type="button">Submit</button>} />;
  const { rerender } = render(dialog());
  const submit = screen.getByRole('button', { name: 'Submit' });
  submit.focus();
  rerender(dialog());
  expect(submit).toHaveFocus();
});
