/**
 * TypeScript types matching the atheria-contracts Pydantic models.
 *
 * These are hand-written for the MVP. Post-MVP: auto-generated from
 * JSON Schema using json-schema-to-typescript.
 */

export interface EvidenceSpan {
  source_record_id: string;
  evidence_ref: string;
  locator: {
    page?: number;
    bbox?: [number, number, number, number];
    char_start?: number;
    char_end?: number;
  };
  quote: string;
  quote_translated?: string;
}

export interface ProvenancedField<T = unknown> {
  value: T | null;
  produced_by: 'ai' | 'rule' | 'human' | 'import' | 'default';
  model_id?: string;
  prompt_version?: string;
  confidence?: number;
  rule_id?: string;
  rule_set_version?: string;
  evidence?: EvidenceSpan[];
  actor_id?: string;
  actor_action?: string;
  reason_code?: string;
  first_set_at: string;
  last_changed_at: string;
  review_state: 'proposed' | 'accepted' | 'edited' | 'rejected' | 'escalated';
}

export interface CodedTerm {
  code: string;
  term: string;
  dictionary: string;
  dictionary_version?: string;
}

export interface AgeValue {
  value: number;
  unit: string;
}

export interface Reporter {
  reporter_id?: string;
  qualification?: string;
  country?: string;
  is_primary: boolean;
}

export interface PatientBlock {
  patient_pii_token?: string;
  age_at_onset?: ProvenancedField<AgeValue>;
  age_group?: ProvenancedField<string>;
  sex?: ProvenancedField<string>;
  weight_kg?: ProvenancedField<number>;
  height_cm?: ProvenancedField<number>;
}

export interface DoseInfo {
  amount?: number;
  unit?: string;
  frequency?: string;
  route?: string;
}

export interface DrugBlock {
  drug_id: string;
  characterisation: ProvenancedField<string>;
  product_name_verbatim: ProvenancedField<string>;
  active_substances?: ProvenancedField<string>[];
  dose?: ProvenancedField<DoseInfo>;
  route?: ProvenancedField<string>;
  therapy_start?: ProvenancedField<{ year: number; month?: number; day?: number }>;
  therapy_end?: ProvenancedField<{ year: number; month?: number; day?: number }>;
  action_taken?: ProvenancedField<string>;
}

export interface SeriousnessFacts {
  resulted_in_death?: ProvenancedField<boolean>;
  life_threatening?: ProvenancedField<boolean>;
  required_hospitalisation?: ProvenancedField<boolean>;
  prolonged_hospitalisation?: ProvenancedField<boolean>;
  persistent_disability?: ProvenancedField<boolean>;
  congenital_anomaly?: ProvenancedField<boolean>;
  other_medically_important?: ProvenancedField<boolean>;
}

export interface RuleEvaluation {
  rule_id: string;
  rule_set_version: string;
  inputs: Record<string, unknown>;
  fired_rules: string[];
  explanation?: string;
  outcome?: string;
}

export interface ReactionBlock {
  reaction_id: string;
  verbatim: ProvenancedField<string>;
  verbatim_translated?: ProvenancedField<string>;
  coded_llt?: ProvenancedField<CodedTerm>;
  coded_pt?: ProvenancedField<CodedTerm>;
  onset_date?: ProvenancedField<{ year: number; month?: number; day?: number }>;
  outcome?: ProvenancedField<string>;
  serious_criteria_facts?: SeriousnessFacts;
  is_serious?: ProvenancedField<boolean>;
  seriousness_rule_trace?: RuleEvaluation;
}

export interface NarrativeBlock {
  text?: ProvenancedField<string>;
  coverage_check_passed?: boolean;
  coverage_gaps?: string[];
}

export interface CaseData {
  case_id: string;
  tenant_id: string;
  case_number: string;
  version: number;
  version_type: 'initial' | 'follow_up' | 'amendment' | 'nullification';
  lifecycle_state: string;
  lock_state: string;
  report_type?: ProvenancedField<string>;
  first_awareness_date?: ProvenancedField<string>;
  source_records: string[];
  reporters: ProvenancedField<Reporter>[];
  patient?: PatientBlock;
  drugs: DrugBlock[];
  reactions: ReactionBlock[];
  narrative?: NarrativeBlock;
  created_at: string;
  created_by: string;
  approved_at?: string;
  approved_by?: string;
}
