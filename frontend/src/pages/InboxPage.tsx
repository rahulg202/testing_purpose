import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CriteriaPanel } from '@/components/triage/CriteriaPanel';
import { OutcomeBadge } from '@/components/triage/OutcomeBadge';
import { RuleTracePanel } from '@/components/triage/RuleTracePanel';
import { SourceTextView } from '@/components/triage/SourceTextView';
import { apiFetch, formatDate, humanise } from '@/lib/utils';
import type { InboxItem, InboxItemDetail, InboxStats, Locator } from '@/types/triage';

/**
 * Triage inbox — read-only review of triaged source records.
 *
 * This page does not ingest anything. Intake lives on its own pages
 * (/report for direct reports, /literature for literature sweeps) so the
 * reviewer's view stays a view.
 *
 * The rule trace shown here is recomputed server-side from the stored criteria
 * rather than re-invoking the model: the rule is deterministic, so replaying it
 * reproduces the original decision exactly and for free.
 */

const CHANNEL_ICONS: Record<string, string> = {
  web_form: '📝',
  literature_pubmed: '📚',
  email: '✉️',
};

export function InboxPage() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [stats, setStats] = useState<InboxStats | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<InboxItemDetail | null>(null);
  const [highlight, setHighlight] = useState<Locator | null>(null);
  const [outcomeFilter, setOutcomeFilter] = useState<string>('');
  const [channelFilter, setChannelFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const query = outcomeFilter ? `?outcome=${outcomeFilter}` : '';
      const [list, counts] = await Promise.all([
        apiFetch<InboxItem[]>(`/inbox${query}`),
        apiFetch<InboxStats>('/inbox/stats'),
      ]);
      setItems(list);
      setStats(counts);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [outcomeFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setHighlight(null);
    apiFetch<InboxItemDetail>(`/inbox/${selectedId}`)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [selectedId]);

  const visible = channelFilter
    ? items.filter((item) => item.channel === channelFilter)
    : items;

  const channels = Array.from(new Set(items.map((item) => item.channel))).sort();

  return (
    <div className="p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Triage Inbox</h1>
          <p className="mt-1 text-sm text-gray-600">
            Review ICSR determinations. The model reports what each source says;
            rule <code className="rounded bg-gray-100 px-1 text-xs">val_001</code>{' '}
            decides validity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/report" className="btn-secondary text-xs">
            + Report an event
          </Link>
          <Link to="/literature" className="btn-secondary text-xs">
            + Literature sweep
          </Link>
          <button type="button" onClick={() => void refresh()} className="btn-secondary">
            Refresh
          </button>
        </div>
      </header>

      {stats && (
        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatCard label="Total records" value={stats.total} />
          <StatCard
            label="Valid ICSR"
            value={stats.by_outcome.valid_icsr ?? 0}
            tone="text-green-700"
          />
          <StatCard
            label="Escalated"
            value={stats.awaiting_review}
            tone="text-amber-700"
          />
          <StatCard
            label="Not ICSR"
            value={stats.by_outcome.non_icsr ?? 0}
            tone="text-gray-500"
          />
          <StatCard label="Pending triage" value={stats.untriaged} tone="text-blue-700" />
        </div>
      )}

      {error && (
        <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800 ring-1 ring-inset ring-red-600/20">
          {error}
        </p>
      )}

      <section className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* --- Queue --- */}
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Work queue ({visible.length})
            </h2>
            <div className="flex gap-1.5">
              <select
                value={channelFilter}
                onChange={(e) => setChannelFilter(e.target.value)}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs"
              >
                <option value="">All channels</option>
                {channels.map((channel) => (
                  <option key={channel} value={channel}>
                    {humanise(channel)}
                  </option>
                ))}
              </select>
              <select
                value={outcomeFilter}
                onChange={(e) => setOutcomeFilter(e.target.value)}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs"
              >
                <option value="">All outcomes</option>
                <option value="valid_icsr">Valid ICSR</option>
                <option value="potential_icsr">Escalated</option>
                <option value="non_icsr">Not an ICSR</option>
              </select>
            </div>
          </div>

          {loading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : visible.length === 0 ? (
            <div className="card text-center">
              <p className="text-sm font-medium text-gray-900">Nothing to review</p>
              <p className="mt-1 text-sm text-gray-500">
                Records appear here once they have been ingested and triaged.
              </p>
              <div className="mt-3 flex justify-center gap-2">
                <Link to="/report" className="btn-primary text-xs">
                  Report an event
                </Link>
                <Link to="/literature" className="btn-secondary text-xs">
                  Run a literature sweep
                </Link>
              </div>
            </div>
          ) : (
            <ul className="space-y-2">
              {visible.map((item) => {
                const isSelected = item.source_record_id === selectedId;
                return (
                  <li key={item.source_record_id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(item.source_record_id)}
                      className={`w-full rounded-lg border p-3 text-left transition-colors ${
                        isSelected
                          ? 'border-primary-400 bg-primary-50/60 ring-1 ring-primary-300'
                          : 'border-gray-200 bg-white hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 text-xs text-gray-500">
                          <span>{CHANNEL_ICONS[item.channel] ?? '📄'}</span>
                          {humanise(item.channel)}
                        </span>
                        <OutcomeBadge outcome={item.icsr_outcome} />
                      </div>

                      <p className="mt-2 line-clamp-2 text-sm text-gray-800">
                        {item.snippet || '(no text)'}
                      </p>

                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-gray-500">
                        <span>{item.criteria_met_count}/4 criteria</span>
                        <span>·</span>
                        <span>priority {item.priority_score?.toFixed?.(2) ?? '—'}</span>
                        {item.seriousness_signal && (
                          <span className="badge bg-red-50 text-red-700">
                            seriousness signal
                          </span>
                        )}
                        {item.status === 'received' && (
                          <span className="badge bg-blue-50 text-blue-700">
                            pending triage
                          </span>
                        )}
                        {item.status === 'error' && (
                          <span className="badge bg-red-100 text-red-800">error</span>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* --- Determination --- */}
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Determination
          </h2>

          {!detail ? (
            <div className="card text-center text-sm text-gray-500">
              Select a record to see the decision, its evidence, and the rule trace.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="card">
                <div className="flex flex-wrap items-center gap-2">
                  <OutcomeBadge outcome={detail.icsr_outcome} />
                  {detail.seriousness_signal && (
                    <span className="badge bg-red-50 text-red-700">
                      seriousness signal
                    </span>
                  )}
                </div>

                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                  <Meta label="Channel" value={humanise(detail.channel)} />
                  <Meta label="Status" value={humanise(detail.status)} />
                  <Meta label="Day 0" value={formatDate(detail.awareness_datetime)} />
                  <Meta
                    label="Patients"
                    value={detail.patient_count?.toString() ?? '—'}
                  />
                  <Meta label="Proposed by" value={detail.model_id ?? '—'} />
                  <Meta label="Prompt" value={detail.prompt_version ?? '—'} />
                  {detail.external_url && (
                    <div className="col-span-2">
                      <dt className="inline text-gray-500">Source: </dt>
                      <dd className="inline">
                        <a
                          href={detail.external_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-primary-600 underline"
                        >
                          {detail.external_id ?? detail.external_url}
                        </a>
                      </dd>
                    </div>
                  )}
                </dl>

                {detail.rationale && (
                  <p className="mt-3 rounded-md bg-blue-50/60 p-2 text-xs italic text-gray-700">
                    Model’s reading: {detail.rationale}
                  </p>
                )}

                {detail.error_message && (
                  <p className="mt-3 rounded-md bg-red-50 p-2 text-xs text-red-800">
                    {detail.error_type}: {detail.error_message}
                  </p>
                )}
              </div>

              <div className="card">
                <h3 className="mb-2 text-sm font-semibold text-gray-900">
                  ICSR minimum criteria
                </h3>
                <CriteriaPanel
                  elements={detail.triage?.icsr_elements}
                  onHighlight={setHighlight}
                />
              </div>

              <div className="card">
                <h3 className="mb-2 text-sm font-semibold text-gray-900">
                  Rule decision
                </h3>
                <RuleTracePanel trace={detail.rule_trace} />
              </div>

              <div className="card">
                <h3 className="mb-2 text-sm font-semibold text-gray-900">
                  Source text
                  <span className="ml-2 text-xs font-normal text-gray-500">
                    click a quote above to highlight
                  </span>
                </h3>
                <div className="max-h-80 overflow-auto rounded border border-gray-100 bg-gray-50/50 p-3">
                  <SourceTextView text={detail.raw_text} highlight={highlight} />
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  tone = 'text-gray-900',
}: {
  label: string;
  value: number;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`mt-0.5 text-xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="inline text-gray-500">{label}: </dt>
      <dd className="inline text-gray-800">{value}</dd>
    </div>
  );
}
