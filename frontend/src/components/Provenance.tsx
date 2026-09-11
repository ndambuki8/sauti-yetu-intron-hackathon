import type { Provenance } from "../api/types";

/**
 * Shared rendering for a knowledge-base citation. Used by both the reasoning
 * trace and the graph node inspector so provenance looks identical everywhere.
 *
 * Colour signals trust at a glance: green = guideline / clinician-reviewed,
 * blue = expert, amber = provisional / unreviewed (i.e. not yet clinically
 * verified). This is deliberate — it keeps the KB honest about its maturity.
 */
export function provenanceBadgeClass(value: string): string {
  const v = value.toLowerCase();
  if (v === "guideline" || v === "clinician-reviewed")
    return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  // Cross-checked against the source chart, pending clinician sign-off.
  if (v === "chart-verified") return "bg-sky-50 text-sky-700 ring-sky-200";
  if (v === "expert") return "bg-blue-50 text-blue-700 ring-blue-200";
  // provisional / unreviewed / anything else: flag as not-yet-verified.
  return "bg-amber-50 text-amber-700 ring-amber-200";
}

/** The evidence-level + review-status pills. Always safe to show compactly. */
export function ProvenanceBadges({ source }: { source: Provenance }) {
  return (
    <div className="flex flex-wrap gap-1">
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ring-1 ${provenanceBadgeClass(
          source.evidence_level,
        )}`}
      >
        {source.evidence_level}
      </span>
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ring-1 ${provenanceBadgeClass(
          source.review_status,
        )}`}
      >
        {source.review_status}
      </span>
    </div>
  );
}

/** The citation body — reference text, mapped scale, and link. No badges, so
 * callers can place the badges where they want (e.g. a collapsible summary). */
export function CitationDetails({ source }: { source: Provenance }) {
  return (
    <div className="text-xs">
      <p className="leading-snug text-slate-600">{source.ref}</p>
      {source.mapped_scale && (
        <p className="mt-1 text-slate-500">
          Scale: <span className="text-slate-600">{source.mapped_scale}</span>
        </p>
      )}
      {source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-1.5 inline-block font-medium text-blue-600 hover:text-blue-700 hover:underline"
        >
          View reference ↗
        </a>
      )}
    </div>
  );
}

/** Full citation: badges + details. Used by the graph node inspector. */
export function SourceCitation({ source }: { source: Provenance }) {
  return (
    <div className="text-xs">
      <ProvenanceBadges source={source} />
      <div className="mt-1.5">
        <CitationDetails source={source} />
      </div>
    </div>
  );
}
