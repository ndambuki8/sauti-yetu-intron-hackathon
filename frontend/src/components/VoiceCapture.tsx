import { useEffect, useRef, useState } from "react";
import { createSession, runTriage } from "../api/client";
import { latestTurn, useConsultation } from "../state/consultation";
import StageStepper from "./StageStepper";
import Tooltip, { InfoIcon } from "./Tooltip";

const MAX_SECONDS = 120;

function MicIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-5a3.5 3.5 0 1 0-7 0v5A3.5 3.5 0 0 0 12 15Z"
        fill="currentColor"
      />
      <path
        d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function StopIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <rect x="7" y="7" width="10" height="10" rx="2.5" />
    </svg>
  );
}

/**
 * The voice-first centerpiece. A reactive microphone orb whose halo pulses to
 * the live input level (Web Audio AnalyserNode), a real-time waveform while
 * recording, and staged status while Sahara analyses. On the first visit it is
 * the hero; once a consultation is running it stays as the primary control.
 */
export default function VoiceCapture() {
  const { state, dispatch } = useConsultation();
  const languageCode = state.languageCode;

  const [consented, setConsented] = useState(false);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [filename, setFilename] = useState("recording.webm");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [micError, setMicError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const haloRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );

  // Tear down audio graph if the component unmounts mid-recording.
  useEffect(() => () => stopViz(), []);

  const acceptAudio = (next: Blob, nextFilename: string) => {
    setBlob(next);
    setFilename(nextFilename);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(next));
  };

  const stopViz = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
    if (haloRef.current) haloRef.current.style.transform = "scale(1)";
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const startViz = (stream: MediaStream) => {
    const Ctor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    const ctx = new Ctor();
    audioCtxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const bins = new Uint8Array(analyser.frequencyBinCount);

    const draw = () => {
      analyser.getByteFrequencyData(bins);

      // Overall level → halo scale (the orb "breathes" with the voice).
      let sum = 0;
      for (let i = 0; i < bins.length; i++) sum += bins[i];
      const level = sum / bins.length / 255; // 0..1
      if (haloRef.current) {
        haloRef.current.style.transform = `scale(${1 + level * 0.9})`;
        haloRef.current.style.opacity = String(0.25 + level * 0.5);
      }

      // Live frequency-bar waveform.
      const canvas = canvasRef.current;
      const cctx = canvas?.getContext("2d");
      if (canvas && cctx) {
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth;
        const h = canvas.clientHeight;
        if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
          canvas.width = w * dpr;
          canvas.height = h * dpr;
        }
        cctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        cctx.clearRect(0, 0, w, h);
        const bars = 40;
        const step = Math.floor(bins.length / bars);
        const gap = 3;
        const bw = (w - gap * (bars - 1)) / bars;
        for (let i = 0; i < bars; i++) {
          const v = bins[i * step] / 255;
          const bh = Math.max(2, v * h);
          const x = i * (bw + gap);
          const y = (h - bh) / 2;
          const grad = cctx.createLinearGradient(0, y, 0, y + bh);
          grad.addColorStop(0, "#57bffb");
          grad.addColorStop(1, "#4f46e5");
          cctx.fillStyle = grad;
          const r = Math.min(bw / 2, 3);
          cctx.beginPath();
          cctx.roundRect(x, y, bw, bh, r);
          cctx.fill();
        }
      }

      rafRef.current = requestAnimationFrame(draw);
    };
    draw();
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
        stopViz();
        stream.getTracks().forEach((t) => t.stop());
        acceptAudio(
          new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }),
          "recording.webm",
        );
        setRecording(false);
      };
      recorder.start();
      setRecording(true);
      setSeconds(0);
      timerRef.current = window.setInterval(
        () => setSeconds((s) => s + 1),
        1000,
      );
      startViz(stream);
    } catch (err) {
      setMicError(err instanceof Error ? err.message : "Microphone unavailable");
    }
  };

  // Auto-stop at the Sahara sync limit.
  useEffect(() => {
    if (recording && seconds >= MAX_SECONDS) {
      recorderRef.current?.stop();
    }
  }, [recording, seconds]);

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
      const response = await runTriage(
        blob,
        filename,
        languageCode,
        sessionId,
        state.patient,
      );
      dispatch({ type: "turnAdded", response, languageName });
      setBlob(null);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Triage failed",
      });
    }
  };

  const analysing = state.analysing;
  const hasResults = latestTurn(state) !== null;
  const mmss = `${String(Math.floor(seconds / 60)).padStart(1, "0")}:${String(
    seconds % 60,
  ).padStart(2, "0")}`;

  const orbState = analysing ? "analysing" : recording ? "recording" : "idle";
  const statusLabel = analysing
    ? "Analysing with Sahara"
    : recording
      ? "Listening, tap to stop"
      : blob
        ? "Ready to analyse"
        : consented
          ? "Tap the mic to capture the patient"
          : "Confirm patient consent to begin";

  return (
    <section className="glass overflow-hidden shadow-glass-lg">
      {/* Ambient aurora wash behind the hero — animated CSS blobs, no assets. */}
      <div className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand-50/60 via-transparent to-indigo-50/60"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -left-16 -top-20 h-56 w-56 rounded-full bg-brand-300/40 blur-3xl animate-float"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-16 -top-10 h-52 w-52 rounded-full bg-indigo-300/40 blur-3xl animate-float"
          style={{ animationDelay: "2s" }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute bottom-0 left-1/3 h-48 w-48 rounded-full bg-teal-300/30 blur-3xl animate-float"
          style={{ animationDelay: "4s" }}
        />
        <div className="relative flex flex-col items-center gap-6 px-5 py-8 sm:py-10">
          {!hasResults && (
            <div className="max-w-xl text-center">
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                Speak. Watch the reasoning form.
              </h1>
              <p className="mt-2 text-sm text-slate-500 sm:text-base">
                Real-time, explainable triage in the patient's own language.
                Every clinical step traceable to its source.
              </p>
            </div>
          )}

          {/* Mic orb */}
          <div className="relative flex h-44 w-44 items-center justify-center">
            {/* Reactive halo (scaled by live level via ref). */}
            <span
              ref={haloRef}
              aria-hidden
              className={`absolute h-40 w-40 rounded-full blur-md transition-transform duration-75 ${
                orbState === "recording"
                  ? "bg-red-400/40"
                  : "bg-brand-400/30"
              }`}
              style={{ transform: "scale(1)" }}
            />
            {/* Idle breathing pulse rings. */}
            {orbState === "idle" && (
              <>
                <span className="absolute h-28 w-28 rounded-full bg-brand-400/20 animate-pulse-ring" />
                <span
                  className="absolute h-28 w-28 rounded-full bg-indigo-400/20 animate-pulse-ring"
                  style={{ animationDelay: "1.2s" }}
                />
              </>
            )}

            <button
              onClick={toggleRecording}
              disabled={!consented || analysing}
              aria-label={recording ? "Stop recording" : "Start recording"}
              className={`relative z-10 flex h-28 w-28 items-center justify-center rounded-full text-white shadow-glow transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 ${
                recording
                  ? "bg-gradient-to-br from-red-500 to-rose-600"
                  : "bg-gradient-to-br from-brand-500 via-brand-600 to-indigo-600 hover:brightness-105"
              } ${orbState === "idle" ? "animate-breathe" : ""}`}
            >
              {analysing ? (
                <span className="h-8 w-8 animate-spin rounded-full border-[3px] border-white/40 border-t-white" />
              ) : recording ? (
                <StopIcon className="h-9 w-9" />
              ) : (
                <MicIcon className="h-11 w-11" />
              )}
            </button>
          </div>

          {/* Status + live waveform */}
          <div className="flex w-full max-w-md flex-col items-center gap-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
              {recording && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-semibold text-red-600 ring-1 ring-red-200">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
                  {mmss} / 2:00
                </span>
              )}
              <span>{statusLabel}</span>
            </div>

            {recording && (
              <div className="h-16 w-full rounded-xl bg-white/60 p-2 ring-1 ring-slate-200/70">
                <canvas ref={canvasRef} className="waveform-canvas" />
              </div>
            )}

            {analysing && <StageStepper />}

            {!recording && !analysing && blob && previewUrl && (
              <div className="flex w-full flex-col items-center gap-3 animate-fade-in">
                <audio src={previewUrl} controls className="w-full" />
                <button onClick={analyse} className="btn-primary w-full">
                  Analyse with Sahara
                </button>
              </div>
            )}
          </div>

          {/* Controls: consent + language + upload */}
          <div className="flex w-full max-w-2xl flex-col gap-3 border-t border-slate-200/60 pt-5 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
              <input
                type="checkbox"
                checked={consented}
                onChange={(e) => setConsented(e.target.checked)}
                className="accent-brand-600"
              />
              Patient consent
              <Tooltip label="Audio is sent to Intron for triage processing and is not stored by this app.">
                <span className="text-slate-300 transition-colors hover:text-slate-500">
                  <InfoIcon className="h-3.5 w-3.5" />
                </span>
              </Tooltip>
            </label>

            <div className="flex flex-wrap items-center gap-2">
              <input
                type="number"
                min={0}
                max={120}
                value={state.patient.age}
                onChange={(e) =>
                  dispatch({ type: "patientChanged", patient: { age: e.target.value } })
                }
                placeholder="Age"
                aria-label="Patient age in years"
                className="input w-16"
              />
              <select
                value={state.patient.sex}
                onChange={(e) =>
                  dispatch({ type: "patientChanged", patient: { sex: e.target.value } })
                }
                aria-label="Patient sex"
                className="input w-auto"
              >
                <option value="">Sex</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
              </select>
              {state.patient.sex === "female" && (
                <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                  <input
                    type="checkbox"
                    checked={state.patient.pregnant}
                    onChange={(e) =>
                      dispatch({
                        type: "patientChanged",
                        patient: { pregnant: e.target.checked },
                      })
                    }
                    className="accent-brand-600"
                  />
                  Pregnant
                </label>
              )}
              <select
                value={languageCode}
                onChange={(e) =>
                  dispatch({ type: "languageChanged", languageCode: e.target.value })
                }
                className="input max-w-[13rem]"
                aria-label="Patient language"
              >
                {Object.entries(state.languages).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name} ({code})
                  </option>
                ))}
              </select>

              <label
                className={`btn-secondary cursor-pointer text-xs ${
                  consented ? "" : "pointer-events-none opacity-50"
                }`}
                title="Upload an audio file instead"
              >
                Upload
                <input
                  type="file"
                  accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm,.flac"
                  disabled={!consented}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) acceptAudio(file, file.name);
                  }}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          {/* Optional vitals — collapsed by default to keep the hero clean.
              When entered they drive the age-banded high-risk vital checks. */}
          <details className="w-full max-w-2xl overflow-hidden rounded-xl bg-white/50 ring-1 ring-slate-200/60">
            <summary className="cursor-pointer list-none px-4 py-2 text-xs font-medium text-slate-500 hover:text-slate-700">
              Vitals (optional)
            </summary>
            <div className="flex flex-wrap items-center gap-2 border-t border-slate-200/60 px-4 py-3">
              {(
                [
                  ["hr", "HR", "bpm"],
                  ["rr", "RR", "/min"],
                  ["temp", "Temp", "°C"],
                  ["spo2", "SpO₂", "%"],
                ] as const
              ).map(([field, label, unit]) => (
                <label key={field} className="flex items-center gap-1 text-xs text-slate-500">
                  {label}
                  <input
                    type="number"
                    value={state.patient[field]}
                    onChange={(e) =>
                      dispatch({ type: "patientChanged", patient: { [field]: e.target.value } })
                    }
                    className="input w-16"
                    aria-label={`${label} (${unit})`}
                  />
                </label>
              ))}
              <label className="flex items-center gap-1 text-xs text-slate-500">
                AVPU
                <select
                  value={state.patient.avpu}
                  onChange={(e) =>
                    dispatch({ type: "patientChanged", patient: { avpu: e.target.value } })
                  }
                  className="input w-auto"
                  aria-label="AVPU responsiveness"
                >
                  <option value="">—</option>
                  <option value="A">A (alert)</option>
                  <option value="V">V (voice)</option>
                  <option value="P">P (pain)</option>
                  <option value="U">U (unresponsive)</option>
                </select>
              </label>
            </div>
          </details>

          {micError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-red-200">
              Microphone error: {micError}
            </p>
          )}
          {state.error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-red-200">
              {state.error}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
