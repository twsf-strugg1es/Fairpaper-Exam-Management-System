import { answerText, blankCount, isAnswered, keyText, parseNumber, splitBlanks } from './questionTypes';
import { EMPTY_KEY, keyFromQuestion, keyPayload, keyProblem } from './components/AnswerKeyEditor';

const t = (text, vars = {}) => text.replace(/{{(\w+)}}/g, (_, k) => vars[k]);

test('numbers are read the way the server reads them', () => {
  // The same cases as backend/tests/test_question_types.py
  const cases = [['9.8', 9.8], [' 9,81 ', 9.81], ['0,500', 0.5], ['1,000', 1000], ['1,00,000', 100000], ['12,34,567', 1234567],
    ['1,000.5', 1000.5], ['1.000,5', 1000.5], ['১২.৫', 12.5], ['−3', -3], ['-0,5', -0.5], ['1 000', 1000], ['6.02e23', 6.02e23],
    [7, 7], ['٣٫١٤', 3.14]];
  cases.forEach(([typed, number]) => expect(parseNumber(typed)).toBeCloseTo(number));
  ['', 'abc', 'nan', 'inf', '-infinity', '1.2.3', '9.8 m/s', null].forEach((typed) => expect(parseNumber(typed)).toBeNull());
});

test('blanks are counted from ___ markers, one when there are none', () => {
  expect(blankCount('The capital is ___.')).toBe(1);
  expect(blankCount('___ over ______')).toBe(2);
  expect(blankCount('No marker')).toBe(1);
  expect(blankCount('Two __ underscores are not a blank')).toBe(1);
  expect(splitBlanks('a ___ b ___')).toEqual(['a ', ' b ', '']);
});

test('an empty matching answer or empty blanks are not answers yet', () => {
  expect(isAnswered({})).toBe(false);
  expect(isAnswered({ Bangladesh: '' })).toBe(false);
  expect(isAnswered(['', ''])).toBe(false);
  expect(isAnswered(['Dhaka', ''])).toBe(true);
  expect(isAnswered({ name: 'photo.jpg', preview: 'data:' })).toBe(true);
  expect(isAnswered('false')).toBe(true);
});

test('answers and keys read as one line', () => {
  expect(answerText('true_false', 'false', t)).toBe('False');
  expect(answerText('matching', { Bangladesh: 'Dhaka' }, t)).toBe('Bangladesh: Dhaka');
  expect(answerText('ordering', ['Mercury', 'Venus'], t)).toBe('1. Mercury, 2. Venus');
  expect(answerText('fill_blank', ['top', ''], t)).toBe('top · —');
  expect(answerText('numeric', '', t)).toBeNull();
  expect(keyText('numeric', { value: 9.8, tolerance: 0.1 }, t)).toBe('9.8 ± 0.1');
  expect(keyText('fill_blank', [['Dhaka', 'Dacca']], t)).toBe('Dhaka / Dacca');
});

const STORED = [
  { type: 'single_choice', options: ['A', 'B'], correct_answers: 'B' },
  { type: 'multi_choice', options: ['A', 'B', 'C'], correct_answers: ['A', 'C'] },
  { type: 'true_false', options: ['true', 'false'], correct_answers: 'false' },
  { type: 'fill_blank', title: '___ over ___', options: null, correct_answers: [['numerator'], ['denominator', 'bottom']] },
  { type: 'matching', options: { left: ['Bangladesh', 'India'], right: ['Dhaka', 'New Delhi', 'Karachi'] }, correct_answers: { Bangladesh: 'Dhaka', India: 'New Delhi' } },
  { type: 'ordering', options: ['Mercury', 'Venus', 'Earth'], correct_answers: ['Mercury', 'Venus', 'Earth'] },
];

test('a stored key opens in the editor and saves back unchanged', () => {
  STORED.forEach((question) => {
    const form = { ...EMPTY_KEY, title: question.title || 'Question', type: question.type, ...keyFromQuestion(question) };
    expect(keyProblem(form, t)).toBeNull();
    // True or false and fill in the blank have no options to send: the server sets them
    const options = ['true_false', 'fill_blank'].includes(question.type) ? null : question.options;
    expect(keyPayload(form)).toEqual({ options, correct_answers: question.correct_answers });
  });
  const numeric = { ...EMPTY_KEY, type: 'numeric', ...keyFromQuestion({ type: 'numeric', correct_answers: { value: 9.8, tolerance: 0.1 } }) };
  expect(keyPayload(numeric)).toEqual({ options: null, correct_answers: { value: '9.8', tolerance: '0.1' } });
});

test('the editor names what is missing before saving', () => {
  const form = (type, key) => ({ ...EMPTY_KEY, title: 'The capital is ___.', type, ...key });
  expect(keyProblem(form('true_false', {}), t)).toBe('Mark whether the statement is true or false.');
  expect(keyProblem(form('fill_blank', { blanks: [[' ']] }), t)).toBe('Give at least one accepted answer for every blank.');
  expect(keyProblem(form('numeric', { number: { value: 'ten', tolerance: '0' } }), t)).toBe('Give the correct answer as a number.');
  expect(keyProblem(form('numeric', { number: { value: '10', tolerance: '-1' } }), t)).toBe("The margin can't be negative.");
  expect(keyProblem(form('matching', { pairs: [{ left: 'A', right: '1' }, { left: 'B', right: '' }] }), t)).toBe('Fill in both sides of every pair or remove the empty ones.');
  expect(keyProblem(form('matching', { pairs: [{ left: 'A', right: '1' }, { left: 'B', right: '1' }] }), t)).toBe('Two matches have the same text.');
  expect(keyProblem(form('ordering', { items: ['Mercury', 'Mercury'] }), t)).toBe('Two items have the same text.');
});
