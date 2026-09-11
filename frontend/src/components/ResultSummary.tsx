import { latestTurn, useConsultation } from "../state/consultation";
import VerdictBanner from "./VerdictBanner";

/** The at-a-glance result: the verdict, the leading likely condition, and a
 * count of what the evidence/differential tabs hold. Keeps the first thing a
 * clinician sees focused instead of a wall of detail. */
export default function ResultSummary({
  onNavigate,
}: {
  onNavigate?: (view: "differential" | "evidence") => void;
}) {
  const { state } = useConsultation();
  const turn = latestTurn(state);
  if (!turn) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="text-sm font-medium text-slate-600">No analysis yet</p>
        <p className="mt-1 text-xs text-slate-400">
          Record the patient to see the triage verdict and the likely conditions here.
        </p>
      </div>
    );
  }

  const t = turn.triage;
  const redFlags = t.matched_discriminators.filter((d) => d.is_red_flag);
  const priority = t.matched_discriminators.filter((d) => !d.is_red_flag);
  const top = t.differential[0];

  return (
    <div className="flex flex-col">
      <VerdictBanner triage={t} />

      <div className="space-y-4 p-5">
        {(t.auto_detected?.length ?? 0) > 0 && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 ring-1 ring-amber-200">
            Auto-detected from the conversation: {t.auto_detected!.join(", ")}. Confirm before acting.
          </p>
        )}

        {top && (
          <button
            onClick={() => onNavigate?.("differential")}
            className="block w-full rounded-xl bg-slate-50 p-3 text-left ring-1 ring-slate-200 transition hover:ring-slate-300"
          >
            <p className="section-label">Most likely</p>
            <div className="mt-1 flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-slate-800">{top.label}</span>
              <span className="text-sm font-semibold tabular-nums text-slate-600">
                {Math.round(top.probability * 100)}%
              </span>
            </div>
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-brand-500"
                style={{ width: `${Math.max(3, Math.round(top.probability * 100))}%` }}
              />
            </div>
            {t.differential.length > 1 && (
              <p className="mt-1.5 text-xs text-slate-400">
                +{t.differential.length - 1} more in the differential →
              </p>
            )}
          </button>
        )}

        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => onNavigate?.("evidence")}
            className="rounded-xl bg-red-50 p-3 text-left ring-1 ring-red-200 transition hover:brightness-[0.98]"
          >
            <p className="text-2xl font-bold text-red-600">{redFlags.length}</p>
            <p className="text-xs font-medium text-red-700">
              red flag{redFlags.length === 1 ? "" : "s"}
            </p>
          </button>
          <button
            onClick={() => onNavigate?.("evidence")}
            className="rounded-xl bg-amber-50 p-3 text-left ring-1 ring-amber-200 transition hover:brightness-[0.98]"
          >
            <p className="text-2xl font-bold text-amber-600">{priority.length}</p>
            <p className="text-xs font-medium text-amber-700">
              priority sign{priority.length === 1 ? "" : "s"}
            </p>
          </button>
        </div>

        {t.acuity && (
          <p className="text-xs text-slate-500">
            Urgency driven by <span className="font-medium text-slate-700">{t.acuity.discriminator}</span>.{" "}
            <button
              onClick={() => onNavigate?.("evidence")}
              className="font-medium text-brand-600 hover:underline"
            >
              See why
            </button>
          </p>
        )}
      </div>
    </div>
  );
}
