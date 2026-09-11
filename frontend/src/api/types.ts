import type { NodeKind } from "../lib/palette";

/** Mirrors the backend JSON contracts exactly (backend/app.py responses). */

export interface IntakeCard {
  patient_language: string;
  /** "34 yrs · Female" style summary, empty when unknown. */
  patient_summary?: string;
  /** "HR 120 · SpO2 88%" style summary of entered vitals, empty when none. */
  vitals?: string;
  presenting_complaint: string;
  key_findings: string;
  possible_conditions: string;
  red_flags: string;
}

/** Optional patient facts that gate age/sex-conditional triage criteria and
 * the age-banded high-risk vital-sign checks. All strings (from inputs). */
export interface PatientInput {
  age: string; // free text, parsed to a number if numeric
  sex: string; // "" | "male" | "female"
  pregnant: boolean;
  hr: string;
  rr: string;
  temp: string;
  spo2: string;
  avpu: string; // "" | "A" | "V" | "P" | "U"
}

/** Where a clinical assertion came from — the explainability trail carried
 * from the knowledge base (backend/knowledge/triage_kb.yaml). */
export interface Provenance {
  ref: string;
  url: string | null;
  evidence_level: string;
  review_status: string;
  mapped_scale: string | null;
  topic_id?: string;
}

/** A matched acuity discriminator (WHO IITT / ETAT sign) with its citation. */
export interface Discriminator {
  id: string;
  label: string;
  category: string;
  keyword: string;
  source: Provenance;
  /** True for emergency-category signs (the clinical red flags). */
  is_red_flag: boolean;
}

/** How the urgency was derived: the most acute matched sign and its source. */
export interface Acuity {
  category: string;
  discriminator: string;
  source: Provenance;
}

/** A finding that shifted a condition's probability. */
export interface DifferentialFinding {
  finding: string;
  lr: number;
}

/** One ranked candidate condition in the probabilistic differential. */
export interface DifferentialItem {
  id: string;
  label: string;
  probability: number; // 0..1 posterior
  prior: number;
  department: string | null;
  contributing: DifferentialFinding[];
  source: Provenance;
}

export interface TriageResult {
  topic: string;
  other_possible_topics: string[];
  urgency: string;
  suggested_department: string;
  intake_card: IntakeCard;
  clarifying_questions: string[];
  matched_keywords: string[];
  intron_suggestions: string;
  /** Source behind the primary topic; null for the fallback hand-off. */
  topic_source: Provenance | null;
  /** Explains the derived urgency; null when no discriminator escalated it. */
  acuity: Acuity | null;
  /** Every acuity discriminator matched this turn, most acute first. */
  matched_discriminators: Discriminator[];
  /** Ranked probabilistic differential (naive-Bayes over the KB). */
  differential: DifferentialItem[];
  /** Which patient fields were auto-detected from the conversation (e.g.
   * ["age","sex"]) rather than entered by the clinician. */
  auto_detected?: string[];
}

export interface GraphNode {
  data: {
    id: string;
    label: string;
    kind: NodeKind;
    turn: number;
    /** Present on nodes that carry a citable source (topic, red flag). */
    source?: Provenance;
    /** 0..1 posterior, present on condition nodes from the differential. */
    probability?: number;
  };
}

export interface GraphEdge {
  data: {
    id: string;
    source: string;
    target: string;
    relation: string;
    turn: number;
  };
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  turns: number;
}

export interface TriageResponse {
  transcript: string;
  summary: string;
  duration_seconds: number | null;
  triage: TriageResult;
  session_id: string;
  graph: Graph;
}

export interface BenchmarkResult {
  model: string;
  kind: string;
  wer: number | null;
  cer: number | null;
  latency_seconds: number | null;
  transcript: string;
  error?: string;
}

export interface BenchmarkResponse {
  results: BenchmarkResult[];
  best_model: string | null;
}

/** One recording's worth of conversation, derived client-side from a
 * TriageResponse and kept in consultation state for the timeline. */
export interface Turn {
  kind: "patient";
  index: number;
  timestamp: string;
  languageName: string;
  transcript: string;
  summary: string;
  durationSeconds: number | null;
  triage: TriageResult;
  findings: string[];
  conditions: string[];
  redFlags: string[];
}

/** A quick-reply phrase from GET /api/phrases. */
export interface Phrase {
  english: string;
  translated: string;
  translation_error?: string;
}

/** POST /api/respond response: worker reply translated + synthesized. */
export interface RespondResponse {
  original_text: string;
  translated_text: string;
  was_translated: boolean;
  english_fallback: boolean;
  audio_base64: string;
  audio_format: string;
}

/** A worker reply spoken to the patient, kept in the timeline. */
export interface WorkerReply {
  kind: "worker";
  timestamp: string;
  originalText: string;
  translatedText: string;
  englishFallback: boolean;
  audioUrl: string;
}

export type TimelineItem = Turn | WorkerReply;
