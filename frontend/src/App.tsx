import BenchmarkPanel from "./components/BenchmarkPanel";
import CapturePanel from "./components/CapturePanel";
import ClinicalRail from "./components/ClinicalRail";
import ConversationTimeline from "./components/ConversationTimeline";
import ReasoningGraph from "./components/ReasoningGraph";
import TopBar from "./components/TopBar";
import { ConsultationProvider, useConsultation } from "./state/consultation";

function TriageWorkspace() {
  return (
    <main className="mx-auto grid max-w-[1600px] grid-cols-1 gap-5 px-5 py-5 lg:grid-cols-[360px_minmax(0,1fr)_340px]">
      <div className="space-y-5">
        <CapturePanel />
        <ConversationTimeline />
      </div>
      <ReasoningGraph />
      <ClinicalRail />
    </main>
  );
}

function Shell() {
  const { state } = useConsultation();
  return (
    <div className="min-h-screen">
      <TopBar />
      {state.tab === "triage" ? (
        <TriageWorkspace />
      ) : (
        <main className="px-5 py-5">
          <BenchmarkPanel />
        </main>
      )}
      <footer className="mx-auto max-w-[1600px] px-5 pb-8 pt-2 text-xs text-slate-400">
        <p className="font-semibold text-slate-500">
          Decision support only — not a medical device.
        </p>
        <p>
          Outputs are hints to aid, never replace, clinical judgement. Verify
          against the patient before acting. · MLC (Africa) × Intron Agentic
          Voice AI Challenge
        </p>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <ConsultationProvider>
      <Shell />
    </ConsultationProvider>
  );
}
