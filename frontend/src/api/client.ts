import type {
  BenchmarkResponse,
  Graph,
  Phrase,
  RespondResponse,
  TriageResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseResponse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
    throw new ApiError(detail, res.status);
  }
  return body as T;
}

export async function getLanguages(): Promise<Record<string, string>> {
  const res = await fetch("/api/languages");
  const body = await parseResponse<{ languages: Record<string, string> }>(res);
  return body.languages;
}

export async function createSession(): Promise<string> {
  const res = await fetch("/api/session", { method: "POST" });
  const body = await parseResponse<{ session_id: string }>(res);
  return body.session_id;
}

export async function deleteSession(sessionId: string): Promise<void> {
  // Best-effort cleanup; the backend store is in-memory anyway.
  await fetch(`/api/session/${sessionId}`, { method: "DELETE" }).catch(
    () => undefined,
  );
}

export async function runTriage(
  audio: Blob,
  filename: string,
  languageCode: string,
  sessionId: string,
): Promise<TriageResponse> {
  const form = new FormData();
  form.append("audio", audio, filename);
  form.append("language_code", languageCode);
  form.append("session_id", sessionId);
  const res = await fetch("/api/triage", { method: "POST", body: form });
  return parseResponse<TriageResponse>(res);
}

export async function getPhrases(languageCode: string): Promise<Phrase[]> {
  const res = await fetch(
    `/api/phrases?language_code=${encodeURIComponent(languageCode)}`,
  );
  const body = await parseResponse<{ phrases: Phrase[] }>(res);
  return body.phrases;
}

export async function respond(
  text: string,
  languageCode: string,
  voiceGender: "male" | "female",
): Promise<RespondResponse> {
  const res = await fetch("/api/respond", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      language_code: languageCode,
      voice_gender: voiceGender,
    }),
  });
  return parseResponse<RespondResponse>(res);
}

export async function runBenchmark(
  audio: Blob,
  filename: string,
  referenceTranscript: string,
  languageCode: string,
  options: {
    switchPoints?: Array<Record<string, unknown>>;
    agentReference?: Record<string, unknown>;
    expectedSlots?: Record<string, string>;
    agentic?: boolean;
  } = {},
): Promise<BenchmarkResponse> {
  const form = new FormData();
  form.append("audio", audio, filename);
  form.append("reference_transcript", referenceTranscript);
  form.append("language_code", languageCode);
  form.append("switch_points", JSON.stringify(options.switchPoints ?? []));
  form.append("agent_reference", JSON.stringify({
    ...(options.agentReference ?? {}),
    expected_slots: options.expectedSlots ?? {},
  }));
  form.append("agentic", String(options.agentic ?? false));
  const res = await fetch("/api/benchmark", { method: "POST", body: form });
  return parseResponse<BenchmarkResponse>(res);
}

export type { Graph };
