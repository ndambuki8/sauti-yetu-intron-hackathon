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
  error?: string;
}

export interface BenchmarkResponse {
  results: BenchmarkResult[];
  best_model: string | null;
}

/** One recording's worth of conversation, derived client-side from a
 * TriageResponse and kept in consultation state for the timeline. */
export interface Turn {
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
