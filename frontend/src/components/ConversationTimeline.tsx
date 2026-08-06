import { useEffect, useRef } from "react";
import type { Turn } from "../api/types";
import { useConsultation } from "../state/consultation";
import UrgencyBadge from "./UrgencyBadge";

function TurnCard({ turn }: { turn: Turn }) {
  const time = new Date(turn.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <article className="card p-4">
      <header className="flex flex-wrap items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-800 text-[11px] font-bold text-white">
          {turn.index}
        </span>
        <span className="text-xs text-slate-400">{time}</span>
        <span className="chip bg-slate-100 text-slate-600">{turn.languageName}</span>
        {turn.durationSeconds != null && (
          <span className="text-xs text-slate-400">
            {Math.round(turn.durationSeconds)}s audio
          </span>
        )}
        <span className="ml-auto">
          <UrgencyBadge urgency={turn.triage.urgency} />
        </span>
      </header>

      <blockquote className="mt-3 border-l-2 border-blue-200 pl-3 text-sm italic text-slate-600">
        “{turn.transcript || "(no transcript returned)"}”
      </blockquote>

      {turn.summary && (
        <p className="mt-2 text-sm text-slate-700">
          <span className="font-semibold">Summary: </span>
          {turn.summary}
        </p>
      )}

      {turn.redFlags.length > 0 && (
        <p className="mt-2 rounded-lg bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 ring-1 ring-red-200">
          ⚑ Red flags: {turn.redFlags.join(", ")}
        </p>
      )}

      {turn.findings.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Findings
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {turn.findings.map((f) => (
              <span key={f} className="chip bg-teal-50 text-teal-800 ring-1 ring-teal-200">
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {turn.conditions.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Possible conditions
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {turn.conditions.map((c) => (
              <span key={c} className="chip bg-amber-50 text-amber-800 ring-1 ring-amber-200">
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {turn.triage.intron_suggestions && (
        <p className="mt-3 rounded-lg bg-blue-50 px-3 py-1.5 text-xs text-blue-800 ring-1 ring-blue-200">
          <span className="font-semibold">Sahara suggests: </span>
          {turn.triage.intron_suggestions}
        </p>
      )}
    </article>
  );
}

export default function ConversationTimeline() {
  const { state } = useConsultation();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [state.turns.length]);

  return (
    <section>
      <h2 className="card-title mb-3 px-1">Conversation</h2>
      {state.turns.length === 0 ? (
        <div className="card border-dashed p-6 text-center">
          <p className="text-sm font-medium text-slate-600">No recordings yet</p>
          <p className="mt-1 text-xs text-slate-400">
            Record the patient describing their problem in their own language.
            Each recording appears here with Sahara's full clinical read-out,
            and the reasoning graph grows on the right.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {state.turns.map((turn) => (
            <TurnCard key={`${turn.index}-${turn.timestamp}`} turn={turn} />
          ))}
          <div ref={endRef} />
        </div>
      )}
    </section>
  );
}
