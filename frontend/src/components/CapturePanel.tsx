import { useEffect, useRef, useState } from "react";
import { createSession, runTriage } from "../api/client";
import { useConsultation } from "../state/consultation";
import StageStepper from "./StageStepper";

export default function CapturePanel() {
  const { state, dispatch } = useConsultation();

  const [languageCode, setLanguageCode] = useState("sw");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [filename, setFilename] = useState("recording.webm");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    // Default once languages arrive, only if the user hasn't chosen one.
    if (state.languages.sw) setLanguageCode((current) => current || "sw");
  }, [state.languages]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const acceptAudio = (next: Blob, nextFilename: string) => {
    setBlob(next);
    setFilename(nextFilename);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(next));
  };

  const toggleRecording = async () => {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
      return;
    }
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        acceptAudio(
          new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }),
          "recording.webm",
        );
        setRecording(false);
      };
      recorder.start();
      setRecording(true);
    } catch (err) {
      setMicError(err instanceof Error ? err.message : "Microphone unavailable");
    }
  };

  const analyse = async () => {
    if (!blob || state.analysing) return;
    dispatch({ type: "analysisStarted" });
    try {
      let sessionId = state.sessionId;
      if (!sessionId) {
        sessionId = await createSession();
        dispatch({ type: "sessionStarted", sessionId });
      }
      const languageName = state.languages[languageCode] ?? languageCode;
      const response = await runTriage(blob, filename, languageCode, sessionId);
      dispatch({ type: "turnAdded", response, languageName });
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Triage failed",
      });
    }
  };

  return (
    <section className="card p-5">
      <h2 className="card-title">Patient audio</h2>

      <label className="mt-4 block text-xs font-medium text-slate-600">
        Patient language
      </label>
      <select
        value={languageCode}
        onChange={(e) => setLanguageCode(e.target.value)}
        className="input mt-1"
      >
        {Object.entries(state.languages).map(([code, name]) => (
          <option key={code} value={code}>
            {name} ({code})
          </option>
        ))}
      </select>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={toggleRecording}
          className={recording ? "btn bg-red-50 text-red-700 ring-1 ring-red-300" : "btn-secondary"}
        >
          <span className={`h-2 w-2 rounded-full ${recording ? "animate-pulse bg-red-600" : "bg-slate-400"}`} />
          {recording ? "Stop recording" : "Start recording"}
        </button>
        <span className="text-xs text-slate-400">or</span>
        <input
          type="file"
          accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm,.flac"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) acceptAudio(file, file.name);
          }}
          className="text-xs text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-xs file:font-medium file:text-slate-700 hover:file:bg-slate-200"
        />
      </div>

      <p className="mt-2 text-xs text-slate-400">Max 120 seconds per clip (Sahara sync limit).</p>

      {micError && <p className="mt-2 text-xs text-red-700">Microphone error: {micError}</p>}

      {previewUrl && <audio src={previewUrl} controls className="mt-3 w-full" />}

      <button onClick={analyse} disabled={!blob || state.analysing} className="btn-primary mt-4 w-full">
        {state.analysing ? "Analysing…" : "Analyse with Sahara"}
      </button>

      {state.analysing && <StageStepper />}

      {state.error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-red-200">
          {state.error}
        </p>
      )}
    </section>
  );
}
