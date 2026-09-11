import type { TriageResult } from "../api/types";

const URGENCY_BANNER: Record<string, string> = {
  EMERGENCY: "bg-red-600",
  URGENT: "bg-amber-500",
  ROUTINE: "bg-emerald-600",
};

/** The colour-coded triage verdict, shared across the summary and evidence
 * views so the headline decision looks identical wherever it appears. */
export default function VerdictBanner({ triage }: { triage: TriageResult }) {
  const color = URGENCY_BANNER[triage.urgency] ?? "bg-slate-600";
  return (
    <div className={`${color} px-5 py-4 text-white`}>
      <p className="text-[11px] font-semibold uppercase tracking-widest text-white/80">
        Triage urgency
      </p>
      <p className="mt-0.5 text-2xl font-bold leading-tight">{triage.urgency}</p>
      <p className="mt-1 text-sm font-medium">{triage.topic}</p>
      <p className="text-xs text-white/85">Route to: {triage.suggested_department}</p>
    </div>
  );
}
