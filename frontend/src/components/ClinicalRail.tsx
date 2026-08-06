import { latestTurn, useConsultation } from "../state/consultation";
import UrgencyBadge from "./UrgencyBadge";

/** Right-hand rail: the latest turn's triage decision and intake details. */
export default function ClinicalRail() {
  const { state } = useConsultation();
  const turn = latestTurn(state);

  if (!turn) {
    return (
      <aside className="card border-dashed p-5 text-center">
        <p className="text-sm font-medium text-slate-600">Triage decision</p>
        <p className="mt-1 text-xs text-slate-400">
          Urgency, routing, the intake card, and the nurse's clarifying
          questions appear here after the first analysis.
        </p>
      </aside>
    );
  }

  const t = turn.triage;
  const intakeRows: Array<[string, string]> = [
    ["Patient language", t.intake_card.patient_language],
    ["Presenting complaint", t.intake_card.presenting_complaint],
    ["Key findings / entities", t.intake_card.key_findings],
    ["Possible conditions", t.intake_card.possible_conditions],
  ];

  return (
    <aside className="space-y-4">
      <section className="card p-5">
        <h2 className="card-title">Triage decision</h2>
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
      </section>

      <section className="card p-5">
        <h2 className="card-title">Intake card</h2>
        <dl className="mt-3 space-y-3">
          {intakeRows.map(([label, value]) =>
            value ? (
              <div key={label}>
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {label}
                </dt>
                <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
              </div>
            ) : null,
          )}
        </dl>
      </section>

      <section className="card p-5">
        <h2 className="card-title">Clarifying questions for the nurse</h2>
        <ul className="mt-3 space-y-2">
          {t.clarifying_questions.map((q) => (
            <li key={q} className="flex gap-2 text-sm text-slate-700">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
              {q}
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
