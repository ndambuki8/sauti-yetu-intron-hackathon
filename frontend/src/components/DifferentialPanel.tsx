import type { DifferentialItem } from "../api/types";
import { latestTurn, useConsultation } from "../state/consultation";
import { CitationDetails, ProvenanceBadges } from "./Provenance";

function pct(p: number): number {
  return Math.round(p * 100);
}

/** Colour the probability bar by confidence tier (visual only). */
function barColor(p: number): string {
  if (p >= 0.66) return "bg-red-500";
  if (p >= 0.33) return "bg-amber-500";
  return "bg-sky-500";
}

function Row({ item, rank }: { item: DifferentialItem; rank: number }) {
  return (
    <details className="group rounded-xl bg-white ring-1 ring-slate-200 open:ring-slate-300">
      <summary className="cursor-pointer list-none px-3 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-2 text-sm font-medium text-slate-800">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-500">
              {rank}
            </span>
            {item.label}
          </span>
          <span className="text-sm font-semibold tabular-nums text-slate-700">
            {pct(item.probability)}%
          </span>
        </div>
        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full ${barColor(item.probability)}`}
            style={{ width: `${Math.max(3, pct(item.probability))}%` }}
          />
        </div>
      </summary>
      <div className="border-t border-slate-100 px-3 py-2.5 text-xs">
        <p className="text-slate-500">
          Raised from a baseline of{" "}
          <span className="font-medium text-slate-700">{pct(item.prior)}%</span> by:
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {item.contributing.map((c) => (
            <span
              key={c.finding}
              className="inline-flex items-center gap-1 rounded-md bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200"
            >
              {c.finding}
              <span className="font-semibold text-slate-400">×{c.lr}</span>
            </span>
          ))}
        </div>
        {item.department && (
          <p className="mt-2 text-slate-500">Typical route: {item.department}</p>
        )}
        <div className="mt-2 border-t border-slate-100 pt-2">
          <ProvenanceBadges source={item.source} />
          <div className="mt-1.5">
            <CitationDetails source={item.source} />
          </div>
        </div>
      </div>
    </details>
  );
}

export default function DifferentialPanel() {
  const { state } = useConsultation();
  const turn = latestTurn(state);
  const differential = turn?.triage.differential ?? [];

  return (
    <div className="space-y-3 p-5">
      <div>
        <h3 className="section-label">Probabilistic differential</h3>
        <p className="mt-1 text-xs text-slate-400">
          Ranked likelihood from the symptoms heard. A ranking aid, not a
          diagnosis. Tap a condition for the evidence behind it.
        </p>
      </div>
      {differential.length === 0 ? (
        <p className="rounded-lg bg-slate-50 px-3 py-4 text-center text-sm text-slate-500 ring-1 ring-slate-200">
          No conditions matched the findings in this recording yet.
        </p>
      ) : (
        <div className="space-y-2">
          {differential.map((item, i) => (
            <Row key={item.id} item={item} rank={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
