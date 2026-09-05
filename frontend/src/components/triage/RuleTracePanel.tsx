import type { RuleEvaluation } from '@/types/triage';

/**
 * The deterministic decision trace.
 *
 * This is the answer to "which rule decided this, and on what basis?" — the
 * question an inspector asks. It deliberately shows the rule ID, the rule-set
 * version, the exact inputs, and which sub-rules fired.
 */
export function RuleTracePanel({ trace }: { trace?: RuleEvaluation | null }) {
  if (!trace) {
    return (
      <p className="text-sm text-gray-500">
        No rule evaluation recorded — this record has not been triaged.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge bg-indigo-50 text-indigo-700 ring-1 ring-inset ring-indigo-600/20">
          Decided by rule
        </span>
        <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-800">
          {trace.rule_id} v{trace.rule_set_version}
        </code>
      </div>

      {trace.explanation && (
        <p className="rounded-md bg-gray-50 p-3 text-sm leading-relaxed text-gray-800">
          {trace.explanation}
        </p>
      )}

      {trace.fired_rules?.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Rules fired
          </h4>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {trace.fired_rules.map((rule) => (
              <li key={rule}>
                <code className="rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] text-indigo-700">
                  {rule}
                </code>
              </li>
            ))}
          </ul>
        </div>
      )}

      {trace.input_provenance && Object.keys(trace.input_provenance).length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Inputs and their basis
          </h4>
          <dl className="mt-1 space-y-1">
            {Object.entries(trace.input_provenance).map(([key, value]) => (
              <div key={key} className="text-xs">
                <dt className="inline font-medium text-gray-700">
                  {key.replace(/_/g, ' ')}:
                </dt>{' '}
                <dd className="inline text-gray-600">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
