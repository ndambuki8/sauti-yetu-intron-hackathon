import { deleteSession } from "../api/client";
import { useConsultation, type Tab } from "../state/consultation";
import Tooltip, { ShieldIcon } from "./Tooltip";

function TabButton({ tab, label }: { tab: Tab; label: string }) {
  const { state, dispatch } = useConsultation();
  const active = state.tab === tab;
  return (
    <button
      onClick={() => dispatch({ type: "tabChanged", tab })}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200"
          : "text-slate-500 hover:text-slate-800"
      }`}
    >
      {label}
    </button>
  );
}

export default function TopBar() {
  const { state, dispatch } = useConsultation();
  const count = state.turns.length;

  const startNewConsultation = async () => {
    if (state.sessionId) await deleteSession(state.sessionId);
    dispatch({ type: "reset" });
  };

  return (
    <header className="sticky top-0 z-30 border-b border-white/40 bg-white/60 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 text-sm font-bold text-white shadow-glow">
            SY
          </span>
          <div className="leading-tight">
            <p className="text-sm font-bold text-slate-900">Sauti&nbsp;Yetu</p>
            <p className="hidden text-xs text-slate-500 sm:block">
              Explainable voice triage · Intron Sahara
            </p>
          </div>
        </div>

        <nav className="ml-4 flex gap-1 rounded-xl bg-slate-100/70 p-1 ring-1 ring-slate-200/60">
          <TabButton tab="triage" label="Triage" />
          <TabButton tab="benchmark" label="Benchmark" />
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <span
            className={`chip hidden sm:inline-flex ${
              state.sessionId ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-500"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                state.sessionId ? "bg-brand-600 animate-breathe" : "bg-slate-400"
              }`}
            />
            {state.sessionId
              ? count
                ? `${count} recording${count === 1 ? "" : "s"}`
                : "Consultation active"
              : "No active consultation"}
          </span>
          <Tooltip
            side="bottom"
            label="Decision support only, not a medical device. Outputs are hints to aid, never replace, clinical judgement."
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600">
              <ShieldIcon />
            </span>
          </Tooltip>
          <button onClick={startNewConsultation} className="btn-secondary px-3 py-1.5 text-xs">
            New
          </button>
        </div>
      </div>
    </header>
  );
}
