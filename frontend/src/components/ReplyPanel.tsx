import { useEffect, useState } from "react";
import { getPhrases, respond } from "../api/client";
import type { Phrase } from "../api/types";
import { toWorkerReply, useConsultation } from "../state/consultation";

/** The worker's side of the loop: pick a quick phrase or type English, and
 * the reply is translated (local NLLB) and spoken to the patient with a
 * native Intron TTS voice. */
export default function ReplyPanel() {
  const { state, dispatch } = useConsultation();

  const [phrases, setPhrases] = useState<Phrase[]>([]);
  const [text, setText] = useState("");
  const [gender, setGender] = useState<"male" | "female">("female");
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasPatientTurn = state.turns.some((t) => t.kind === "patient");

  useEffect(() => {
    if (!hasPatientTurn) return;
    let cancelled = false;
    getPhrases(state.languageCode)
      .then((items) => {
        if (!cancelled) setPhrases(items);
      })
      .catch(() => {
        if (!cancelled) setPhrases([]);
      });
    return () => {
      cancelled = true;
    };
  }, [state.languageCode, hasPatientTurn]);

  if (!hasPatientTurn) return null;

  const speak = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || speaking) return;
    setSpeaking(true);
    setError(null);
    try {
      const response = await respond(trimmed, state.languageCode, gender);
      const reply = toWorkerReply(response);
      dispatch({ type: "replyAdded", reply });
      setText("");
      // Autoplay may be blocked by the browser; the timeline card keeps
      // a replayable <audio> control either way.
      new Audio(reply.audioUrl).play().catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reply failed");
    } finally {
      setSpeaking(false);
    }
  };

  return (
    <section className="card p-5">
      <h2 className="card-title">Reply to patient</h2>
      <p className="mt-1 text-xs text-slate-400">
        Pick a quick phrase or type in English — it is translated and spoken
        aloud in the patient's language.
      </p>

      {phrases.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {phrases.map((p) => (
            <button
              key={p.english}
              onClick={() => speak(p.english)}
              disabled={speaking}
              title={p.translated !== p.english ? p.translated : undefined}
              className="chip bg-slate-100 text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-200 disabled:opacity-50"
            >
              {p.english}
            </button>
          ))}
        </div>
      )}

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        placeholder="Type a reply in English..."
        className="input mt-3"
      />

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
          Voice
          <select
            value={gender}
            onChange={(e) => setGender(e.target.value as "male" | "female")}
            className="input !mt-0 w-auto"
          >
            <option value="female">Female</option>
            <option value="male">Male</option>
          </select>
        </label>
        <button
          onClick={() => speak(text)}
          disabled={!text.trim() || speaking}
          className="btn-primary ml-auto"
        >
          {speaking ? "Translating & speaking…" : "Speak to patient"}
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-red-200">
          {error}
        </p>
      )}
    </section>
  );
}
