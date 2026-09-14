import { Platform } from "react-native";
import Constants from "expo-constants";
import { File } from "expo-file-system";
import { fetch as expoFetch } from "expo/fetch";
import type { Clip } from "../lib/audioTypes";
import type {
  CommandResponse,
  PatientInput,
  Phrase,
  RespondResponse,
  SessionResponse,
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

export function apiBase(): string {
  const env = process.env.EXPO_PUBLIC_API_URL;
  if (env) return env.replace(/\/$/, "");
  if (Platform.OS === "web") {
    if (typeof window !== "undefined" && window.location?.origin) {
      const origin = window.location.origin;
      if (/:(8081|8082|19006|8080)\b/.test(origin)) {
        return "http://localhost:8000";
      }
      return origin;
    }
    return "http://localhost:8000";
  }
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  return host ? `http://${host}:8000` : "http://localhost:8000";
}

function url(path: string): string {
  return `${apiBase()}${path}`;
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

export async function getLanguages(): Promise<{
  languages: Record<string, string>;
  doctorLanguages: Record<string, string>;
}> {
  const res = await fetch(url("/api/languages"));
  const body = await parseResponse<{
    languages: Record<string, string>;
    doctor_languages: Record<string, string>;
  }>(res);
  return {
    languages: body.languages,
    doctorLanguages: body.doctor_languages ?? { en: "English", fr: "French" },
  };
}

export async function createSession(
  doctorLanguage: string,
  patientLanguage: string,
): Promise<string> {
  const params = new URLSearchParams({
    doctor_language: doctorLanguage,
    patient_language: patientLanguage,
  });
  const res = await fetch(url(`/api/session?${params}`), { method: "POST" });
  const body = await parseResponse<{ session_id: string }>(res);
  return body.session_id;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(url(`/api/session/${sessionId}`), { method: "DELETE" }).catch(
    () => undefined,
  );
}

export async function getSession(sessionId: string): Promise<SessionResponse> {
  const res = await fetch(url(`/api/session/${sessionId}`));
  return parseResponse<SessionResponse>(res);
}

function appendAudio(form: FormData, audio: Clip) {
  if (Platform.OS === "web" && audio.blob) {
    form.append("audio", audio.blob, audio.filename);
    return;
  }
  // RN 0.76+ fetch rejects { uri, name, type } with
  // "unsupported FormDataPart implementation". Expo File is a real Blob.
  const file = new File(audio.uri);
  form.append("audio", file, audio.filename);
}

async function postForm(path: string, form: FormData): Promise<Response> {
  const target = url(path);
  if (Platform.OS === "web") {
    return fetch(target, { method: "POST", body: form });
  }
  return expoFetch(target, { method: "POST", body: form }) as unknown as Response;
}

function appendIfPresent(form: FormData, key: string, value: string | boolean | null | undefined) {
  if (value === null || value === undefined || value === "") return;
  form.append(key, String(value));
}

export async function runTriage(
  audio: Clip,
  languageCode: string,
  doctorLanguage: string,
  sessionId: string,
  patient?: PatientInput,
): Promise<TriageResponse> {
  const form = new FormData();
  appendAudio(form, audio);
  form.append("language_code", languageCode);
  form.append("doctor_language", doctorLanguage);
  form.append("session_id", sessionId);
  if (patient) {
    appendIfPresent(form, "age", patient.age);
    appendIfPresent(form, "sex", patient.sex);
    if (patient.pregnant !== null) form.append("pregnant", String(patient.pregnant));
    appendIfPresent(form, "hr", patient.hr);
    appendIfPresent(form, "rr", patient.rr);
    appendIfPresent(form, "temp", patient.temp);
    appendIfPresent(form, "spo2", patient.spo2);
    appendIfPresent(form, "avpu", patient.avpu);
  }
  const res = await postForm("/api/triage", form);
  return parseResponse<TriageResponse>(res);
}

export async function getPhrases(languageCode: string): Promise<Phrase[]> {
  const res = await fetch(
    url(`/api/phrases?language_code=${encodeURIComponent(languageCode)}`),
  );
  const body = await parseResponse<{ phrases: Phrase[] }>(res);
  return body.phrases;
}

export async function respond(
  text: string,
  languageCode: string,
  voiceGender: "male" | "female",
): Promise<RespondResponse> {
  const res = await fetch(url("/api/respond"), {
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

export async function runCommand(opts: {
  sessionId: string;
  text?: string;
  audio?: Clip;
}): Promise<CommandResponse> {
  const form = new FormData();
  form.append("session_id", opts.sessionId);
  if (opts.text) form.append("text", opts.text);
  if (opts.audio) appendAudio(form, opts.audio);
  const res = await postForm("/api/command", form);
  return parseResponse<CommandResponse>(res);
}
