import {
  createContext,
  useContext,
  useEffect,
  useReducer,
  type ReactNode,
} from "react";
import { getLanguages } from "../api/client";
import type {
  Artifact,
  RespondResponse,
  TimelineItem,
  TriageResponse,
  Turn,
  WorkerReply,
} from "../api/types";
import { splitExtraction, splitRedFlags } from "../lib/extraction";

interface ConsultationState {
  sessionId: string | null;
  turns: TimelineItem[];
  graph: TriageResponse["graph"] | null;
  analysing: boolean;
  commanding: boolean;
  error: string | null;
  languages: Record<string, string>;
  doctorLanguages: Record<string, string>;
  languageCode: string;
  doctorLanguage: string;
  artifacts: Artifact[];
  detectedLanguages: string[];
}

type Action =
  | {
      type: "languagesLoaded";
      languages: Record<string, string>;
      doctorLanguages: Record<string, string>;
    }
  | { type: "languageChanged"; languageCode: string }
  | { type: "doctorLanguageChanged"; doctorLanguage: string }
  | { type: "sessionStarted"; sessionId: string }
  | { type: "analysisStarted" }
  | { type: "turnAdded"; response: TriageResponse; languageName: string }
  | { type: "replyAdded"; reply: WorkerReply }
  | { type: "commandStarted" }
  | { type: "commandFinished"; artifacts: Artifact[] }
  | { type: "analysisFailed"; message: string }
  | { type: "reset" };

const initialState: ConsultationState = {
  sessionId: null,
  turns: [],
  graph: null,
  analysing: false,
  commanding: false,
  error: null,
  languages: {},
  doctorLanguages: { en: "English", fr: "French" },
  languageCode: "auto",
  doctorLanguage: "en",
  artifacts: [],
  detectedLanguages: [],
};

export function toWorkerReply(response: RespondResponse): WorkerReply {
  return {
    kind: "worker",
    timestamp: new Date().toISOString(),
    originalText: response.original_text,
    translatedText: response.translated_text,
    englishFallback: response.english_fallback,
    audioUrl: `data:audio/${response.audio_format};base64,${response.audio_base64}`,
  };
}

function toTurn(response: TriageResponse, languageName: string): Turn {
  return {
    kind: "patient",
    index: response.graph.turns,
    timestamp: new Date().toISOString(),
    languageName,
    transcript: response.transcript_patient || response.transcript,
    transcriptDoctor: response.transcript_doctor || response.transcript,
    detectedLanguage: response.detected_language,
    summary: response.summary,
    durationSeconds: response.duration_seconds,
    triage: response.triage,
    findings: splitExtraction(response.triage.intake_card.key_findings),
    conditions: splitExtraction(response.triage.intake_card.possible_conditions),
    redFlags: splitRedFlags(response.triage.intake_card.red_flags),
  };
}

function reducer(state: ConsultationState, action: Action): ConsultationState {
  switch (action.type) {
    case "languagesLoaded":
      return {
        ...state,
        languages: action.languages,
        doctorLanguages: action.doctorLanguages,
      };
    case "languageChanged":
      return { ...state, languageCode: action.languageCode };
    case "doctorLanguageChanged":
      return { ...state, doctorLanguage: action.doctorLanguage };
    case "sessionStarted":
      return { ...state, sessionId: action.sessionId };
    case "analysisStarted":
      return { ...state, analysing: true, error: null };
    case "turnAdded":
      return {
        ...state,
        analysing: false,
        sessionId: action.response.session_id,
        graph: action.response.graph,
        turns: [...state.turns, toTurn(action.response, action.languageName)],
        artifacts: action.response.artifacts ?? state.artifacts,
        detectedLanguages: action.response.detected_languages ?? state.detectedLanguages,
      };
    case "replyAdded":
      return { ...state, turns: [...state.turns, action.reply] };
    case "commandStarted":
      return { ...state, commanding: true, error: null };
    case "commandFinished":
      return { ...state, commanding: false, artifacts: action.artifacts };
    case "analysisFailed":
      return { ...state, analysing: false, commanding: false, error: action.message };
    case "reset":
      return {
        ...initialState,
        languages: state.languages,
        doctorLanguages: state.doctorLanguages,
        languageCode: state.languageCode,
        doctorLanguage: state.doctorLanguage,
      };
  }
}

const ConsultationContext = createContext<{
  state: ConsultationState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

export function ConsultationProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    getLanguages()
      .then(({ languages, doctorLanguages }) =>
        dispatch({ type: "languagesLoaded", languages, doctorLanguages }),
      )
      .catch(() => undefined);
  }, []);

  return (
    <ConsultationContext.Provider value={{ state, dispatch }}>
      {children}
    </ConsultationContext.Provider>
  );
}

export function useConsultation() {
  const ctx = useContext(ConsultationContext);
  if (!ctx) {
    throw new Error("useConsultation must be used inside ConsultationProvider");
  }
  return ctx;
}

export function latestTurn(state: ConsultationState): Turn | null {
  for (let i = state.turns.length - 1; i >= 0; i--) {
    const item = state.turns[i];
    if (item.kind === "patient") return item;
  }
  return null;
}
