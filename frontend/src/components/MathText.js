import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { cx } from './ui';

// Math in question text (task 4.8): $…$ inline and $$…$$ on a line of its own, drawn by KaTeX, which is loaded
// only once some text on the page has math in it. A single $ opens math only by Pandoc's rule: no space right
// after the opening $, none right before the closing one, and no digit right after it, so "$20 and $30" stays
// text. \$ is a dollar sign.

export function splitMath(text) {
  const source = String(text ?? '');
  const parts = [];
  let plain = '';
  let i = 0;
  const flush = () => {
    if (plain) parts.push({ type: 'text', value: plain });
    plain = '';
  };
  while (i < source.length) {
    if (source[i] === '\\' && source[i + 1] === '$') {
      plain += '$';
      i += 2;
      continue;
    }
    if (source.startsWith('$$', i)) {
      const end = source.indexOf('$$', i + 2);
      if (end > i + 2) {
        flush();
        parts.push({ type: 'display', value: source.slice(i + 2, end).trim() });
        i = end + 2;
        continue;
      }
    }
    if (source[i] === '$' && source[i + 1] && !/\s/.test(source[i + 1])) {
      let end = i + 1;
      while ((end = source.indexOf('$', end + 1)) !== -1) {
        if (source[end - 1] === '\\') continue;
        if (!/\s/.test(source[end - 1]) && !/\d/.test(source[end + 1] || '')) break;
      }
      if (end !== -1) {
        flush();
        parts.push({ type: 'inline', value: source.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    plain += source[i];
    i += 1;
  }
  flush();
  return parts;
}

let loading = null;
const loadKatex = () => {
  loading = loading || Promise.all([import('katex'), import('katex/dist/katex.min.css')]).then(([module]) => module.default || module);
  return loading;
};

// Safe options: no \href, \url or other commands that reach outside the text, and limits against runaway macros
const OPTIONS = { throwOnError: false, trust: false, strict: 'ignore', maxSize: 20, maxExpand: 200 };

function MathPart({ tex, display }) {
  const [katex, setKatex] = useState(null);
  const [failed, setFailed] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    let live = true;
    loadKatex().then((k) => live && setKatex(() => k)).catch(() => live && setFailed(true));
    return () => { live = false; };
  }, []);
  // KaTeX draws into an element React leaves empty, so the two never fight over its children
  useLayoutEffect(() => {
    if (!katex || !box.current) return;
    try {
      katex.render(tex, box.current, { ...OPTIONS, displayMode: display });
    } catch {
      setFailed(true);
    }
  }, [katex, tex, display]);
  if (failed || !katex) return <span className="font-mono text-[0.95em]">{display ? `$$${tex}$$` : `$${tex}$`}</span>;
  return <span ref={box} className={cx(display && 'my-2 block overflow-x-auto overflow-y-hidden')} />;
}

// Text with its math drawn; text without math comes back as it is, with no extra work
export default function MathText({ text }) {
  const parts = splitMath(text);
  if (parts.length === 0) return null;
  if (parts.length === 1 && parts[0].type === 'text') return parts[0].value;
  return parts.map((part, i) => (part.type === 'text'
    ? <React.Fragment key={i}>{part.value}</React.Fragment>
    : <MathPart key={i} tex={part.value} display={part.type === 'display'} />));
}

export const hasMath = (text) => splitMath(text).some((part) => part.type !== 'text');
