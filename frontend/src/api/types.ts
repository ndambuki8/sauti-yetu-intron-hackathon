import type { NodeKind } from "../lib/palette";

/** Mirrors the backend JSON contracts exactly (backend/app.py responses). */

export interface IntakeCard {
  patient_language: string;
  presenting_complaint: string;
  key_findings: string;
  possible_conditions: string;
  red_flags: string;
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
}

export interface GraphNode {
  data: { id: string; label: string; kind: NodeKind; turn: number };
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
  rtf?: number | null;
  audio_duration_seconds?: number | null;
  switch_point?: {
    wer: number | null;
    count: number;
    windows: Array<{ token_index: number; wer: number | null }>;
  };
  agentic?: {
    intent_correct: boolean | null;
    slot_accuracy: number | null;
    entity_error_rate: number | null;
  };
  warning?: string | null;
  error?: string;
}

export interface BenchmarkResponse {
  results: BenchmarkResult[];
  best_model: string | null;
  language_code?: string;
  switch_points?: Array<Record<string, unknown>>;
  agentic?: boolean;
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
