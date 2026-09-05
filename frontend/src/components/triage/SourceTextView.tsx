import { useEffect, useRef } from 'react';
import type { Locator } from '@/types/triage';

/**
 * The source text with the selected evidence span highlighted.
 *
 * Highlighting works off character offsets recorded at triage time, which is
 * why the backend locates every quote in the stored text rather than trusting
 * the model to report positions.
 */
export function SourceTextView({
  text,
  highlight,
}: {
  text?: string | null;
  highlight?: Locator | null;
}) {
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [highlight]);

  if (!text) {
    return <p className="text-sm text-gray-500">No source text stored.</p>;
  }

  const start = highlight?.char_start;
  const end = highlight?.char_end;
  const hasRange =
    typeof start === 'number' &&
    typeof end === 'number' &&
    start >= 0 &&
    end > start &&
    start < text.length;

  if (!hasRange) {
    return (
      <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-gray-800">
        {text}
      </pre>
    );
  }

  return (
    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-gray-800">
      {text.slice(0, start)}
      <mark
        ref={markRef}
        className="rounded bg-yellow-200 px-0.5 text-gray-900 ring-1 ring-yellow-400"
      >
        {text.slice(start, Math.min(end, text.length))}
      </mark>
      {text.slice(Math.min(end, text.length))}
    </pre>
  );
}
