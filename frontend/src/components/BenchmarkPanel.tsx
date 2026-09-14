import { useEffect, useRef, useState } from "react";
import { runBenchmark } from "../api/client";
import type { BenchmarkResponse } from "../api/types";
import { useConsultation } from "../state/consultation";

const fmt = (v: number | null) => (v === null || v === undefined ? "—" : v);

export default function BenchmarkPanel() {
  const { state } = useConsultation();
  const [languageCode, setLanguageCode] = useState(state.languageCode);
  const [file, setFile] = useState<Blob | null>(state.capturedAudio?.blob ?? null);
  const [filename, setFilename] = useState(state.capturedAudio?.filename ?? "recording.webm");
  const [reference, setReference] = useState("");
  const [switchPoints, setSwitchPoints] = useState("");
  const [expectedTopic, setExpectedTopic] = useState("");
  const [expectedUrgency, setExpectedUrgency] = useState("");
  const [expectedDepartment, setExpectedDepartment] = useState("");
  const [expectedSlots, setExpectedSlots] = useState("");
  const [expectedEntities, setExpectedEntities] = useState("");
  const [agentic, setAgentic] = useState(true);
  const [running, setRunning] = useState(false);
  const [consented, setConsented] = useState(false);
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BenchmarkResponse | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (state.capturedAudio) {
      setFile(state.capturedAudio.blob);
      setFilename(state.capturedAudio.filename);
      setLanguageCode(state.languageCode);
    }
  }, [state.capturedAudio, state.languageCode]);

  const ready = file !== null && reference.trim().length > 0 && !running;

  const acceptRecording = (next: Blob) => {
    setFile(next);
    setFilename("benchmark-recording.webm");
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
      recorder.ondataavailable = (event) => chunksRef.current.push(event.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        acceptRecording(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
        setRecording(false);
      };
      recorder.start();
      setRecording(true);
    } catch (err) {
      setMicError(err instanceof Error ? err.message : "Microphone unavailable");
    }
  };

  const submit = async () => {
    if (!file || !ready) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      let parsedSwitchPoints: Array<Record<string, unknown>> = [];
      if (switchPoints.trim()) {
        parsedSwitchPoints = JSON.parse(switchPoints);
        if (!Array.isArray(parsedSwitchPoints)) throw new Error("Switch points must be a JSON list.");
      }
      let parsedSlots: Record<string, string> = {};
      if (expectedSlots.trim()) {
        parsedSlots = JSON.parse(expectedSlots);
        if (Array.isArray(parsedSlots) || typeof parsedSlots !== "object") throw new Error("Expected slots must be a JSON object.");
      }
      setResult(await runBenchmark(file, filename, reference.trim(), languageCode, {
        switchPoints: parsedSwitchPoints,
        agentic,
        agentReference: agentic ? {
          expected_topic: expectedTopic,
          expected_urgency: expectedUrgency,
          expected_suggested_department: expectedDepartment,
          expected_entities: expectedEntities.split(",").map((item) => item.trim()).filter(Boolean),
        } : undefined,
        expectedSlots: parsedSlots,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Benchmark failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <section className="card p-5">
        <h2 className="card-title">Code-switch benchmark</h2>
        <p className="mt-1 text-xs text-slate-400">
          Compare Intron Sahara, OpenAI Whisper (local), and Meta MMS (local)
          against a human reference transcript. First run downloads model
          weights and is slow.
        </p>

        <label className="mt-4 flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 ring-1 ring-slate-200">
          <input
            type="checkbox"
            checked={consented}
            onChange={(event) => setConsented(event.target.checked)}
            className="mt-0.5"
          />
          The speaker consents to this recording being sent to the configured
          speech services for benchmarking.
        </label>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium text-slate-600">
              Language of the clip
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
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600">Audio clip</label>
            {state.capturedAudio && (
              <p className="mb-2 text-xs text-emerald-700">Using the recording captured in Triage: {filename}</p>
            )}
            <input
              type="file"
              accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm,.flac"
              disabled={!consented}
              onChange={(e) => {
                const next = e.target.files?.[0];
                if (next) {
                  setFile(next);
                  setFilename(next.name);
                }
              }}
              className="mt-2 text-xs text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-xs file:font-medium file:text-slate-700 hover:file:bg-slate-200"
            />
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={toggleRecording}
                disabled={!consented || running}
                className={`${recording ? "btn bg-red-50 text-red-700 ring-1 ring-red-300" : "btn-secondary"} disabled:cursor-not-allowed disabled:opacity-50`}
              >
                <span className={`h-2 w-2 rounded-full ${recording ? "animate-pulse bg-red-600" : "bg-slate-400"}`} />
                {recording ? "Stop recording" : "Record from microphone"}
              </button>
              <span className="text-xs text-slate-400">or choose a file above</span>
            </div>
            {micError && <p className="mt-2 text-xs text-red-700">Microphone error: {micError}</p>}
            {previewUrl && <audio src={previewUrl} controls className="mt-3 w-full" />}
          </div>
        </div>

        <label className="mt-4 block text-xs font-medium text-slate-600">
          Reference transcript (ground truth)
        </label>
        <textarea
          rows={3}
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          placeholder="Type the exact words spoken in the clip, code-switching included…"
          className="input mt-1 resize-y"
        />

        <details className="mt-4 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200" open>
          <summary className="cursor-pointer text-xs font-semibold text-slate-700">
            Thorough evaluation annotations
          </summary>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            Add gold annotations when available. They make switch-point WER and downstream scores auditable; leave them blank rather than guessing.
          </p>
          <label className="mt-3 block text-xs font-medium text-slate-600">
            Switch points (JSON)
          </label>
          <textarea
            rows={2}
            value={switchPoints}
            onChange={(e) => setSwitchPoints(e.target.value)}
            placeholder='[{"token_index":4,"from_language":"sw","to_language":"en"}]'
            className="input mt-1 font-mono text-xs"
          />
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <input value={expectedTopic} onChange={(e) => setExpectedTopic(e.target.value)} placeholder="Expected topic" className="input" />
            <select value={expectedUrgency} onChange={(e) => setExpectedUrgency(e.target.value)} className="input">
              <option value="">Expected urgency (optional)</option>
              <option>EMERGENCY</option>
              <option>URGENT</option>
              <option>ROUTINE</option>
            </select>
            <input value={expectedDepartment} onChange={(e) => setExpectedDepartment(e.target.value)} placeholder="Expected department" className="input" />
            <input value={expectedSlots} onChange={(e) => setExpectedSlots(e.target.value)} placeholder='Expected slots JSON, e.g. {"phone":"0712..."}' className="input font-mono text-xs" />
            <input value={expectedEntities} onChange={(e) => setExpectedEntities(e.target.value)} placeholder="Expected entities, comma separated" className="input" />
          </div>
          <label className="mt-3 flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={agentic} onChange={(e) => setAgentic(e.target.checked)} />
            Run Sahara telehealth extraction for downstream evaluation
          </label>
        </details>

        <button onClick={submit} disabled={!ready} className="btn-primary mt-4">
          {running ? "Running benchmark…" : "Run benchmark"}
        </button>

        {error && (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-red-200">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="card mt-5 overflow-hidden">
          <p className="border-b border-slate-200 px-5 py-3 text-sm font-semibold text-slate-800">
            {result.best_model
              ? `Lowest WER on this clip: ${result.best_model}`
              : "No model produced a scoreable transcript."}
          </p>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs text-slate-500">
                <th className="px-5 py-2 font-medium">Model</th>
                <th className="px-3 py-2 font-medium">WER</th>
                <th className="px-3 py-2 font-medium">CER</th>
                <th className="px-3 py-2 font-medium">Latency / RTF</th>
                <th className="px-3 py-2 font-medium">Switch WER</th>
                <th className="px-3 py-2 font-medium">Agentic</th>
                <th className="px-5 py-2 font-medium">Transcript</th>
              </tr>
            </thead>
            <tbody>
              {result.results.map((r) => (
                <tr key={r.model} className="border-b border-slate-100 align-top last:border-0">
                  <td className="px-5 py-3">
                    <p className="font-medium text-slate-800">{r.model}</p>
                    <p className="text-xs text-slate-400">{r.kind}</p>
                  </td>
                  {r.error ? (
                    <td colSpan={6} className="px-3 py-3 text-xs text-red-700">
                      Error: {r.error}
                    </td>
                  ) : (
                    <>
                      <td className="px-3 py-3">{fmt(r.wer)}</td>
                      <td className="px-3 py-3">{fmt(r.cer)}</td>
                      <td className="px-3 py-3">{fmt(r.latency_seconds)}s / {fmt(r.rtf ?? null)}</td>
                      <td className="px-3 py-3">{fmt(r.switch_point?.wer ?? null)}</td>
                      <td className="px-3 py-3 text-xs">
                        {r.agentic ? `I:${r.agentic.intent_correct === null ? "—" : r.agentic.intent_correct ? "yes" : "no"} S:${fmt(r.agentic.slot_accuracy)}` : "—"}
                      </td>
                      <td className="px-5 py-3 text-slate-600">
                        {r.transcript || "(empty transcript)"}
                        {r.warning && <p className="mt-1 text-xs text-amber-700">{r.warning}</p>}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
