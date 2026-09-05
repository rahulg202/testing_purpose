import { cn } from '@/lib/utils';
import { OUTCOME_LABELS, type ICSROutcome } from '@/types/triage';

/**
 * The headline determination. Colour carries meaning:
 * green = valid ICSR, amber = escalated for human review, grey = not an ICSR.
 */
export function OutcomeBadge({
  outcome,
  className,
}: {
  outcome?: ICSROutcome | null;
  className?: string;
}) {
  if (!outcome) {
    return (
      <span className={cn('badge bg-gray-100 text-gray-600', className)}>
        Not triaged
      </span>
    );
  }

  const styles: Record<ICSROutcome, string> = {
    valid_icsr: 'bg-green-50 text-green-700 ring-1 ring-inset ring-green-600/20',
    potential_icsr: 'bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/30',
    non_icsr: 'bg-gray-100 text-gray-600 ring-1 ring-inset ring-gray-400/20',
  };

  return (
    <span className={cn('badge', styles[outcome], className)}>
      {OUTCOME_LABELS[outcome]}
    </span>
  );
}
