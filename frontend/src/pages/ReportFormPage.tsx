import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CriteriaPanel } from '@/components/triage/CriteriaPanel';
import { OutcomeBadge } from '@/components/triage/OutcomeBadge';
import { RuleTracePanel } from '@/components/triage/RuleTracePanel';
import { apiFetch } from '@/lib/utils';
import type { TriageResponse } from '@/types/triage';

/**
 * Public-facing adverse event report form.
 *
 * This is the reporter's view: a physician, pharmacist, or patient fills it in
 * and submits. On submission the triage engine runs immediately — the model
 * reads the report, then rule val_001 decides whether it constitutes a valid
 * ICSR — and the determination is shown back on this page.
 *
 * Every field except the narrative is optional on purpose. Incomplete reports
 * are exactly what the validity rule exists to classify, so the form must
 * accept them rather than blocking submission.
 */

interface FormState {
  reporter_name: string;
  reporter_qualification: string;
  reporter_email: string;
  reporter_country: string;
  patient_initials: string;
  patient_age: string;
  patient_sex: string;
  product_name: string;
  dose: string;
  event_description: string;
  onset_date: string;
  narrative: string;
}

const EMPTY: FormState = {
  reporter_name: '',
  reporter_qualification: '',
  reporter_email: '',
  reporter_country: '',
  patient_initials: '',
  patient_age: '',
  patient_sex: '',
  product_name: '',
  dose: '',
  event_description: '',
  onset_date: '',
  narrative: '',
};

/** Pre-filled examples so the three outcomes can be demonstrated quickly. */
const EXAMPLES: { label: string; hint: string; data: Partial<FormState> }[] = [
  {
    label: 'Complete report',
    hint: 'expect: Valid ICSR',
    data: {
      reporter_name: 'Dr. Anita Sharma',
      reporter_qualification: 'physician',
      reporter_email: 'a.sharma@example-hospital.in',
      reporter_country: 'IN',
      patient_initials: 'R.K.',
      patient_age: '54 years',
      patient_sex: 'female',
      product_name: 'Atherex 100mg',
      dose: '100mg once daily',
      event_description: 'Severe itchy rash across the torso',
      onset_date: '2026-08-28',
      narrative:
        'My patient was prescribed Atherex 100mg once daily for hypertension. Eight days later she developed a severe itchy rash across her torso and was admitted overnight for observation. The drug was withdrawn and the rash began to settle.',
    },
  },
  {
    label: 'Incomplete report',
    hint: 'expect: Escalated',
    data: {
      product_name: 'Atherex',
      event_description: 'stomach bleeding',
      narrative:
        'I read online that people are getting bad stomach bleeding from Atherex. I do not have details of who was affected.',
    },
  },
  {
    label: 'Enquiry only',
    hint: 'expect: Not an ICSR',
    data: {
      reporter_qualification: 'pharmacist',
      product_name: 'Atherex 100mg',
      narrative:
        'Can Atherex 100mg tablets be split in half for easier swallowing? No patient has experienced any problem.',
    },
  },
];

