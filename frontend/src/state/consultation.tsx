import {
  createContext,
  useContext,
  useEffect,
  useReducer,
  type ReactNode,
} from "react";
import { getLanguages } from "../api/client";
import type {
  Graph,
  PatientInput,
  RespondResponse,
  TimelineItem,
  TriageResponse,
  Turn,
  WorkerReply,
} from "../api/types";
import { splitExtraction, splitRedFlags } from "../lib/extraction";

export type Tab = "triage" | "benchmark";

interface ConsultationState {
  sessionId: string | null;
  turns: TimelineItem[];
  graph: Graph | null;
  analysing: boolean;
  error: string | null;
  tab: Tab;
  languages: Record<string, string>;
  languageCode: string;
  patient: PatientInput;
}

type Action =
  | { type: "languagesLoaded"; languages: Record<string, string> }
  | { type: "tabChanged"; tab: Tab }
  | { type: "languageChanged"; languageCode: string }
  | { type: "patientChanged"; patient: Partial<PatientInput> }
  | { type: "sessionStarted"; sessionId: string }
  | { type: "analysisStarted" }
  | { type: "turnAdded"; response: TriageResponse; languageName: string }
  | { type: "replyAdded"; reply: WorkerReply }
  | { type: "analysisFailed"; message: string }
  | { type: "reset" };

const initialState: ConsultationState = {
  sessionId: null,
  turns: [],
  graph: null,
  analysing: false,
  error: null,
  tab: "triage",
  languages: {},
  languageCode: "sw",
  patient: {
    age: "",
    sex: "",
    pregnant: false,
    hr: "",
    rr: "",
    temp: "",
    spo2: "",
    avpu: "",
  },
};

/** Build a timeline item from a spoken worker reply, decoding the audio
 * into an object URL the <audio> element can replay. */
export function toWorkerReply(response: RespondResponse): WorkerReply {
  const bytes = Uint8Array.from(atob(response.audio_base64), (c) =>
    c.charCodeAt(0),
  );
  const blob = new Blob([bytes], { type: `audio/${response.audio_format}` });
  return {
    kind: "worker",
    timestamp: new Date().toISOString(),
    originalText: response.original_text,
    translatedText: response.translated_text,
    englishFallback: response.english_fallback,
    audioUrl: URL.createObjectURL(blob),
  };
}

function toTurn(response: TriageResponse, languageName: string): Turn {
  return {
    kind: "patient",
    index: response.graph.turns,
    timestamp: new Date().toISOString(),
    languageName,
    transcript: response.transcript,
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
      return { ...state, languages: action.languages };
    case "tabChanged":
      return { ...state, tab: action.tab };
    case "languageChanged":
      return { ...state, languageCode: action.languageCode };
    case "patientChanged":
      return { ...state, patient: { ...state.patient, ...action.patient } };
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
      };
    case "replyAdded":
      return { ...state, turns: [...state.turns, action.reply] };
    case "analysisFailed":
      return { ...state, analysing: false, error: action.message };
    case "reset":
      return {
        ...initialState,
        languages: state.languages,
        tab: state.tab,
        languageCode: state.languageCode,
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
      .then((languages) => dispatch({ type: "languagesLoaded", languages }))
      .catch(() => undefined); // dropdowns stay empty; error surfaces on submit
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
