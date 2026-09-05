import { useState } from 'react';
import { Link } from 'react-router-dom';
import { OutcomeBadge } from '@/components/triage/OutcomeBadge';
import { apiFetch } from '@/lib/utils';
import type { PubMedSweepResponse } from '@/types/triage';

/**
 * Literature monitoring — scheduled screening of published literature.
 *
 * Marketing authorisation holders must screen the literature for adverse
 * reactions involving their products. This page runs that sweep against PubMed
 * live via NCBI E-utilities: each new article is ingested as a source record,
 * triaged, and decided by the same rule set as any other channel.
 *
 * Articles already seen are skipped by content hash, so re-running a standing
 * query does not create duplicate work.
 */

/** Realistic standing queries a PV team would monitor. */
const PRESETS: { label: string; query: string }[] = [
  {
    label: 'Hepatotoxicity case reports',
    query: 'drug induced liver injury case report',
  },
  {
    label: 'Serious skin reactions',
    query: 'stevens johnson syndrome drug induced case report',
  },
  {
    label: 'Anaphylaxis',
    query: 'anaphylaxis drug adverse reaction case report',
  },
  {
    label: 'Cardiac adverse reactions',
    query: 'drug induced QT prolongation adverse reaction',
  },
];

export function LiteratureSweepPage() {
  const [query, setQuery] = useState(PRESETS[0].query);
  const [maxResults, setMaxResults] = useState(3);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PubMedSweepResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runSweep(e: React.FormEvent) {
    e.preventDefault();
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await apiFetch<PubMedSweepResponse>('/intake/literature/pubmed', {
        method: 'POST',
        body: JSON.stringify({ query, max_results: maxResults, triage: true }),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <header>
        <h1 className="text-2xl font-semibold text-gray-900">Literature Sweep</h1>
        <p className="mt-1 text-sm text-gray-600">
          Screen published literature for adverse reactions. Runs live against
          PubMed; every new article is ingested and triaged automatically.
        </p>
      </header>

      <form onSubmit={runSweep} className="mt-5 card">
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-gray-500">Standing queries:</span>
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => setQuery(preset.query)}
              className={`rounded border px-2 py-1 text-[11px] ${
                query === preset.query
                  ? 'border-primary-400 bg-primary-50 text-primary-700'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <label className="block">
          <span className="text-xs font-medium text-gray-700">
            PubMed search expression
          </span>
          <input
            className="input mt-1"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. drug induced liver injury case report"
          />
        </label>

        <label className="mt-3 block">
          <span className="text-xs font-medium text-gray-700">
            Articles to retrieve: <strong>{maxResults}</strong>
          </span>
          <input
            type="range"
            min={1}
            max={10}
            value={maxResults}
            onChange={(e) => setMaxResults(Number(e.target.value))}
            className="mt-1 w-full max-w-sm"
          />
          <span className="mt-0.5 block text-[11px] text-gray-400">
            Each article is one model call, so larger sweeps take longer.
          </span>
        </label>

        <button
          type="submit"
          disabled={running || !query.trim()}
          className="btn-primary mt-4"
        >
          {running ? 'Sweeping and triaging…' : 'Run sweep'}
        </button>
      </form>

      {running && (
        <p className="mt-4 text-sm text-gray-600">
          Searching PubMed, then triaging each article. This can take a few
          seconds per article.
        </p>
      )}

      {error && (
        <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800 ring-1 ring-inset ring-red-600/20">
          <p className="font-medium">Sweep failed</p>
          <p className="mt-1">{error}</p>
          <p className="mt-2 text-xs">
            Connections to NCBI are retried automatically; a persistent failure
            usually means network egress to eutils.ncbi.nlm.nih.gov is blocked.
          </p>
        </div>
      )}

      {result && (
        <section className="mt-6">
          <h2 className="text-lg font-semibold text-gray-900">Sweep result</h2>
          <p className="mt-1 text-sm text-gray-600">{result.summary}</p>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <Metric label="Ingested" value={result.ingested} />
            <Metric label="Triaged" value={result.triaged} />
            <Metric
              label="Duplicates skipped"
              value={result.duplicates_skipped}
              hint="Already seen"
            />
          </div>

          {result.failures.length > 0 && (
            <div className="mt-3 rounded-md bg-amber-50 p-3 text-xs text-amber-900 ring-1 ring-inset ring-amber-600/20">
              <p className="font-medium">
                {result.failures.length} article(s) could not be triaged
              </p>
              <ul className="mt-1 list-inside list-disc">
                {result.failures.map((f) => (
                  <li key={f.source_record_id}>{f.error}</li>
                ))}
              </ul>
            </div>
          )}

          {result.results.length > 0 && (
            <ul className="mt-4 space-y-2">
              {result.results.map((item) => (
                <li
                  key={item.source_record_id}
                  className="rounded-lg border border-gray-200 bg-white p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <OutcomeBadge outcome={item.icsr_outcome} />
                    {item.triage?.seriousness_signal && (
                      <span className="badge bg-red-50 text-red-700">
                        seriousness signal
                      </span>
                    )}
                  </div>
                  {item.triage?.rationale && (
                    <p className="mt-2 text-xs italic text-gray-600">
                      {item.triage.rationale}
                    </p>
                  )}
                  {item.triage?.products_mentioned &&
                    item.triage.products_mentioned.length > 0 && (
                      <p className="mt-1.5 text-[11px] text-gray-500">
                        Products:{' '}
                        {item.triage.products_mentioned
                          .map((p) => p.verbatim)
                          .join(', ')}
                      </p>
                    )}
                </li>
              ))}
            </ul>
          )}

          <Link to="/inbox" className="btn-secondary mt-4 inline-flex">
            Review in the triage inbox →
          </Link>

          <p className="mt-4 text-xs leading-relaxed text-gray-500">
            Review articles and abstracts commonly resolve to{' '}
            <em>Not an ICSR</em>, which is correct: without an identifiable
            patient and reporter there is no individual case to report. Single
            case reports are the ones that tend to escalate.
          </p>
        </section>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-0.5 text-xl font-semibold text-gray-900">{value}</p>
      {hint && <p className="text-[11px] text-gray-400">{hint}</p>}
    </div>
  );
}
