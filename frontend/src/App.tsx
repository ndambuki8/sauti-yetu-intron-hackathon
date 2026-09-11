import BenchmarkPanel from "./components/BenchmarkPanel";
import ClinicalRail from "./components/ClinicalRail";
import ConversationTimeline from "./components/ConversationTimeline";
import ReasoningView from "./components/ReasoningView";
import ReplyPanel from "./components/ReplyPanel";
import TopBar from "./components/TopBar";
import VoiceCapture from "./components/VoiceCapture";
import { ConsultationProvider, latestTurn, useConsultation } from "./state/consultation";

function TriageWorkspace() {
  const { state } = useConsultation();
  const hasResults = latestTurn(state) !== null;

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:py-8">
      <VoiceCapture />

      {hasResults ? (
        <>
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="animate-fade-in-up lg:col-span-2">
              <ReasoningView />
            </div>
            <div className="animate-fade-in-up space-y-6">
              <ClinicalRail />
              <ReplyPanel />
            </div>
          </div>
          <div className="animate-fade-in-up">
            <ConversationTimeline />
          </div>
        </>
      ) : (
        // Pre-analysis: the interactive reasoning board sits full width so the
        // clinician can explore it before recording.
        <ReasoningView />
      )}
    </div>
  );
}

function Shell() {
  const { state } = useConsultation();
  return (
    <div className="min-h-screen pb-12">
      <TopBar />
      {state.tab === "triage" ? (
        <TriageWorkspace />
      ) : (
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <BenchmarkPanel />
        </main>
      )}
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
