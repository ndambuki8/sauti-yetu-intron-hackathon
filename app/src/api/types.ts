import type { NodeKind } from "../lib/palette";

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

export interface Artifact {
  id: string;
  created_at: string;
  command_text: string;
  intent: "report" | "flowchart" | "summary" | "clarify";
  title: string;
  body: string;
  notes: string;
  kind: "report" | "flowchart";
}

export interface AudioDetection {
  language_code: string;
  mms_code?: string | null;
  confidence?: number;
  error?: string;
}

export interface TextDetection {
  language_code: string;
  confidence?: number;
  source?: string;
}

export interface DetectionMeta {
  audio: AudioDetection | null;
  text: TextDetection | null;
  final: string;
}

export interface TriageResponse {
  transcript: string;
  transcript_patient: string;
  transcript_doctor: string;
  detected_language: string;
  detection: DetectionMeta | null;
  doctor_language: string;
  summary: string;
  duration_seconds: number | null;
  triage: TriageResult;
  session_id: string;
  graph: Graph;
  detected_languages: string[];
  artifacts: Artifact[];
}

export interface SessionResponse {
  session_id: string;
  graph: Graph;
  doctor_language: string;
  patient_language: string;
  detected_languages: string[];
  artifacts: Artifact[];
}

export interface CommandResponse {
  session_id: string;
  command_text: string;
  intent: Artifact["intent"];
  artifact: Artifact;
  artifacts: Artifact[];
}

export interface Phrase {
  english: string;
  translated: string;
  translation_error?: string;
}

export interface RespondResponse {
  original_text: string;
  translated_text: string;
  was_translated: boolean;
  english_fallback: boolean;
  audio_base64: string;
  audio_format: string;
}

export interface Turn {
  kind: "patient";
  index: number;
  timestamp: string;
  languageName: string;
  transcript: string;
  transcriptDoctor: string;
  detectedLanguage: string;
  summary: string;
  durationSeconds: number | null;
  triage: TriageResult;
  findings: string[];
  conditions: string[];
  redFlags: string[];
}

export interface WorkerReply {
  kind: "worker";
  timestamp: string;
  originalText: string;
  translatedText: string;
  englishFallback: boolean;
  audioUrl: string;
}

export type TimelineItem = Turn | WorkerReply;
