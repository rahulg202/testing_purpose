/**
 * Types mirroring the backend triage contracts.
 * Source of truth: packages/atheria-contracts/atheria_contracts/source_record.py
 */

export type ICSROutcome = 'valid_icsr' | 'potential_icsr' | 'non_icsr';

export type SourceStatus =
  | 'received'
  | 'normalising'
  | 'triaging'
  | 'triaged'
  | 'case_created'
  | 'non_icsr'
  | 'noise'
  | 'error'
  | 'quarantined';

/** The four ICSR minimum criteria. */
export type CriterionName =
  | 'identifiable_patient'
  | 'identifiable_reporter'
  | 'suspect_product'
  | 'adverse_event';

export interface Locator {
  char_start?: number | null;
  char_end?: number | null;
  page?: number | null;
}

export interface EvidenceSpan {
  source_record_id: string;
  evidence_ref: string;
  locator: Locator;
  quote: string;
  quote_translated?: string | null;
}

export interface ICSRElement {
  present: boolean;
  evidence_span?: EvidenceSpan | null;
}

export interface ICSRElements {
  identifiable_patient: ICSRElement;
  identifiable_reporter: ICSRElement;
  suspect_product: ICSRElement;
  adverse_event: ICSRElement;
}

export interface Mention {
  verbatim: string;
  confidence: number;
  span?: EvidenceSpan | null;
}

export interface TriageResult {
  is_noise: boolean;
  noise_reason?: string | null;
  products_mentioned: Mention[];
  ae_candidates: Mention[];
  content_types: string[];
  patient_count: number;
  icsr_elements?: ICSRElements | null;
  icsr_outcome?: ICSROutcome | null;
  outcome_rule_id?: string | null;
  outcome_rule_version?: string | null;
  priority_score: number;
  seriousness_signal: boolean;
  model_id?: string | null;
  prompt_version?: string | null;
  rationale?: string | null;
}

/** The deterministic rule decision trace. */
export interface RuleEvaluation {
  rule_id: string;
  rule_set_version: string;
  inputs: Record<string, unknown>;
  input_provenance: Record<string, string>;
  fired_rules: string[];
  explanation?: string | null;
  outcome?: string | null;
}

/** A row in the triage inbox. */
export interface InboxItem {
  source_record_id: string;
  channel: string;
  channel_class: string;
  external_id?: string | null;
  external_url?: string | null;
  status: SourceStatus;
  awareness_datetime?: string | null;
  content_hash: string;
  snippet: string;
  icsr_outcome?: ICSROutcome | null;
  outcome_rule_id?: string | null;
  outcome_rule_version?: string | null;
  priority_score: number;
  seriousness_signal: boolean;
  content_types: string[];
  patient_count?: number | null;
  rationale?: string | null;
  model_id?: string | null;
  prompt_version?: string | null;
  criteria_present: Record<CriterionName, boolean>;
  criteria_met_count: number;
  is_noise: boolean;
  error_type?: string | null;
  error_message?: string | null;
}

/** Full detail for one record. */
export interface InboxItemDetail extends InboxItem {
  raw_text?: string | null;
  raw_language?: string | null;
  triage?: TriageResult | null;
  evidence_ref?: string | null;
  retrieved_at?: string | null;
  /**
   * Rule decision trace, recomputed server-side from the stored criteria.
   * Deterministic, so it matches the original decision without a model call.
   */
  rule_trace?: RuleEvaluation | null;
}

export interface InboxStats {
  total: number;
  by_status: Record<string, number>;
  by_outcome: Record<string, number>;
  awaiting_review: number;
  untriaged: number;
}

/** Response from an intake call that also ran triage. */
export interface TriageResponse {
  source_record_id: string;
  status: SourceStatus;
  icsr_outcome?: ICSROutcome | null;
  triage?: TriageResult;
  rule_trace?: RuleEvaluation;
  run_id?: string;
}

export interface PubMedSweepResponse {
  query: string;
  summary: string;
  ingested: number;
  duplicates_skipped: number;
  triaged: number;
  failures: { source_record_id: string; error: string }[];
  results: TriageResponse[];
}

export const CRITERION_LABELS: Record<CriterionName, string> = {
  identifiable_patient: 'Identifiable patient',
  identifiable_reporter: 'Identifiable reporter',
  suspect_product: 'Suspect product',
  adverse_event: 'Adverse event',
};

export const OUTCOME_LABELS: Record<ICSROutcome, string> = {
  valid_icsr: 'Valid ICSR',
  potential_icsr: 'Potential ICSR — escalated',
  non_icsr: 'Not an ICSR',
};
