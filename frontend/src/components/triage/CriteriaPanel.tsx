import { CRITERION_LABELS, type CriterionName, type ICSRElements } from '@/types/triage';

/**
 * The four ICSR minimum criteria with the evidence behind each one.
 *
 * This is the "click any field, see the source sentence" beat: every criterion
 * the AI marked present shows the verbatim quote and its character offsets in
 * the source text, so a reviewer can verify rather than trust.
 */
export function CriteriaPanel({
  elements,
  onHighlight,
}: {
  elements?: ICSRElements | null;
  onHighlight?: (span: { char_start?: number | null; char_end?: number | null }) => void;
}) {
  if (!elements) {
    return <p className="text-sm text-gray-500">No triage result yet.</p>;
  }

  const names = Object.keys(CRITERION_LABELS) as CriterionName[];

  return (
    <ul className="space-y-2">
      {names.map((name) => {
        const element = elements[name];
        const span = element?.evidence_span;
        const present = Boolean(element?.present);

        return (
          <li
            key={name}
            className={`rounded-md border p-3 ${
              present ? 'border-green-200 bg-green-50/40' : 'border-gray-200 bg-gray-50'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-gray-900">
                {CRITERION_LABELS[name]}
              </span>
              <span
                className={
                  present
                    ? 'badge bg-green-100 text-green-800'
                    : 'badge bg-gray-200 text-gray-600'
                }
              >
                {present ? 'Present' : 'Absent'}
              </span>
            </div>

            {span?.quote ? (
              <button
                type="button"
                onClick={() => onHighlight?.(span.locator)}
                className="mt-2 w-full text-left"
                title="Show this quote in the source text"
              >
                <p className="border-l-2 border-green-400 pl-2 text-xs italic text-gray-700 hover:text-gray-900">
                  “{span.quote}”
                </p>
                {span.locator?.char_start != null && (
                  <p className="mt-1 pl-2 text-[10px] uppercase tracking-wide text-gray-400">
                    chars {span.locator.char_start}–{span.locator.char_end}
                  </p>
                )}
              </button>
            ) : (
              !present && (
                <p className="mt-1 text-xs text-gray-500">
                  Not found in the source text.
                </p>
              )
            )}
          </li>
        );
      })}
    </ul>
  );
}
