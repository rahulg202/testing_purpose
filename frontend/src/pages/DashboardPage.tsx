import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { OutcomeBadge } from '@/components/triage/OutcomeBadge';
import { apiFetch, formatDate, humanise } from '@/lib/utils';
import type { InboxItem, InboxStats } from '@/types/triage';

interface HealthStatus {
  status: string;
  service: string;
  version: string;
  environment: string;
}

/**
 * Operational overview of the triage pipeline.
 *
 * Every figure here is read from the API rather than being illustrative, so an
 * empty platform correctly shows zeros and a populated one shows real counts.
 */
export function DashboardPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [stats, setStats] = useState<InboxStats | null>(null);
  const [recent, setRecent] = useState<InboxItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [healthRes, statsRes, items] = await Promise.all([
        apiFetch<HealthStatus>('/health'),
        apiFetch<InboxStats>('/inbox/stats'),
        apiFetch<InboxItem[]>('/inbox?limit=5'),
      ]);
      setHealth(healthRes);
      setStats(statsRes);
      setRecent(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const valid = stats?.by_outcome.valid_icsr ?? 0;
  const escalated = stats?.awaiting_review ?? 0;
  const nonIcsr = stats?.by_outcome.non_icsr ?? 0;
  const noise = stats?.by_status.noise ?? 0;
  const errored = stats?.by_status.error ?? 0;

  return (
    <div className="p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-600">
            ICSR identification across all intake channels.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/report" className="btn-primary">
            New report
          </Link>
          <button type="button" onClick={() => void load()} className="btn-secondary">
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800 ring-1 ring-inset ring-red-600/20">
          {error}
        </p>
      )}

      {/* --- Headline figures --- */}
      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <Stat
          label="Records received"
          value={stats?.total ?? 0}
          tone="text-gray-900"
          hint="All channels"
        />
        <Stat
          label="Valid ICSR"
          value={valid}
          tone="text-green-700"
          hint="All 4 criteria met"
        />
        <Stat
          label="Awaiting review"
          value={escalated}
          tone="text-amber-700"
          hint="Escalated, not guessed"
        />
        <Stat
          label="Not an ICSR"
          value={nonIcsr}
          tone="text-gray-500"
          hint="No reportable signal"
        />
        <Stat
          label="Pending triage"
          value={stats?.untriaged ?? 0}
          tone="text-blue-700"
          hint="Not yet processed"
        />
      </div>

      {(noise > 0 || errored > 0) && (
        <div className="mt-3 flex gap-3 text-xs text-gray-500">
          {noise > 0 && <span>{noise} discarded as noise</span>}
          {errored > 0 && (
            <span className="text-red-600">{errored} failed triage — see inbox</span>
          )}
        </div>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* --- Recent activity --- */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Latest records
            </h2>
            <Link to="/inbox" className="text-xs text-primary-600 underline">
              View all
            </Link>
          </div>

          {recent.length === 0 ? (
            <div className="card text-center">
              <p className="text-sm font-medium text-gray-900">No records yet</p>
              <p className="mt-1 text-sm text-gray-500">
                Submit a report or run a literature sweep to see the engine work.
              </p>
              <div className="mt-3 flex justify-center gap-2">
                <Link to="/report" className="btn-primary text-xs">
                  Report an event
                </Link>
                <Link to="/literature" className="btn-secondary text-xs">
                  Literature sweep
                </Link>
              </div>
            </div>
          ) : (
            <ul className="space-y-2">
              {recent.map((item) => (
                <li key={item.source_record_id}>
                  <Link
                    to="/inbox"
                    className="block rounded-lg border border-gray-200 bg-white p-3 hover:bg-gray-50"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-gray-500">
                        {humanise(item.channel)}
                      </span>
                      <OutcomeBadge outcome={item.icsr_outcome} />
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-sm text-gray-800">
                      {item.snippet || '(no text)'}
                    </p>
                    <p className="mt-1.5 text-[11px] text-gray-400">
                      {item.criteria_met_count}/4 criteria ·{' '}
                      {formatDate(item.awareness_datetime)}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* --- Platform state --- */}
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Platform
          </h2>
          <div className="card">
            {health ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="badge-success">{health.status}</span>
                  <span className="text-sm text-gray-600">v{health.version}</span>
                </div>
                <dl className="grid grid-cols-2 gap-1 text-sm">
                  <dt className="text-gray-500">Service</dt>
                  <dd className="font-medium">{health.service}</dd>
                  <dt className="text-gray-500">Environment</dt>
                  <dd className="font-medium">{health.environment}</dd>
                </dl>
              </div>
            ) : error ? (
              <span className="badge-error">Disconnected</span>
            ) : (
              <div className="h-4 w-32 animate-pulse rounded bg-gray-200" />
            )}

            <div className="mt-4 border-t border-gray-100 pt-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                Decision authority
              </h3>
              <p className="mt-1.5 text-xs leading-relaxed text-gray-600">
                The model reports what each source says. Rule{' '}
                <code className="rounded bg-gray-100 px-1">val_001 v1.0.0</code>{' '}
                decides ICSR validity. Incomplete reports are escalated, never
                guessed.
              </p>
              <Link
                to="/inbox"
                className="mt-2 inline-block text-xs text-primary-600 underline"
              >
                Inspect decisions and evidence →
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: number;
  tone: string;
  hint?: string;
}) {
  return (
    <div className="card">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-0.5 text-2xl font-semibold ${tone}`}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-gray-400">{hint}</p>}
    </div>
  );
}
