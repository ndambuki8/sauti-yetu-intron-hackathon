import { useEffect, useRef, useState } from "react";
import { latestTurn, useConsultation } from "../state/consultation";
import DifferentialPanel from "./DifferentialPanel";
import ReasoningGraph from "./ReasoningGraph";
import ReasoningTrace from "./ReasoningTrace";
import ResultSummary from "./ResultSummary";
import Tooltip, { InfoIcon } from "./Tooltip";

type View = "summary" | "differential" | "evidence" | "map";

const SEGMENTS: { id: View; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "differential", label: "Differential" },
  { id: "evidence", label: "Evidence" },
  { id: "map", label: "Map" },
];

/**
 * One cohesive reasoning panel with an adaptive segmented view. After analysis
 * it opens on a focused Summary and lets the clinician step into the
 * Differential, the Evidence (cited signs), or the Map, so information is
 * revealed on demand instead of dumped all at once. Before analysis it opens on
 * the interactive Map board.
 */
export default function ReasoningView() {
  const { state } = useConsultation();
  const hasResults = latestTurn(state) !== null;
  const [view, setView] = useState<View>("map");
  const userChose = useRef(false);

  useEffect(() => {
    if (hasResults && !userChose.current) setView("summary");
  }, [hasResults]);

  const choose = (v: View) => {
    userChose.current = true;
    setView(v);
  };

  return (
    <div className="card flex flex-col overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-1.5">
          <h2 className="text-sm font-semibold text-slate-800">Clinical reasoning</h2>
          <Tooltip label="Every conclusion links to its source. Green means guideline-backed, blue means chart-verified, amber means provisional and not yet clinically reviewed.">
            <span className="text-slate-300 transition-colors hover:text-slate-500">
              <InfoIcon />
            </span>
          </Tooltip>
        </div>
        <div className="seg">
          {SEGMENTS.map((s) => (
            <button
              key={s.id}
              onClick={() => choose(s.id)}
              className={`seg-btn ${view === s.id ? "seg-btn-active" : ""}`}
              aria-pressed={view === s.id}
            >
              {s.label}
            </button>
          ))}
        </div>
      </header>
      <div className="divider" />
      {view === "summary" && <ResultSummary onNavigate={choose} />}
      {view === "differential" && <DifferentialPanel />}
      {view === "evidence" && <ReasoningTrace />}
      {view === "map" && <ReasoningGraph />}
    </div>
  );
}
