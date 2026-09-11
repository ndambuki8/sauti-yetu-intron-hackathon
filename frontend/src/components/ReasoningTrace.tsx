import type { Discriminator } from "../api/types";
import { latestTurn, useConsultation } from "../state/consultation";
import { CitationDetails, ProvenanceBadges } from "./Provenance";
import VerdictBanner from "./VerdictBanner";

/**
 * The explainability surface ("Evidence" view). Renders why the urgency was
 * reached (which cited sign drove it), the topic basis, and every discriminator
 * that fired, each with its knowledge-base citation one tap away. Rendered
 * inside the shared reasoning panel, so it returns bare content.
 */

function SignCard({ sign }: { sign: Discriminator }) {
  return (
    <details className="group rounded-xl bg-white ring-1 ring-slate-200 open:ring-slate-300">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2">
        <span className="flex items-center gap-2 text-sm font-medium text-slate-800">
          <span className="text-slate-400 transition-transform group-open:rotate-90">›</span>
          {sign.label}
        </span>
        <ProvenanceBadges source={sign.source} />
      </summary>
      <div className="border-t border-slate-100 px-3 py-2 pl-8">
        <p className="mb-1.5 text-xs text-slate-500">
          Heard in the recording:{" "}
          <span className="font-medium text-slate-700">“{sign.keyword}”</span>
        </p>
        <CitationDetails source={sign.source} />
      </div>
    </details>
  );
}

function Block({
  title,
  accent,
  children,
}: {
  title: string;
  accent?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className={`section-label ${accent ?? ""}`}>{title}</h3>
      <div className="mt-2 space-y-2">{children}</div>
    </div>
  );
}

export default function ReasoningTrace() {
  const { state } = useConsultation();
  const turn = latestTurn(state);

  if (!turn) {
    return (
      <div className="flex min-h-[280px] flex-col items-center justify-center px-6 py-12 text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-500 ring-1 ring-brand-100">
          <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
            <path
              d="M4 7h16M4 12h10M4 17h7"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </div>
        <p className="text-sm font-medium text-slate-600">
          Reasoning appears after the first recording
        </p>
        <p className="mt-1 max-w-xs text-xs text-slate-400">
          Urgency, why it was reached, and the guideline behind every clinical
          sign, traceable top to bottom.
        </p>
      </div>
    );
  }

  const t = turn.triage;
  const redFlags = t.matched_discriminators.filter((d) => d.is_red_flag);
  const prioritySigns = t.matched_discriminators.filter((d) => !d.is_red_flag);

  return (
    <div className="flex flex-col">
      <VerdictBanner triage={t} />

      <div className="space-y-5 p-5">
        <Block title="Why this urgency">
          {t.acuity ? (
            <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
              <p className="text-sm text-slate-700">
                Escalated to <span className="font-semibold">{t.urgency}</span> by
                the sign{" "}
                <span className="font-semibold">{t.acuity.discriminator}</span>.
              </p>
              <div className="mt-2">
                <ProvenanceBadges source={t.acuity.source} />
                <div className="mt-1.5">
                  <CitationDetails source={t.acuity.source} />
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              Urgency reflects the presenting complaint. No acute discriminators
              were detected in this recording.
            </p>
          )}
        </Block>

        {t.topic_source && (
          <Block title="Basis for the topic">
            <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
              <p className="text-sm font-medium text-slate-800">{t.topic}</p>
              <div className="mt-2">
                <ProvenanceBadges source={t.topic_source} />
                <div className="mt-1.5">
                  <CitationDetails source={t.topic_source} />
                </div>
              </div>
            </div>
            {t.other_possible_topics.length > 0 && (
              <p className="text-xs text-slate-400">
                Also considered: {t.other_possible_topics.join("; ")}
              </p>
            )}
          </Block>
        )}

        {redFlags.length > 0 && (
          <Block title={`Red flags (${redFlags.length})`} accent="text-red-600">
            {redFlags.map((sign) => (
              <SignCard key={sign.id} sign={sign} />
            ))}
          </Block>
        )}

        {prioritySigns.length > 0 && (
          <Block
            title={`Priority signs (${prioritySigns.length})`}
            accent="text-amber-600"
          >
            {prioritySigns.map((sign) => (
              <SignCard key={sign.id} sign={sign} />
            ))}
          </Block>
        )}
      </div>
    </div>
  );
}
