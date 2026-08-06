import { useState } from "react";
import { runBenchmark } from "../api/client";
import type { BenchmarkResponse } from "../api/types";
import { useConsultation } from "../state/consultation";

const fmt = (v: number | null) => (v === null || v === undefined ? "—" : v);

export default function BenchmarkPanel() {
  const { state } = useConsultation();
  const [languageCode, setLanguageCode] = useState("sw");
  const [file, setFile] = useState<File | null>(null);
  const [reference, setReference] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BenchmarkResponse | null>(null);

  const ready = file !== null && reference.trim().length > 0 && !running;

  const submit = async () => {
    if (!file || !ready) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await runBenchmark(file, reference.trim(), languageCode));
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
            <input
              type="file"
              accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm,.flac"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-2 text-xs text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-xs file:font-medium file:text-slate-700 hover:file:bg-slate-200"
            />
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
                <th className="px-3 py-2 font-medium">Latency (s)</th>
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
                    <td colSpan={4} className="px-3 py-3 text-xs text-red-700">
                      Error: {r.error}
                    </td>
                  ) : (
                    <>
                      <td className="px-3 py-3">{fmt(r.wer)}</td>
                      <td className="px-3 py-3">{fmt(r.cer)}</td>
                      <td className="px-3 py-3">{fmt(r.latency_seconds)}</td>
                      <td className="px-5 py-3 text-slate-600">{r.transcript || "(empty)"}</td>
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
