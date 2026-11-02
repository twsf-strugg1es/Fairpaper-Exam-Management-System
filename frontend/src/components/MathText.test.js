import { render, screen, waitFor } from '@testing-library/react';
import MathText, { hasMath, splitMath } from './MathText';

const kinds = (text) => splitMath(text).map((part) => [part.type, part.value]);

test('dollars are math only by Pandoc’s rule', () => {
  expect(kinds('Solve $x^2 = 4$ for x')).toEqual([['text', 'Solve '], ['inline', 'x^2 = 4'], ['text', ' for x']]);
  expect(kinds('$$\\int_0^1 x\\,dx$$')).toEqual([['display', '\\int_0^1 x\\,dx']]);
  expect(kinds('It costs $20 and $30')).toEqual([['text', 'It costs $20 and $30']]); // closing $ before a digit
  expect(kinds('A $ sign alone, and $ x$ too')).toEqual([['text', 'A $ sign alone, and $ x$ too']]); // space after the opening $
  expect(kinds('Pay \\$5, then find $y$')).toEqual([['text', 'Pay $5, then find '], ['inline', 'y']]);
  expect(kinds('Unclosed $x + 1')).toEqual([['text', 'Unclosed $x + 1']]);
  expect(hasMath('No math here')).toBe(false);
  expect(hasMath('Area $\\pi r^2$')).toBe(true);
});

test('text without math is left as it is, and math is drawn by KaTeX', async () => {
  const { container, rerender } = render(<p>{<MathText text="Plain words, $5 each" />}</p>);
  expect(container.textContent).toBe('Plain words, $5 each');
  rerender(<p><MathText text="Area is $\pi r^2$." /></p>);
  await waitFor(() => expect(container.querySelector('.katex')).not.toBeNull());
  expect(screen.getByText(/Area is/)).toBeInTheDocument();
  expect(container.textContent).not.toContain('$');
});

test('KaTeX refuses links and other commands that reach outside the text', async () => {
  const { container } = render(<p><MathText text={'See $\\href{https://example.com}{here}$'} /></p>);
  await waitFor(() => expect(container.querySelector('.katex')).not.toBeNull());
  expect(container.querySelector('a')).toBeNull();
});
