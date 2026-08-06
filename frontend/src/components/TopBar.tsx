import { deleteSession } from "../api/client";
import { useConsultation, type Tab } from "../state/consultation";

function TabButton({ tab, label }: { tab: Tab; label: string }) {
  const { state, dispatch } = useConsultation();
  const active = state.tab === tab;
  return (
    <button
      onClick={() => dispatch({ type: "tabChanged", tab })}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
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
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-5 py-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
            SY
          </span>
          <div className="leading-tight">
            <p className="text-sm font-bold text-slate-900">Sauti Yetu</p>
            <p className="text-xs text-slate-500">Clinical voice triage · Intron Sahara</p>
          </div>
        </div>

        <nav className="ml-6 flex gap-1 rounded-lg bg-slate-100 p-1">
          <TabButton tab="triage" label="Triage" />
          <TabButton tab="benchmark" label="Model benchmark" />
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <span
            className={`chip ${
              state.sessionId ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-500"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                state.sessionId ? "bg-blue-600" : "bg-slate-400"
              }`}
            />
            {state.sessionId
              ? count
                ? `Consultation · ${count} recording${count === 1 ? "" : "s"}`
                : "Consultation active"
              : "No active consultation"}
          </span>
          <button onClick={startNewConsultation} className="btn-secondary py-1.5 text-xs">
            New consultation
          </button>
        </div>
      </div>
    </header>
  );
}