export function ReportFormPage() {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<TriageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function loadExample(data: Partial<FormState>) {
    setForm({ ...EMPTY, ...data });
    setResult(null);
    setError(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    // Send only populated fields: a blank field must not be transmitted as a
    // positive assertion that the information is absent.
    const payload: Record<string, unknown> = { triage: true };
    for (const [key, value] of Object.entries(form)) {
      if (value.trim()) payload[key] = value.trim();
    }

    try {
      const res = await apiFetch<TriageResponse>('/intake/web-form', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <header>
        <h1 className="text-2xl font-semibold text-gray-900">
          Report an adverse event
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          Submit a suspected adverse reaction. Only the description is required —
          send whatever you have. The triage engine runs the moment you submit.
        </p>
      </header>

      {/* Example loaders — demo convenience, not part of a real public form. */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-gray-500">Load an example:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.label}
            type="button"
            onClick={() => loadExample(ex.data)}
            className="rounded border border-gray-300 px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50"
            title={ex.hint}
          >
            {ex.label}
            <span className="ml-1 text-gray-400">({ex.hint})</span>
          </button>
        ))}
        <button
          type="button"
          onClick={() => loadExample({})}
          className="rounded border border-gray-300 px-2 py-1 text-[11px] text-gray-500 hover:bg-gray-50"
        >
          Clear
        </button>
      </div>

      <form onSubmit={submit} className="mt-5 space-y-4">
        <Section title="About you" subtitle="The reporter">
          <Field label="Full name">
            <input
              className="input"
              value={form.reporter_name}
              onChange={(e) => set('reporter_name', e.target.value)}
              placeholder="Dr. Anita Sharma"
            />
          </Field>
          <Field label="You are a">
            <select
              className="input"
              value={form.reporter_qualification}
              onChange={(e) => set('reporter_qualification', e.target.value)}
            >
              <option value="">Select…</option>
              <option value="physician">Physician</option>
              <option value="pharmacist">Pharmacist</option>
              <option value="nurse">Nurse</option>
              <option value="patient">Patient</option>
              <option value="consumer">Consumer / carer</option>
              <option value="other health professional">Other health professional</option>
            </select>
          </Field>
          <Field label="Email">
            <input
              type="email"
              className="input"
              value={form.reporter_email}
              onChange={(e) => set('reporter_email', e.target.value)}
              placeholder="you@example.com"
            />
          </Field>
          <Field label="Country">
            <input
              className="input"
              value={form.reporter_country}
              onChange={(e) => set('reporter_country', e.target.value)}
              placeholder="IN"
            />
          </Field>
        </Section>

        <Section title="About the patient" subtitle="Leave blank if not known">
          <Field label="Initials">
            <input
              className="input"
              value={form.patient_initials}
              onChange={(e) => set('patient_initials', e.target.value)}
              placeholder="R.K."
            />
          </Field>
          <Field label="Age">
            <input
              className="input"
              value={form.patient_age}
              onChange={(e) => set('patient_age', e.target.value)}
              placeholder="54 years"
            />
          </Field>
          <Field label="Sex">
            <select
              className="input"
              value={form.patient_sex}
              onChange={(e) => set('patient_sex', e.target.value)}
            >
              <option value="">Select…</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="unknown">Unknown</option>
            </select>
          </Field>
        </Section>

        <Section title="The medicine">
          <Field label="Product name">
            <input
              className="input"
              value={form.product_name}
              onChange={(e) => set('product_name', e.target.value)}
              placeholder="Atherex 100mg"
            />
          </Field>
          <Field label="Dose">
            <input
              className="input"
              value={form.dose}
              onChange={(e) => set('dose', e.target.value)}
              placeholder="100mg once daily"
            />
          </Field>
        </Section>

        <Section title="What happened">
          <Field label="Reaction / event">
            <input
              className="input"
              value={form.event_description}
              onChange={(e) => set('event_description', e.target.value)}
              placeholder="Severe itchy rash"
            />
          </Field>
          <Field label="When did it start">
            <input
              type="date"
              className="input"
              value={form.onset_date}
              onChange={(e) => set('onset_date', e.target.value)}
            />
          </Field>
        </Section>

        <div className="card">
          <label className="block">
            <span className="text-sm font-medium text-gray-900">
              Description <span className="text-red-600">*</span>
            </span>
            <span className="mt-0.5 block text-xs text-gray-500">
              Describe what happened in your own words.
            </span>
            <textarea
              required
              rows={6}
              className="input mt-2"
              value={form.narrative}
              onChange={(e) => set('narrative', e.target.value)}
              placeholder="My patient was prescribed… and then developed…"
            />
          </label>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={submitting || !form.narrative.trim()}
            className="btn-primary"
          >
            {submitting ? 'Running triage…' : 'Submit report'}
          </button>
          <Link to="/inbox" className="text-sm text-primary-600 underline">
            View the triage inbox
          </Link>
        </div>
      </form>

      {error && (
        <p className="mt-5 rounded-md bg-red-50 p-3 text-sm text-red-800 ring-1 ring-inset ring-red-600/20">
          {error}
        </p>
      )}

      {/* --- What the engine decided --- */}
      {result && (
        <section className="mt-8 border-t border-gray-200 pt-6">
          <h2 className="text-lg font-semibold text-gray-900">
            Triage complete
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            The report was stored, read by the model, and decided by the rules
            engine. Reference{' '}
            <code className="rounded bg-gray-100 px-1 text-xs">
              {result.source_record_id}
            </code>
            .
          </p>

          <div className="mt-4 space-y-4">
            <div className="card">
              <div className="flex flex-wrap items-center gap-3">
                <OutcomeBadge outcome={result.icsr_outcome} />
                {result.triage?.seriousness_signal && (
                  <span className="badge bg-red-50 text-red-700">
                    seriousness signal
                  </span>
                )}
                <span className="text-xs text-gray-500">
                  read by {result.triage?.model_id} ·{' '}
                  {result.triage?.prompt_version}
                </span>
              </div>
              {result.triage?.rationale && (
                <p className="mt-3 rounded-md bg-blue-50/60 p-2 text-xs italic text-gray-700">
                  Model’s reading: {result.triage.rationale}
                </p>
              )}
            </div>

            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-900">
                ICSR minimum criteria
              </h3>
              <CriteriaPanel elements={result.triage?.icsr_elements} />
            </div>

            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-900">
                Rule decision
              </h3>
              <RuleTracePanel trace={result.rule_trace} />
            </div>

            <Link to="/inbox" className="btn-secondary inline-flex">
              Open in the triage inbox →
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="card">
      <legend className="px-1 text-sm font-semibold text-gray-900">
        {title}
        {subtitle && (
          <span className="ml-2 font-normal text-gray-500">— {subtitle}</span>
        )}
      </legend>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-gray-700">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
