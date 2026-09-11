import { latestTurn, useConsultation } from "../state/consultation";
import UrgencyBadge from "./UrgencyBadge";

/** Right-hand decision panel: one cohesive card with the triage decision, the
 * auto-filled intake, and the nurse's clarifying questions as stacked sections
 * separated by hairline dividers (rather than several floating cards). */
export default function ClinicalRail() {
  const { state } = useConsultation();
  const turn = latestTurn(state);
  if (!turn) return null;

  const t = turn.triage;
  const intakeRows: Array<[string, string]> = [
    ["Patient", t.intake_card.patient_summary ?? ""],
    ["Language", t.intake_card.patient_language],
    ["Vitals", t.intake_card.vitals ?? ""],
    ["Presenting complaint", t.intake_card.presenting_complaint],
    ["Key findings", t.intake_card.key_findings],
    ["Possible conditions", t.intake_card.possible_conditions],
  ];

  return (
    <aside className="card flex flex-col overflow-hidden">
      {(t.auto_detected?.length ?? 0) > 0 && (
        <p className="bg-amber-50 px-5 py-2 text-[11px] text-amber-700">
          Auto-detected from the conversation: {t.auto_detected!.join(", ")}. Confirm before acting.
        </p>
      )}

      {/* Decision */}
      <div className="p-5">
        <h2 className="section-label">Triage decision</h2>
        <div className="mt-3 flex items-start gap-3">
          <UrgencyBadge urgency={t.urgency} />
          <div>
            <p className="text-sm font-semibold text-slate-900">{t.topic}</p>
            <p className="mt-0.5 text-xs text-slate-500">
              Route to: {t.suggested_department}
            </p>
            {t.other_possible_topics.length > 0 && (
              <p className="mt-1 text-xs text-slate-400">
                Also possible: {t.other_possible_topics.join("; ")}
              </p>
            )}
          </div>
        </div>
        {turn.redFlags.length > 0 && (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 ring-1 ring-red-200">
            ⚑ {turn.redFlags.join(", ")}
          </p>
        )}
      </div>

      {/* Intake */}
      <div className="divider" />
      <div className="p-5">
        <h2 className="section-label">Intake card</h2>
        <dl className="mt-3 space-y-3">
          {intakeRows.map(([label, value]) =>
            value ? (
              <div key={label}>
                <dt className="text-[11px] font-medium text-slate-400">{label}</dt>
                <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
              </div>
            ) : null,
          )}
        </dl>
      </div>

      {/* Clarifying questions */}
      {t.clarifying_questions.length > 0 && (
        <>
          <div className="divider" />
          <div className="p-5">
            <h2 className="section-label">Clarifying questions</h2>
            <ul className="mt-3 space-y-2">
              {t.clarifying_questions.map((q) => (
                <li key={q} className="flex gap-2 text-sm text-slate-700">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                  {q}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </aside>
  );
}
