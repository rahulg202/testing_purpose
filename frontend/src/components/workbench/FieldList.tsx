import type { CaseData, ProvenancedField } from '@/types/case';

interface FieldListProps {
  caseData: CaseData;
  onFieldSelect: (path: string | null) => void;
  selectedFieldPath: string | null;
}

type FieldGroup = 'auto_accepted' | 'review_required' | 'unknown';

interface FieldEntry {
  path: string;
  label: string;
  value: string | null;
  group: FieldGroup;
  confidence: number | null;
  producedBy: string | null;
  reviewState: string | null;
}

function getFieldGroup(field: ProvenancedField | undefined): FieldGroup {
  if (!field) return 'unknown';
  if (field.review_state === 'accepted') return 'auto_accepted';
  if (field.review_state === 'escalated' || !field.value) return 'unknown';
  return 'review_required';
}

function extractFields(caseData: CaseData): FieldEntry[] {
  const fields: FieldEntry[] = [];

  // Patient fields
  if (caseData.patient) {
    const p = caseData.patient;
    if (p.age_at_onset) {
      fields.push({
        path: 'patient.age_at_onset',
        label: 'Patient Age',
        value: p.age_at_onset.value ? `${p.age_at_onset.value.value} ${p.age_at_onset.value.unit}` : null,
        group: getFieldGroup(p.age_at_onset),
        confidence: p.age_at_onset.confidence ?? null,
        producedBy: p.age_at_onset.produced_by ?? null,
        reviewState: p.age_at_onset.review_state ?? null,
      });
    }
    if (p.sex) {
      fields.push({
        path: 'patient.sex',
        label: 'Patient Sex',
        value: p.sex.value ?? null,
        group: getFieldGroup(p.sex),
        confidence: p.sex.confidence ?? null,
        producedBy: p.sex.produced_by ?? null,
        reviewState: p.sex.review_state ?? null,
      });
    }
  }

  // Drug fields
  caseData.drugs?.forEach((drug, i) => {
    fields.push({
      path: `drugs[${i}].product_name_verbatim`,
      label: `Drug ${i + 1}: Name`,
      value: drug.product_name_verbatim?.value ?? null,
      group: getFieldGroup(drug.product_name_verbatim),
      confidence: drug.product_name_verbatim?.confidence ?? null,
      producedBy: drug.product_name_verbatim?.produced_by ?? null,
      reviewState: drug.product_name_verbatim?.review_state ?? null,
    });
  });

  // Reaction fields
  caseData.reactions?.forEach((reaction, i) => {
    fields.push({
      path: `reactions[${i}].verbatim`,
      label: `Reaction ${i + 1}: Verbatim`,
      value: reaction.verbatim?.value ?? null,
      group: getFieldGroup(reaction.verbatim),
      confidence: reaction.verbatim?.confidence ?? null,
      producedBy: reaction.verbatim?.produced_by ?? null,
      reviewState: reaction.verbatim?.review_state ?? null,
    });
    if (reaction.coded_pt) {
      fields.push({
        path: `reactions[${i}].coded_pt`,
        label: `Reaction ${i + 1}: PT`,
        value: reaction.coded_pt.value ? `${reaction.coded_pt.value.term} (${reaction.coded_pt.value.code})` : null,
        group: getFieldGroup(reaction.coded_pt),
        confidence: reaction.coded_pt.confidence ?? null,
        producedBy: reaction.coded_pt.produced_by ?? null,
        reviewState: reaction.coded_pt.review_state ?? null,
      });
    }
    if (reaction.is_serious) {
      fields.push({
        path: `reactions[${i}].is_serious`,
        label: `Reaction ${i + 1}: Serious`,
        value: reaction.is_serious.value != null ? String(reaction.is_serious.value) : null,
        group: getFieldGroup(reaction.is_serious),
        confidence: reaction.is_serious.confidence ?? null,
        producedBy: reaction.is_serious.produced_by ?? null,
        reviewState: reaction.is_serious.review_state ?? null,
      });
    }
  });

  // Reporter
  caseData.reporters?.forEach((reporter, i) => {
    fields.push({
      path: `reporters[${i}]`,
      label: `Reporter ${i + 1}`,
      value: reporter.value ? `${reporter.value.qualification || 'Unknown'} (${reporter.value.country || '?'})` : null,
      group: getFieldGroup(reporter),
      confidence: reporter.confidence ?? null,
      producedBy: reporter.produced_by ?? null,
      reviewState: reporter.review_state ?? null,
    });
  });

  return fields;
}

function FieldCard({
  field,
  isSelected,
  onSelect,
}: {
  field: FieldEntry;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left rounded-md border p-3 transition-all ${
        isSelected
          ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200'
          : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500">{field.label}</span>
        <div className="flex items-center gap-1.5">
          {field.producedBy && (
            <span className={`badge text-[10px] ${
              field.producedBy === 'ai' ? 'bg-purple-50 text-purple-700' :
              field.producedBy === 'rule' ? 'bg-blue-50 text-blue-700' :
              field.producedBy === 'human' ? 'bg-green-50 text-green-700' :
              'bg-gray-50 text-gray-700'
            }`}>
              {field.producedBy}
            </span>
          )}
          {field.confidence != null && (
            <span className="text-[10px] text-gray-400">
              {Math.round(field.confidence * 100)}%
            </span>
          )}
        </div>
      </div>
      <p className="mt-1 text-sm font-medium text-gray-900 truncate">
        {field.value || <span className="text-gray-400 italic">—</span>}
      </p>
    </button>
  );
}

export function FieldList({ caseData, onFieldSelect, selectedFieldPath }: FieldListProps) {
  const fields = extractFields(caseData);

  const autoAccepted = fields.filter((f) => f.group === 'auto_accepted');
  const reviewRequired = fields.filter((f) => f.group === 'review_required');
  const unknown = fields.filter((f) => f.group === 'unknown');

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
            Case Fields
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {caseData.case_number} v{caseData.version}
          </p>
        </div>
        <span className={`badge ${
          caseData.lifecycle_state === 'approved' ? 'badge-success' :
          caseData.lifecycle_state === 'review_required' ? 'badge-warning' :
          'badge-info'
        }`}>
          {caseData.lifecycle_state}
        </span>
      </div>

      {/* Review required — shown first, these need attention */}
      {reviewRequired.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-yellow-700 uppercase tracking-wide mb-2 flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-yellow-400" />
            Review Required ({reviewRequired.length})
          </h3>
          <div className="space-y-2">
            {reviewRequired.map((field) => (
              <FieldCard
                key={field.path}
                field={field}
                isSelected={selectedFieldPath === field.path}
                onSelect={() => onFieldSelect(field.path)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Unknown / escalated */}
      {unknown.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-red-700 uppercase tracking-wide mb-2 flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-red-400" />
            Unknown / Escalated ({unknown.length})
          </h3>
          <div className="space-y-2">
            {unknown.map((field) => (
              <FieldCard
                key={field.path}
                field={field}
                isSelected={selectedFieldPath === field.path}
                onSelect={() => onFieldSelect(field.path)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Auto-accepted — collapsed by default */}
      {autoAccepted.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-medium text-green-700 uppercase tracking-wide flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-green-400" />
            Auto-Accepted ({autoAccepted.length})
            <span className="ml-1 text-gray-400 group-open:rotate-90 transition-transform">▶</span>
          </summary>
          <div className="mt-2 space-y-2">
            {autoAccepted.map((field) => (
              <FieldCard
                key={field.path}
                field={field}
                isSelected={selectedFieldPath === field.path}
                onSelect={() => onFieldSelect(field.path)}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
