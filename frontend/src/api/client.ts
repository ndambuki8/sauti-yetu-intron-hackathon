import type {
  BenchmarkResponse,
  Graph,
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

export async function runBenchmark(
  audio: File,
  referenceTranscript: string,
  languageCode: string,
): Promise<BenchmarkResponse> {
  const form = new FormData();
  form.append("audio", audio, audio.name);
  form.append("reference_transcript", referenceTranscript);
  form.append("language_code", languageCode);
  const res = await fetch("/api/benchmark", { method: "POST", body: form });
  return parseResponse<BenchmarkResponse>(res);
}

export type { Graph };
